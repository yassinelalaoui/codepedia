from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Mapping

from dependency_graph import DependencyGraph
from repository_metadata.models import RepositoryBundle

# A directory holding fewer modules than this is not a section on its own: it is
# absorbed into whichever section it is most coupled to. A one-module "section"
# is navigation noise, not a concept.
MIN_SECTION_MODULES = 2

# Above this many modules a single directory stops reading as one concept, so a
# community split is attempted. The split is only kept when it actually yields
# more than one substantial community (see `_split_group`).
SPLIT_THRESHOLD_MODULES = 12

# Below this many members a community produced by the split is a stray rather
# than a concept, and the whole split is abandoned.
MIN_SPLIT_COMMUNITY_MODULES = 2

# Label propagation converges in a handful of sweeps on import graphs this size;
# the cap only guards against a pathological oscillation.
MAX_LABEL_PROPAGATION_SWEEPS = 10


@dataclass(frozen=True, slots=True)
class SectionMember:
    """One module inside a section, keyed by the same stable ``sourceFileId``
    the module's own page is keyed by."""

    moduleKey: str
    name: str
    filePath: str
    docstring: str = ""
    generatedSummary: str = ""


@dataclass(frozen=True, slots=True)
class Section:
    """A conceptual area of the repository.

    ``key`` is derived only from the repository-relative directory (plus, for a
    split directory, the lead module's name) - never from a content hash and
    never from an ordinal position - so a section page's identity survives
    ordinary edits, exactly like ``ModuleSymbol.sourceFileId`` does for module
    pages.
    """

    key: str
    title: str
    directoryPath: str
    members: tuple[SectionMember, ...] = ()
    internalEdges: tuple[tuple[str, str], ...] = ()
    neighborKeys: tuple[str, ...] = ()
    description: str = ""
    isNarrated: bool = False

    @property
    def moduleKeys(self) -> tuple[str, ...]:
        return tuple(member.moduleKey for member in self.members)

    def membershipHash(self) -> str:
        """Identifies *what this section contains*, for narration caching.

        Deliberately excludes member docstrings and summaries: a section's name
        and description describe the grouping, and re-narrating every section
        because one member's summary changed would spend an LLM call per section
        on every run.
        """
        digest = hashlib.sha1()
        digest.update(self.key.encode("utf-8"))
        digest.update(b"\0")
        digest.update(self.directoryPath.encode("utf-8"))
        for member in self.members:
            digest.update(b"\0")
            digest.update(member.moduleKey.encode("utf-8"))
            digest.update(b"\0")
            digest.update(member.name.encode("utf-8"))
        return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class SectionSelection:
    sections: tuple[Section, ...] = ()

    def by_module_key(self) -> dict[str, Section]:
        return {member.moduleKey: section for section in self.sections for member in section.members}


def build_sections(
    bundle: RepositoryBundle,
    graph: DependencyGraph,
    *,
    repository_root: str | Path,
) -> SectionSelection:
    """Derive the repository's conceptual sections.

    Directory layout is the seed - it is the grouping the authors already chose,
    it is stable across runs, and it costs no model call. The import graph then
    *refines* it in the two places a raw directory listing misreads the code:

    1. a directory too small to be a concept is absorbed into the section it is
       most coupled to, falling back to its nearest documented ancestor;
    2. a directory too large to be one concept is split into communities by
       label propagation over its internal imports, and only when that split is
       substantial enough to be worth showing.

    Everything here is deterministic: the same repository yields the same
    sections, with the same keys, on every run. Naming a section is the only
    part left to a model (``section_narrator``), and naming never moves a
    module between sections.
    """
    members_by_directory = _group_members_by_directory(bundle, repository_root=repository_root)
    if not members_by_directory:
        return SectionSelection()

    adjacency = _build_import_adjacency(bundle, graph)
    members_by_directory = _absorb_small_directories(members_by_directory, adjacency)

    groups: list[tuple[str, str, tuple[SectionMember, ...]]] = []
    for directory in sorted(members_by_directory):
        groups.extend(_split_group(directory, members_by_directory[directory], adjacency))

    sections = tuple(
        _finalize_section(key, directory, members, adjacency)
        for key, directory, members in sorted(groups, key=lambda group: (group[1], group[0]))
    )
    return SectionSelection(sections=_with_neighbors(sections, adjacency))


def _group_members_by_directory(
    bundle: RepositoryBundle, *, repository_root: str | Path
) -> dict[str, tuple[SectionMember, ...]]:
    """Seed grouping, keyed by *full* repository-relative directory path.

    The path, not just its last segment: `src/api/models` and `src/db/models`
    are two areas that happen to share a folder name, and collapsing them into
    one "models" bucket - which grouping by `Path(...).parent.name` does - would
    describe a structure the repository does not have.
    """
    grouped: dict[str, list[SectionMember]] = {}
    for file_bundle in bundle.files:
        module = file_bundle.module
        directory = _relative_directory(module.filePath, repository_root)
        grouped.setdefault(directory, []).append(
            SectionMember(
                moduleKey=module.sourceFileId,
                name=module.name,
                filePath=module.filePath,
                docstring=module.docstring,
                generatedSummary=module.generatedSummary,
            )
        )
    return {directory: _ordered(members) for directory, members in grouped.items()}


