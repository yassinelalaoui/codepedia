"""What the Overview narrative may draw on: bounded, ordered, and model-free.

Takes no LLM engine - see this package's docstring for why that is a signature
and not a convention.

Everything here is derived from state the run already holds: the repaired
features (so the narrative names the subsystems the sidebar shows, never the
planner's pre-repair candidates), the entry points, the dependency graph and
the opening paragraph of the analysed repository's own README. Not the README's
bullet list, which is the planner's evidence: measured on the sample repository
it is headings and directory names, and a model copies directory names into
citations that grounding then has to reject. Every collection is capped by a constant
and taken in a defined order, which is what lets `narrator` bound its prompt by
construction and lets an unchanged repository produce the same prompt - and so
the same cache key - on every run.
"""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from dependency_graph import DependencyGraph
from repository_metadata.models import RepositoryBundle

from ..entry_point_diagram import identify_entry_points
from ..features.evidence import (  # noqa: F401 - re-exported; defined in `features` (039 research Decision 3)
    ENTRY_KINDS,
    MAX_EVIDENCE_CALL_DEPTH,
    MAX_README_LEAD_CHARS,
    entry_kind,
    is_test_path,
    read_readme_lead,
)
from ..features.validate import Feature, FeatureMember
from ..plain_text import excerpt, first_sentence
from ..prose import display_label, is_prose_file

# Twelve subsystems describe any repository's shape; past that the prompt grows
# with the repository, which is exactly what FR-020 forbids. The subsystems
# table still lists every one.
MAX_PROMPTED_FEATURES = 12

# Six flows are enough to say where work enters: commands, routes and `main`
# first (`ENTRY_KINDS`), then the six reaching the most modules, so the
# principal paths are the ones described.
MAX_PROMPTED_ENTRY_FLOWS = 6

# How many subsystems may receive a paragraph of their own (spec FR-025). Here
# rather than in `grounding` because the evidence decides which ones are major.
MAX_SUBSYSTEM_PARAGRAPHS = 8

# `ENTRY_KINDS` (commands, routes and `main`, which rank first and which the
# prompt labels as entries) and `is_test_path` are imported above from
# `features.evidence`, which grouping reads too.

MAX_DESCRIPTION_CHARS = 160
MAX_ANCHOR_SUMMARY_CHARS = 120
MAX_MEMBER_NAMES = 3
MAX_MEMBER_NAME_CHARS = 50
MAX_REACHED_FEATURES = 5


@dataclass(frozen=True, slots=True)
class FeatureBrief:
    """One subsystem as the model is told about it."""

    handle: str
    featureKey: str
    title: str
    description: str
    kind: str
    anchorName: str
    anchorPath: str
    anchorSummary: str
    memberNames: tuple[str, ...]
    entryPointCount: int


@dataclass(frozen=True, slots=True)
class EntryFlow:
    """Where one entry point takes work: the subsystems it reaches, in order."""

    qualifiedName: str
    #: One of `ENTRY_KINDS`, or "function" for a function nothing calls.
    kind: str
    modulePath: str
    featureHandle: str
    reachedHandles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OverviewEvidence:
    repositoryName: str
    languages: tuple[str, ...]
    readmeLead: str
    features: tuple[FeatureBrief, ...]
    omittedFeatureCount: int
    entryFlows: tuple[EntryFlow, ...]
    majorFeatureKeys: tuple[str, ...]
    #: Every current feature, prompted or not, as (key, title) in navigation
    #: order. Grounding resolves a handle to a key and then needs to know the
    #: key still exists - and what it is called now - to link it.
    featureTitles: tuple[tuple[str, str], ...] = ()
    #: SHA-1 of every file's path and content hash. Never part of the prompt:
    #: the cache key says whether the *question* changed, this says whether the
    #: *repository* did. A narrative kept for an unchanged repository after only
    #: the prompt changed is not "an earlier version" (038 analyze finding I2).
    repositoryFingerprint: str = ""

    def handle_map(self) -> dict[str, str]:
        return {brief.handle: brief.featureKey for brief in self.features}

    def feature_title_by_key(self) -> dict[str, str]:
        return dict(self.featureTitles)


