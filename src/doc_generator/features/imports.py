"""Java and JavaScript/TypeScript imports, resolved to the repository's own modules.

Takes no LLM engine - see this package's docstring.

Why this exists (039 research Decision 2): `DependencyGraph` records one import
node per imported *name*, and for these languages the names are clean -
`com.acme.dto.*`, `static com.acme.util.Money.round`, `../core/account.service`
- but it resolves none of them to a file. The node's `sourceFile` is empty, so
033's `fallback.build_import_adjacency`, which maps a node to a module through
that path, coupled 0 of 64 Java modules and 2 of 43 TypeScript modules on
`nextgen-wealth-ledger`. Without coupling, every seed there stayed a lone group
and one feature ended up holding 85% of the repository.

The names are resolved here, at the point of use, rather than inside
`dependency_graph`: that package is read by every stage and persisted, and its
Python resolution rules are load-bearing (see `_resolve_file_candidate`).

It never reads the analysed repository: the names are already in the graph,
and the path index comes from the bundle.
"""

from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping

from dependency_graph import DependencyGraph
from repository_metadata.models import RepositoryBundle

from .evidence import relative_path

# A relative import is tried as written, then with each of these, then as the
# directory's `index` with each of these. The order is the resolution order.
JS_RESOLVE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

_JAVA_SUFFIX = ".java"

# A static or nested-class import is retried with its last segment dropped, but
# never below two segments: a one-segment name would match any class of that
# name anywhere in the repository, which is the misattribution FR-002 forbids.
_MIN_JAVA_NAME_SEGMENTS = 2

Weight = int | Fraction


def resolve_repository_imports(
    bundle: RepositoryBundle, graph: DependencyGraph, *, repository_root: str | Path
) -> dict[str, dict[str, Weight]]:
    """Import coupling between the repository's Java and JS/TS modules.

    Returns only edges between two distinct modules, symmetric, keyed by module
    key (`sourceFileId`). Weights (039 data-model § Adjacency):

    - a Java import naming a class, directly, statically or through a nested
      class, adds 1 per distinct target module;
    - a Java wildcard import of a package with *n* repository modules adds
      `Fraction(1, n)` to each, so it weighs no more in total than one direct
      import (FR-003);
    - a relative JS/TS import resolving to a module adds 1 per distinct target;
    - anything else - the standard library, a package, an alias, a missing
      file - adds nothing (FR-002).

    Modules are chosen by file suffix, never by the stored language label,
    whose spelling differs between indexing and tests. Only graph nodes left
    unresolved are read: a node the graph did resolve to a file is already
    counted by 033's adjacency, and counting it here too would double it.
    """
    path_by_key = {
        file_bundle.module.sourceFileId: relative_path(file_bundle.module.filePath, repository_root)
        for file_bundle in bundle.files
    }
    key_by_path = {path: key for key, path in path_by_key.items()}
    java = _JavaIndex(path_by_key)

    edges: dict[str, dict[str, Weight]] = defaultdict(dict)
    for file_bundle in sorted(bundle.files, key=lambda item: item.module.sourceFileId):
        module = file_bundle.module
        source = module.sourceFileId
        path = path_by_key[source]
        suffix = PurePosixPath(path).suffix.lower()
        if suffix != _JAVA_SUFFIX and suffix not in JS_RESOLVE_EXTENSIONS:
            continue

        direct: set[str] = set()
        shared: dict[str, Fraction] = defaultdict(Fraction)
        for name in _unresolved_import_names(graph, module.filePath):
            if suffix == _JAVA_SUFFIX:
                targets = java.resolve(name, importer=source)
            else:
                targets = _resolve_relative(name, path, key_by_path)
            if isinstance(targets, str):
                direct.add(targets)
            elif targets:
                for target, weight in targets.items():
                    shared[target] += weight

        for target in sorted(direct):
            _add(edges, source, target, 1)
        for target in sorted(shared):
            _add(edges, source, target, shared[target])

    return {source: dict(row) for source, row in edges.items()}


def _unresolved_import_names(graph: DependencyGraph, file_path: str) -> list[str]:
    return sorted(
        node.name
        for node in graph.dependencies(file_path, relation_type="import")
        if node.kind == "file" and not node.sourceFile and node.name
    )


def _add(edges: dict[str, dict[str, Weight]], source: str, target: str, weight: Weight) -> None:
    if source == target or not weight:
        return
    edges[source][target] = edges[source].get(target, 0) + weight
    edges[target][source] = edges[target].get(source, 0) + weight


class _JavaIndex:
    """Java modules by every trailing run of their path's segments.

    `backend/src/main/java/com/acme/Money.java` is filed under `Money`,
    `acme/Money`, `com/acme/Money` and so on, so a dotted name is resolved by
    one lookup of its whole slash form. That is what makes a match *whole*: a
    name matches a path ending with all of it, at a segment boundary, never a
    partial tail (039 research Decision 2; `org.other.dto.ADto` is not
    `com/acme/dto/ADto`).
    """

    def __init__(self, path_by_key: Mapping[str, str]) -> None:
        self.classes: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.packages: dict[str, list[str]] = defaultdict(list)
        for key, path in path_by_key.items():
            if not path.lower().endswith(_JAVA_SUFFIX):
                continue
            segments = path[: -len(_JAVA_SUFFIX)].split("/")
            for start in range(len(segments)):
                self.classes["/".join(segments[start:])].append((path, key))
            directory = segments[:-1]
            for start in range(len(directory)):
                self.packages["/".join(directory[start:])].append(key)

    def resolve(self, name: str, *, importer: str) -> str | dict[str, Fraction] | None:
        """One module key for a class import, a split weight for a package, or nothing."""
        name = name.strip()
        if name.startswith("static "):
            name = name[len("static ") :].strip()
        if name.endswith(".*"):
            package = name[:-2]
            members = sorted(key for key in self.packages.get(package.replace(".", "/"), ()) if key != importer)
            if members:
                return {key: Fraction(1, len(members)) for key in members}
            # `import static a.b.C.*` imports a class's members, not a package.
            name = package
        segments = [segment for segment in name.split(".") if segment]
        for cut in range(len(segments), _MIN_JAVA_NAME_SEGMENTS - 1, -1):
            matches = [match for match in self.classes.get("/".join(segments[:cut]), ()) if match[1] != importer]
            if matches:
                return min(matches)[1]
        return None


def _resolve_relative(name: str, importer_path: str, key_by_path: Mapping[str, str]) -> str | None:
    """A relative JS/TS import against the importer's directory; bare names are packages."""
    if not name.startswith("."):
        return None
    parts = _normalized(PurePosixPath(importer_path).parent.parts + PurePosixPath(name).parts)
    if parts is None:
        return None
    base = "/".join(parts)
    importer_key = key_by_path.get(importer_path)
    for candidate in _js_candidates(base):
        target = key_by_path.get(candidate)
        if target is not None and target != importer_key:
            return target
    return None


def _js_candidates(base: str) -> Iterable[str]:
    yield base
    for extension in JS_RESOLVE_EXTENSIONS:
        yield base + extension
    for extension in JS_RESOLVE_EXTENSIONS:
        yield f"{base}/index{extension}"


def _normalized(parts: Iterable[str]) -> list[str] | None:
    """Resolve `.` and `..`; `None` when the path climbs out of the repository."""
    kept: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not kept:
                return None
            kept.pop()
            continue
        kept.append(part)
    return kept