def _build_import_adjacency(bundle: RepositoryBundle, graph: DependencyGraph) -> dict[str, dict[str, int]]:
    """Undirected module-to-module import weights, keyed by stable module key.

    Coupling is what decides a grouping, and coupling has no direction: a module
    belongs with the modules it imports just as much as with the modules that
    import it. Weights are symmetric so absorption and label propagation both
    read the same graph.
    """
    key_by_path = {
        _normalize_path(file_bundle.module.filePath): file_bundle.module.sourceFileId
        for file_bundle in bundle.files
    }
    adjacency: dict[str, dict[str, int]] = {key: {} for key in key_by_path.values()}
    for file_bundle in bundle.files:
        module = file_bundle.module
        source_key = module.sourceFileId
        neighbors = graph.dependencies(module.filePath, relation_type="import") + graph.dependents(
            module.filePath, relation_type="import"
        )
        for node in neighbors:
            if node.kind != "file":
                continue
            target_key = key_by_path.get(_normalize_path(node.sourceFile))
            if target_key is None or target_key == source_key:
                continue
            adjacency[source_key][target_key] = adjacency[source_key].get(target_key, 0) + 1
            adjacency[target_key][source_key] = adjacency[target_key].get(source_key, 0) + 1
    return adjacency


def _absorb_small_directories(
    members_by_directory: Mapping[str, tuple[SectionMember, ...]],
    adjacency: Mapping[str, Mapping[str, int]],
) -> dict[str, tuple[SectionMember, ...]]:
    """Fold directories below `MIN_SECTION_MODULES` into a real section.

    Targets are chosen against the *original* directory grouping and only then
    are chains resolved, so the outcome never depends on iteration order. A
    directory with neither coupling nor a documented ancestor stays on its own
    rather than being forced somewhere arbitrary.
    """
    directories = set(members_by_directory)
    large = {directory for directory in directories if len(members_by_directory[directory]) >= MIN_SECTION_MODULES}
    small = sorted(directories - large)
    if not small or not large:
        return dict(members_by_directory)

    directory_by_module_key = {
        member.moduleKey: directory
        for directory, members in members_by_directory.items()
        for member in members
    }

    target_by_directory: dict[str, str] = {}
    for directory in small:
        target = _coupling_target(
            directory,
            members_by_directory[directory],
            adjacency,
            directory_by_module_key=directory_by_module_key,
            candidates=large,
        ) or _ancestor_target(directory, candidates=large)
        if target is not None:
            target_by_directory[directory] = target

    merged: dict[str, list[SectionMember]] = {
        directory: list(members) for directory, members in members_by_directory.items()
    }
    for directory in small:
        target = _resolve_absorption_target(directory, target_by_directory)
        if target is None or target == directory:
            continue
        merged[target].extend(merged.pop(directory, ()))

    return {directory: _ordered(members) for directory, members in merged.items()}


def _coupling_target(
    directory: str,
    members: tuple[SectionMember, ...],
    adjacency: Mapping[str, Mapping[str, int]],
    *,
    directory_by_module_key: Mapping[str, str],
    candidates: set[str],
) -> str | None:
    weights: Counter[str] = Counter()
    for member in members:
        for neighbor_key, weight in adjacency.get(member.moduleKey, {}).items():
            neighbor_directory = directory_by_module_key.get(neighbor_key)
            if neighbor_directory is None or neighbor_directory == directory or neighbor_directory not in candidates:
                continue
            weights[neighbor_directory] += weight
    if not weights:
        return None
    return min(weights.items(), key=lambda item: (-item[1], item[0]))[0]


def _ancestor_target(directory: str, *, candidates: set[str]) -> str | None:
    if directory == ".":
        return None
    parts = PurePosixPath(directory).parts
    for depth in range(len(parts) - 1, 0, -1):
        ancestor = "/".join(parts[:depth])
        if ancestor in candidates:
            return ancestor
    return "." if "." in candidates else None


def _resolve_absorption_target(directory: str, target_by_directory: Mapping[str, str]) -> str | None:
    """Follow an absorption chain to its endpoint, refusing to loop.

    Every target is a directory that was large enough to keep, so a chain is at
    most one hop today; the guard keeps that an invariant rather than an
    assumption that a later threshold change could quietly break.
    """
    seen = {directory}
    current = target_by_directory.get(directory)
    while current is not None and current in target_by_directory and current not in seen:
        seen.add(current)
        current = target_by_directory[current]
    return None if current in seen else current