def build_overview_evidence(
    features: Sequence[Feature],
    bundle: RepositoryBundle,
    graph: DependencyGraph,
    *,
    repository_root: str | Path,
) -> OverviewEvidence:
    """The bounded evidence bundle for one Overview narrative."""
    prompted = tuple(features[:MAX_PROMPTED_FEATURES])
    briefs = tuple(
        _brief(f"f{index}", feature, repository_root) for index, feature in enumerate(prompted)
    )
    handle_by_key = {brief.featureKey: brief.handle for brief in briefs}
    major = tuple(
        feature.key
        for feature in prompted
        if feature.kind != "tooling" and not _is_docs_or_tests_only(feature, repository_root)
    )[:MAX_SUBSYSTEM_PARAGRAPHS]

    repository = bundle.repository
    readme_lead = read_readme_lead(repository_root)
    return OverviewEvidence(
        repositoryName=Path(repository.rootPath).name or repository.rootPath,
        languages=tuple(sorted(repository.detectedLanguages or ())),
        readmeLead=readme_lead,
        features=briefs,
        omittedFeatureCount=max(0, len(features) - len(prompted)),
        entryFlows=_entry_flows(features, handle_by_key, bundle, graph, repository_root),
        majorFeatureKeys=major,
        featureTitles=tuple((feature.key, feature.title) for feature in features),
        repositoryFingerprint=repository_fingerprint(bundle, repository_root, readme_lead=readme_lead),
    )


def repository_fingerprint(bundle: RepositoryBundle, repository_root: str | Path, *, readme_lead: str = "") -> str:
    """Identifies everything the evidence reads from the repository, and no prompt.

    The analysed files' contents, plus the README lead, which is read from disk
    rather than from the index - a repository whose Markdown is not indexed
    would otherwise change its prompt without changing its fingerprint.
    """
    digest = hashlib.sha1()
    digest.update(readme_lead.encode("utf-8") + b"\0")
    for path, content_hash in sorted(
        (_relative_path(file_bundle.file.path, repository_root), file_bundle.file.contentHash)
        for file_bundle in bundle.files
    ):
        digest.update(f"{path}\0{content_hash}\n".encode("utf-8"))
    return digest.hexdigest()


def _brief(handle: str, feature: Feature, repository_root: str | Path) -> FeatureBrief:
    anchor = next((member for member in feature.members if member.moduleKey == feature.key), None)
    if anchor is None and feature.members:
        anchor = feature.members[0]
    others = [member for member in feature.members if anchor is None or member.moduleKey != anchor.moduleKey]
    return FeatureBrief(
        handle=handle,
        featureKey=feature.key,
        title=feature.title,
        description=excerpt(feature.description, max_chars=MAX_DESCRIPTION_CHARS),
        kind=feature.kind,
        anchorName=_label(anchor, repository_root) if anchor else "",
        anchorPath=_relative_path(anchor.filePath, repository_root) if anchor else "",
        anchorSummary=_summary(anchor),
        memberNames=tuple(_member_name(member, repository_root) for member in others[:MAX_MEMBER_NAMES]),
        entryPointCount=feature.exposedEntryPointCount,
    )


def _is_docs_or_tests_only(feature: Feature, repository_root: str | Path) -> bool:
    """Whether every member is known to be documentation or a test file.

    Such a subsystem gets no paragraph. Measured on the sample repository, the
    planner's kind ranking put "Documentation" among the eight while both
    storage subsystems went without (research Decision 19). A member with no
    path is not known to be either, so it keeps its subsystem eligible.
    """
    paths = [member.filePath for member in feature.members]
    return bool(paths) and all(
        path and (is_prose_file(path) or is_test_path(_relative_path(path, repository_root))) for path in paths
    )


def _summary(member: FeatureMember | None) -> str:
    if member is None:
        return ""
    source = member.docstring or member.generatedSummary
    return first_sentence(source, max_chars=MAX_ANCHOR_SUMMARY_CHARS) if source else ""


def _label(member: FeatureMember, repository_root: str | Path) -> str:
    return display_label(member.name, member.filePath, repository_root) if member.filePath else member.name


