"""Structural clustering: the fallback path, no longer the main one.

Every function below moved here from `sections.py` unchanged. It used to decide
the wiki's whole navigation; it now answers one narrower question - "how do I
group the modules no entry point reaches?" - which is what it was always
actually good at.

That question is not rare. `identify_entry_points` skips prose files outright,
so every README, every document and every spec in the analysed repository
arrives here. On a real indexing run this path groups the documentation.

Takes no LLM engine. See this package's docstring.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Mapping, Sequence

from dependency_graph import DependencyGraph
from repository_metadata.models import RepositoryBundle

from .evidence import FeatureEvidence, normalize_path

# A directory holding fewer modules than this is not a group on its own: it is
# absorbed into whichever group it is most coupled to. A one-module "area" is
# navigation noise, not a concept.
MIN_FALLBACK_MODULES = 2

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
class FallbackGroup:
    """One cluster of modules no entry point reaches."""

    leadModuleKey: str
    directoryPath: str
    memberKeys: tuple[str, ...]


def build_import_adjacency(
    bundle: RepositoryBundle, graph: DependencyGraph
) -> dict[str, dict[str, int]]:
    """Undirected module-to-module import weights, keyed by stable module key.

    Coupling is what decides a grouping, and coupling has no direction: a module
    belongs with the modules it imports just as much as with the modules that
    import it. Weights are symmetric so absorption, label propagation and the
    candidate stage's assignment all read the same graph.

    **An import node only counts when it names the module it is attributed to.**
    That guard is load-bearing, not defensive. `DependencyGraph` creates one node
    per imported *name*, and an unresolved import - every stdlib and third-party
    one - keeps the `sourceFile` of whichever repository file happened to declare
    it first. So the node for `__future__` carries `sourceFile=src/chat/budget.py`
    purely because `budget.py` sorted first, and mapping that node back by its
    path alone produced an import edge from every single module that writes
    `from __future__ import annotations` to `budget`.

    Measured on this repository before the guard: `budget` showed degree **131 of
    139 modules** and `models` 102, against true internal degrees of 4 and 12.
    Of 869 "import" edges, 192 targeted `budget` and 158 `models` - almost all of
    them shared stdlib imports. The adjacency was substantially fictional.

    Requiring `node.name` to equal the target module's name rejects exactly those:
    a real `from .models import ChatMessage` produces a node named `models` whose
    `sourceFile` really is `models.py`, and survives. This changes the clustering
    below as well as the candidate stage above, and it changes it for the better -
    directory grouping merely masked the corruption, it did not escape it.
    """
    key_by_path: dict[str, str] = {}
    name_by_key: dict[str, str] = {}
    for file_bundle in bundle.files:
        module = file_bundle.module
        key_by_path[normalize_path(module.filePath)] = module.sourceFileId
        name_by_key[module.sourceFileId] = module.name

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
            target_key = key_by_path.get(normalize_path(node.sourceFile))
            if target_key is None or target_key == source_key:
                continue
            if node.name != name_by_key.get(target_key):
                # An unresolved import wearing another module's file path. See
                # the docstring: this is where the fictional edges came from.
                continue
            adjacency[source_key][target_key] = adjacency[source_key].get(target_key, 0) + 1
            adjacency[target_key][source_key] = adjacency[target_key].get(source_key, 0) + 1
    return adjacency


def build_fallback_groups(
    evidence: Sequence[FeatureEvidence],
    adjacency: Mapping[str, Mapping[str, int]],
) -> tuple[FallbackGroup, ...]:
    """Cluster the modules handed over - not the whole repository.

    Directory layout is the seed: it is the grouping the authors already chose,
    it is stable across runs, and it costs no model call. The import graph then
    refines it in the two places a raw directory listing misreads the code - a
    directory too small to be a concept, and one too large to be a single one.
    """
    if not evidence:
        return ()

    members_by_directory: dict[str, list[str]] = {}
    directory_by_key: dict[str, str] = {}
    name_by_key: dict[str, str] = {}
    for item in evidence:
        members_by_directory.setdefault(item.directoryPath, []).append(item.moduleKey)
        directory_by_key[item.moduleKey] = item.directoryPath
        name_by_key[item.moduleKey] = item.moduleName

    ordered_by_directory = {
        directory: _ordered(keys, name_by_key) for directory, keys in members_by_directory.items()
    }
    ordered_by_directory = _absorb_small_directories(ordered_by_directory, adjacency, directory_by_key)

    groups: list[FallbackGroup] = []
    for directory in sorted(ordered_by_directory):
        groups.extend(
            _split_group(directory, ordered_by_directory[directory], adjacency, name_by_key)
        )
    return tuple(sorted(groups, key=lambda group: (group.directoryPath, group.leadModuleKey)))


def _absorb_small_directories(
    members_by_directory: Mapping[str, tuple[str, ...]],
    adjacency: Mapping[str, Mapping[str, int]],
    directory_by_key: Mapping[str, str],
) -> dict[str, tuple[str, ...]]:
    """Fold directories below `MIN_FALLBACK_MODULES` into a real group.

    Targets are chosen against the *original* directory grouping and only then
    are chains resolved, so the outcome never depends on iteration order. A
    directory with neither coupling nor a documented ancestor stays on its own
    rather than being forced somewhere arbitrary.
    """
    directories = set(members_by_directory)
    large = {
        directory
        for directory in directories
        if len(members_by_directory[directory]) >= MIN_FALLBACK_MODULES
    }
    small = sorted(directories - large)
    if not small or not large:
        return dict(members_by_directory)

    target_by_directory: dict[str, str] = {}
    for directory in small:
        target = _coupling_target(
            directory,
            members_by_directory[directory],
            adjacency,
            directory_by_key=directory_by_key,
            candidates=large,
        ) or _ancestor_target(directory, candidates=large)
        if target is not None:
            target_by_directory[directory] = target

    merged: dict[str, list[str]] = {
        directory: list(members) for directory, members in members_by_directory.items()
    }
    for directory in small:
        target = _resolve_absorption_target(directory, target_by_directory)
        if target is None or target == directory:
            continue
        merged[target].extend(merged.pop(directory, ()))

    return {directory: tuple(members) for directory, members in merged.items()}


def _coupling_target(
    directory: str,
    member_keys: tuple[str, ...],
    adjacency: Mapping[str, Mapping[str, int]],
    *,
    directory_by_key: Mapping[str, str],
    candidates: set[str],
) -> str | None:
    weights: Counter[str] = Counter()
    for member_key in member_keys:
        for neighbor_key, weight in adjacency.get(member_key, {}).items():
            neighbor_directory = directory_by_key.get(neighbor_key)
            if (
                neighbor_directory is None
                or neighbor_directory == directory
                or neighbor_directory not in candidates
            ):
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
    member_keys: tuple[str, ...],
    adjacency: Mapping[str, Mapping[str, int]],
    name_by_key: Mapping[str, str],
) -> list[FallbackGroup]:
    if len(member_keys) <= SPLIT_THRESHOLD_MODULES:
        return [
            FallbackGroup(
                leadModuleKey=lead_module_key(member_keys, adjacency, name_by_key),
                directoryPath=directory,
                memberKeys=member_keys,
            )
        ]

    labels = _label_propagation(set(member_keys), adjacency)

    communities: dict[str, list[str]] = {}
    for member_key in member_keys:
        communities.setdefault(labels[member_key], []).append(member_key)

    substantial = [group for group in communities.values() if len(group) >= MIN_SPLIT_COMMUNITY_MODULES]
    if len(communities) < 2 or len(substantial) != len(communities):
        # Either the directory is one community, or the split only shaved off
        # strays. A "group" of one module reads worse than the directory shown
        # whole, so the split is dropped rather than partially applied.
        return [
            FallbackGroup(
                leadModuleKey=lead_module_key(member_keys, adjacency, name_by_key),
                directoryPath=directory,
                memberKeys=member_keys,
            )
        ]

    split: list[FallbackGroup] = []
    for group in communities.values():
        ordered = _ordered(group, name_by_key)
        split.append(
            FallbackGroup(
                leadModuleKey=lead_module_key(ordered, adjacency, name_by_key),
                directoryPath=directory,
                memberKeys=ordered,
            )
        )
    return split


def _label_propagation(
    member_keys: set[str], adjacency: Mapping[str, Mapping[str, int]]
) -> dict[str, str]:
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


def lead_module_key(
    member_keys: Sequence[str],
    adjacency: Mapping[str, Mapping[str, int]],
    name_by_key: Mapping[str, str],
) -> str:
    """The member that best names a group: the most internally connected one.

    Also the rule that picks a *feature's anchor*, which is why it is public.
    Both answers must be the same rule - a feature named after one module and
    addressed by another would be two identities wearing one page.
    """
    keys = set(member_keys)

    def internal_degree(key: str) -> int:
        return sum(weight for neighbor, weight in adjacency.get(key, {}).items() if neighbor in keys)

    return min(keys, key=lambda key: (-internal_degree(key), name_by_key.get(key, key), key))


def _ordered(member_keys: Sequence[str], name_by_key: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(sorted(set(member_keys), key=lambda key: (name_by_key.get(key, key), key)))


def default_group_title(directory: str, lead_name: str, *, split: bool) -> str:
    """A group's name when no model has named it.

    Always a real, recognizable identifier from the repository - a directory
    name, or a directory name qualified by its lead module - rather than an
    invented label: a deterministic fallback that guesses at intent reads worse
    than one that simply states where the code lives.
    """
    base = "Root" if directory == "." else PurePosixPath(directory).name or directory
    return f"{base} - {lead_name}" if split else base