def _split_group(
    directory: str,
    members: tuple[SectionMember, ...],
    adjacency: Mapping[str, Mapping[str, int]],
) -> list[tuple[str, str, tuple[SectionMember, ...]]]:
    if len(members) <= SPLIT_THRESHOLD_MODULES:
        return [(directory, directory, members)]

    member_keys = {member.moduleKey for member in members}
    labels = _label_propagation(member_keys, adjacency)

    communities: dict[str, list[SectionMember]] = {}
    for member in members:
        communities.setdefault(labels[member.moduleKey], []).append(member)

    substantial = [group for group in communities.values() if len(group) >= MIN_SPLIT_COMMUNITY_MODULES]
    if len(communities) < 2 or len(substantial) != len(communities):
        # Either the directory is one community, or the split only shaved off
        # strays. A "section" of one module reads worse than the directory shown
        # whole, so the split is dropped rather than partially applied.
        return [(directory, directory, members)]

    split: list[tuple[str, str, tuple[SectionMember, ...]]] = []
    for group in communities.values():
        ordered = _ordered(group)
        lead = _lead_member(ordered, adjacency)
        split.append((f"{directory}#{lead.name}", directory, ordered))
    return split


def _label_propagation(member_keys: set[str], adjacency: Mapping[str, Mapping[str, int]]) -> dict[str, str]:
    """Community labels over one directory's internal import edges.

    Classic label propagation, made deterministic in the two places the
    algorithm is normally random: nodes are visited in sorted key order rather
    than shuffled, and the strongest-label tie is broken by the label string
    rather than arbitrarily. Edges leaving the directory are ignored - the split
    answers "how does this directory divide", not "where should these modules
    live", which is `_absorb_small_directories`' question.
    """
    ordered_keys = sorted(member_keys)
    labels = {key: key for key in ordered_keys}
    for _sweep in range(MAX_LABEL_PROPAGATION_SWEEPS):
        changed = False
        for key in ordered_keys:
            weights: Counter[str] = Counter()
            for neighbor_key, weight in adjacency.get(key, {}).items():
                neighbor_label = labels.get(neighbor_key)
                if neighbor_label is not None:
                    weights[neighbor_label] += weight
            if not weights:
                continue
            best = min(weights.items(), key=lambda item: (-item[1], item[0]))[0]
            if best != labels[key]:
                labels[key] = best
                changed = True
        if not changed:
            break
    return labels


def _lead_member(members: tuple[SectionMember, ...], adjacency: Mapping[str, Mapping[str, int]]) -> SectionMember:
    """The member that best names a group: the most internally connected one."""
    member_keys = {member.moduleKey for member in members}

    def internal_degree(member: SectionMember) -> int:
        return sum(
            weight
            for neighbor_key, weight in adjacency.get(member.moduleKey, {}).items()
            if neighbor_key in member_keys
        )

    return min(members, key=lambda member: (-internal_degree(member), member.name, member.moduleKey))


def _finalize_section(
    key: str,
    directory: str,
    members: tuple[SectionMember, ...],
    adjacency: Mapping[str, Mapping[str, int]],
) -> Section:
    member_keys = {member.moduleKey for member in members}
    internal_edges = sorted(
        {
            (min(member.moduleKey, neighbor_key), max(member.moduleKey, neighbor_key))
            for member in members
            for neighbor_key in adjacency.get(member.moduleKey, {})
            if neighbor_key in member_keys
        }
    )
    return Section(
        key=key,
        title=default_section_title(key, directory),
        directoryPath=directory,
        members=members,
        internalEdges=tuple(internal_edges),
    )


def default_section_title(key: str, directory: str) -> str:
    """The section's name when no model has named it.

    Always a real, recognizable identifier from the repository - a directory
    name, or a directory name qualified by its lead module - rather than an
    invented label: a deterministic fallback that guesses at intent reads worse
    than one that simply states where the code lives.
    """
    base = "Root" if directory == "." else PurePosixPath(directory).name or directory
    _, separator, lead_name = key.partition("#")
    return f"{base} - {lead_name}" if separator else base


def _with_neighbors(
    sections: tuple[Section, ...], adjacency: Mapping[str, Mapping[str, int]]
) -> tuple[Section, ...]:
    section_key_by_module = {member.moduleKey: section.key for section in sections for member in section.members}
    resolved: list[Section] = []
    for section in sections:
        neighbor_keys: set[str] = set()
        for member in section.members:
            for neighbor_key in adjacency.get(member.moduleKey, {}):
                neighbor_section_key = section_key_by_module.get(neighbor_key)
                if neighbor_section_key is not None and neighbor_section_key != section.key:
                    neighbor_keys.add(neighbor_section_key)
        resolved.append(replace(section, neighborKeys=tuple(sorted(neighbor_keys))))
    return tuple(resolved)


def _ordered(members: list[SectionMember] | tuple[SectionMember, ...]) -> tuple[SectionMember, ...]:
    return tuple(sorted(members, key=lambda member: (member.name, member.moduleKey)))


def _relative_directory(file_path: str, repository_root: str | Path) -> str:
    path = Path(file_path)
    root = Path(repository_root)
    try:
        relative = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        # A path outside the repository root, or one this filesystem cannot
        # resolve, still has to land somewhere; its own parent name is the
        # closest honest answer.
        return path.parent.name or "."
    directory = relative.parent.as_posix()
    return directory if directory not in ("", ".") else "."


def _normalize_path(path: str) -> str:
    return Path(path).as_posix().replace("\\", "/")