def _member_name(member: FeatureMember, repository_root: str | Path) -> str:
    """A path when it fits - it resolves unambiguously - else the label."""
    path = _relative_path(member.filePath, repository_root) if member.filePath else ""
    if path and len(path) <= MAX_MEMBER_NAME_CHARS:
        return path
    return _label(member, repository_root)[:MAX_MEMBER_NAME_CHARS]


def _relative_path(file_path: str, repository_root: str | Path) -> str:
    path = Path(file_path)
    try:
        return path.resolve().relative_to(Path(repository_root).resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def _entry_flows(
    features: Sequence[Feature],
    handle_by_key: Mapping[str, str],
    bundle: RepositoryBundle,
    graph: DependencyGraph,
    repository_root: str | Path,
) -> tuple[EntryFlow, ...]:
    module_key_by_symbol: dict[str, str] = {}
    path_by_module_key: dict[str, str] = {}
    for file_bundle in bundle.files:
        module = file_bundle.module
        path_by_module_key[module.sourceFileId] = module.filePath
        for symbol in (module, *file_bundle.classes, *file_bundle.functions):
            module_key_by_symbol[symbol.id] = module.sourceFileId
    feature_key_by_module = {
        member.moduleKey: feature.key for feature in features for member in feature.members
    }
    ranked: list[tuple[int, int, str, EntryFlow]] = []
    for entry_point in identify_entry_points(bundle, graph):
        module_path = path_by_module_key.get(entry_point.moduleKey, "")
        if module_path and (
            is_prose_file(module_path) or is_test_path(_relative_path(module_path, repository_root))
        ):
            continue
        depth_by_module = _module_depths(graph, entry_point.symbolId, module_key_by_symbol)
        own_feature = feature_key_by_module.get(entry_point.moduleKey, "")

        depth_by_feature: dict[str, int] = {}
        for module_key, depth in depth_by_module.items():
            feature_key = feature_key_by_module.get(module_key)
            if not feature_key or feature_key == own_feature or feature_key not in handle_by_key:
                continue
            if depth < depth_by_feature.get(feature_key, depth + 1):
                depth_by_feature[feature_key] = depth
        reached = sorted(
            depth_by_feature,
            key=lambda key: (depth_by_feature[key], _handle_index(handle_by_key[key])),
        )[:MAX_REACHED_FEATURES]

        kind = entry_kind(entry_point)
        flow = EntryFlow(
            qualifiedName=f"{entry_point.className}.{entry_point.name}" if entry_point.className else entry_point.name,
            kind=kind,
            modulePath=_relative_path(module_path, repository_root) if module_path else entry_point.moduleName,
            featureHandle=handle_by_key.get(own_feature, ""),
            reachedHandles=tuple(handle_by_key[key] for key in reached),
        )
        tier = 0 if kind in ENTRY_KINDS else 1
        ranked.append((tier, -len(depth_by_module), entry_point.stableKey, flow))

    ranked.sort(key=lambda item: item[:3])
    return tuple(item[3] for item in ranked[:MAX_PROMPTED_ENTRY_FLOWS])


def _module_depths(
    graph: DependencyGraph, start_symbol_id: str, module_key_by_symbol: Mapping[str, str]
) -> dict[str, int]:
    """The call depth at which each module is first reached from one entry point.

    A visited-set BFS for the reason `features.evidence._reachable_symbol_ids`
    gives, but recording depth: "where work goes next" is an ordering question,
    and reachability alone cannot answer it.
    """
    seen = {start_symbol_id}
    depths: dict[str, int] = {}
    frontier: deque[tuple[str, int]] = deque([(start_symbol_id, 0)])
    while frontier:
        symbol_id, depth = frontier.popleft()
        module_key = module_key_by_symbol.get(symbol_id)
        if module_key is not None and module_key not in depths:
            depths[module_key] = depth
        if depth >= MAX_EVIDENCE_CALL_DEPTH:
            continue
        for callee in graph.functions_called_by(symbol_id):
            if callee.id not in seen:
                seen.add(callee.id)
                frontier.append((callee.id, depth + 1))
    return depths


def _handle_index(handle: str) -> int:
    try:
        return int(handle[1:])
    except ValueError:
        return 0
