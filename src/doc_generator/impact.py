from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from dependency_graph import DependencyGraph
from repository_metadata.models import RepositoryBundle

from . import links
from .entry_point_diagram import identify_entry_points
from .manifest_store import PageManifestEntry
from .models import EdgeId, RegenerationImpactSet
from .sections import Section


def compute_regeneration_impact(
    *,
    bundle: RepositoryBundle,
    dependency_graph: DependencyGraph,
    previous_entries: Iterable[PageManifestEntry],
    changed_paths: Iterable[str | Path] = (),
    changed_symbol_ids: Iterable[str] = (),
    changed_dependency_edge_ids: Iterable[EdgeId] = (),
    sections: Sequence[Section] = (),
) -> RegenerationImpactSet:
    entries = list(previous_entries)
    changed_path_strings = {_normalize(path) for path in changed_paths}
    changed_edges = list(changed_dependency_edge_ids)

    # Every id below keys off each module's stable sourceFileId (path-derived),
    # never the volatile content-hash ModuleSymbol.id, so page identity survives
    # ordinary edits that shift a symbol's line range.
    module_key_by_symbol_id: dict[str, str] = {}
    module_key_by_file_path: dict[str, str] = {}
    for file_bundle in bundle.files:
        module_key = file_bundle.module.sourceFileId
        module_key_by_file_path[_normalize(file_bundle.file.path)] = module_key
        for symbol in (file_bundle.module, *file_bundle.classes, *file_bundle.functions):
            module_key_by_symbol_id[symbol.id] = module_key

    changed_file_ids: set[str] = set()
    direct_symbol_ids: set[str] = set(changed_symbol_ids)
    for file_bundle in bundle.files:
        if _normalize(file_bundle.file.path) in changed_path_strings:
            changed_file_ids.add(file_bundle.file.id)
            direct_symbol_ids.add(file_bundle.module.id)
            direct_symbol_ids.update(symbol.id for symbol in file_bundle.classes)
            direct_symbol_ids.update(symbol.id for symbol in file_bundle.functions)

    # Unlike the summary pipeline's prompt context, a module page never embeds another
    # module's symbols or summaries - it only links to related modules by stable id/name,
    # neither of which changes when a callee's body changes. So, unlike summary
    # generation, a changed symbol's callers do not need their page regenerated here.
    impacted_module_keys: set[str] = {
        owning_key for symbol_id in direct_symbol_ids if (owning_key := module_key_by_symbol_id.get(symbol_id))
    }

    impacted_diagram_module_keys: set[str] = set()
    for source_id, target_id, _edge_type in changed_edges:
        for node_id in (source_id, target_id):
            node = dependency_graph.nodes.get(node_id)
            if node is None:
                continue
            if node.kind == "file":
                module_key = module_key_by_file_path.get(_normalize(node.sourceFile))
            else:
                module_key = module_key_by_symbol_id.get(node.id)
            if module_key:
                impacted_diagram_module_keys.add(module_key)
                impacted_module_keys.add(module_key)

    impacted_page_ids: set[str] = set()
    for module_key in impacted_module_keys:
        impacted_page_ids.add(links.module_page_id(module_key))
    for module_key in impacted_diagram_module_keys:
        impacted_page_ids.add(links.diagram_page_id(module_key))

    # A section page lists its members with their docstrings and summaries, so
    # unlike a module page - which links to its neighbours by stable id/name and
    # is therefore untouched by what they contain - it really does go stale when
    # a member changes. Membership is read from the freshly derived sections
    # rather than from the previous manifest, so a module that moved between
    # sections invalidates both the section it left and the one it joined.
    section_key_by_module_key = {
        member.moduleKey: section.key for section in sections for member in section.members
    }
    for module_key in impacted_module_keys:
        section_key = section_key_by_module_key.get(module_key)
        if section_key:
            impacted_page_ids.add(links.section_page_id(section_key))

    # The class diagram is repository-wide: which classes rank as "major" can
    # change from a single edit anywhere in the repository, so it always
    # refreshes on any qualifying change rather than being scoped like a
    # per-module page, per research.md Decision 3.
    has_any_class = any(file_bundle.classes for file_bundle in bundle.files)
    if has_any_class and (direct_symbol_ids or changed_edges):
        impacted_page_ids.add(links.class_diagram_page_id())

    # Entry-point set membership is recomputed fresh every run rather than
    # incrementally diffed (research.md Decision 8, mirroring 021's major-class
    # ranking precedent) - cheap, in-memory, no source re-parse.
    entry_points = identify_entry_points(bundle, dependency_graph)
    current_sequence_diagram_page_ids = {links.sequence_diagram_page_id(entry_point.stableKey) for entry_point in entry_points}
    for entry_point in entry_points:
        if entry_point.symbolId in direct_symbol_ids:
            impacted_page_ids.add(links.sequence_diagram_page_id(entry_point.stableKey))
    for entry in entries:
        if entry.kind == "sequence-diagram" and set(entry.sourceSymbolIds) & direct_symbol_ids:
            impacted_page_ids.add(entry.pageId)

    # The use-case diagram is repository-wide, keyed off the same
    # already-computed entry-point list, the same "refresh on any qualifying
    # change" rule as the class diagram above (research.md Decision 6).
    has_any_entry_point = bool(entry_points)
    if has_any_entry_point and (direct_symbol_ids or changed_edges):
        impacted_page_ids.add(links.use_case_diagram_page_id())

    current_section_page_ids = {links.section_page_id(section.key) for section in sections}
    current_module_page_ids = {links.module_page_id(file_bundle.module.sourceFileId) for file_bundle in bundle.files}
    current_diagram_page_ids = {links.diagram_page_id(file_bundle.module.sourceFileId) for file_bundle in bundle.files}
    current_class_diagram_page_ids = {links.class_diagram_page_id()} if has_any_class else set()
    current_use_case_diagram_page_ids = {links.use_case_diagram_page_id()} if has_any_entry_point else set()
    # The diagrams-index page (024) is always generated once at all (never
    # conditionally present like the class/use-case diagram pages), so its id
    # is unconditionally current - it must never appear in removedPageIds.
    current_page_ids = (
        current_section_page_ids
        | current_module_page_ids
        | current_diagram_page_ids
        | current_class_diagram_page_ids
        | current_sequence_diagram_page_ids
        | current_use_case_diagram_page_ids
        | {links.HOME_PAGE_ID, links.diagrams_index_page_id()}
    )
    removed_page_ids = {entry.pageId for entry in entries} - current_page_ids

    # A page's link target is only ever invalidated by removal, not by the target's
    # content changing (links are keyed by the target's stable page id/path), so only
    # removed pages propagate impact to whoever referenced them.
    _add_referrers_of(impacted_page_ids, removed_page_ids, entries)

    previous_module_page_ids = {entry.pageId for entry in entries if entry.kind == "module"}
    previous_section_page_ids = {entry.pageId for entry in entries if entry.kind == "section"}
    requires_home_regeneration = (
        previous_module_page_ids != current_module_page_ids
        or previous_section_page_ids != current_section_page_ids
    )

    # The sidebar renders the whole section/module tree into *every* page, so a
    # page that is otherwise untouched still shows stale navigation once that
    # tree changes shape. No per-page impact set can express that, hence a
    # separate flag the generator answers by regenerating everything. It stays
    # cheap because the tree only reshapes when files are added, removed or
    # moved - never when their contents change, which is the ordinary case the
    # incremental path exists to make fast.
    requires_navigation_regeneration = (
        previous_module_page_ids != current_module_page_ids
        or previous_section_page_ids != current_section_page_ids
    )

    # The diagrams-index page (024, research.md Decision 6) reflects four
    # independent, repository-wide facts: the module-page set, the
    # sequence-diagram-page set, and whether a class-diagram/use-case-diagram
    # page currently exists. It refreshes whenever any of them differs from
    # the previous manifest snapshot.
    previous_sequence_diagram_page_ids = {entry.pageId for entry in entries if entry.kind == "sequence-diagram"}
    previous_page_ids = {entry.pageId for entry in entries}
    previous_class_diagram_exists = links.class_diagram_page_id() in previous_page_ids
    previous_use_case_diagram_exists = links.use_case_diagram_page_id() in previous_page_ids
    requires_diagrams_index_regeneration = (
        previous_module_page_ids != current_module_page_ids
        or previous_sequence_diagram_page_ids != current_sequence_diagram_page_ids
        or previous_class_diagram_exists != has_any_class
        or previous_use_case_diagram_exists != has_any_entry_point
    )

    return RegenerationImpactSet(
        changedFileIds=tuple(sorted(changed_file_ids)),
        changedSymbolIds=tuple(sorted(direct_symbol_ids)),
        changedDependencyEdgeIds=tuple(changed_edges),
        impactedPageIds=tuple(sorted(impacted_page_ids)),
        removedPageIds=tuple(sorted(removed_page_ids)),
        requiresHomePageRegeneration=requires_home_regeneration,
        requiresDiagramsIndexRegeneration=requires_diagrams_index_regeneration,
        requiresNavigationRegeneration=requires_navigation_regeneration,
    )


def _add_referrers_of(impacted_page_ids: set[str], removed_page_ids: set[str], entries: list[PageManifestEntry]) -> None:
    reverse_links: dict[str, set[str]] = {}
    for entry in entries:
        for target in entry.linkedPageIds:
            reverse_links.setdefault(target, set()).add(entry.pageId)
    for removed_id in removed_page_ids:
        for referrer in reverse_links.get(removed_id, ()):
            if referrer not in removed_page_ids:
                impacted_page_ids.add(referrer)


def _normalize(path: str | Path) -> str:
    return Path(path).as_posix().replace("\\", "/")
