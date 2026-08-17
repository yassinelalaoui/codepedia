from __future__ import annotations

from pathlib import Path
from typing import Iterable

from dependency_graph import DependencyGraph
from repository_metadata.models import RepositoryBundle

from . import links
from .manifest_store import PageManifestEntry
from .models import EdgeId, RegenerationImpactSet


def compute_regeneration_impact(
    *,
    bundle: RepositoryBundle,
    dependency_graph: DependencyGraph,
    previous_entries: Iterable[PageManifestEntry],
    changed_paths: Iterable[str | Path] = (),
    changed_symbol_ids: Iterable[str] = (),
    changed_dependency_edge_ids: Iterable[EdgeId] = (),
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

    # The class diagram is repository-wide: which classes rank as "major" can
    # change from a single edit anywhere in the repository, so it always
    # refreshes on any qualifying change rather than being scoped like a
    # per-module page, per research.md Decision 3.
    has_any_class = any(file_bundle.classes for file_bundle in bundle.files)
    if has_any_class and (direct_symbol_ids or changed_edges):
        impacted_page_ids.add(links.class_diagram_page_id())

    current_module_page_ids = {links.module_page_id(file_bundle.module.sourceFileId) for file_bundle in bundle.files}
    current_diagram_page_ids = {links.diagram_page_id(file_bundle.module.sourceFileId) for file_bundle in bundle.files}
    current_class_diagram_page_ids = {links.class_diagram_page_id()} if has_any_class else set()
    current_page_ids = (
        current_module_page_ids | current_diagram_page_ids | current_class_diagram_page_ids | {links.HOME_PAGE_ID}
    )
    removed_page_ids = {entry.pageId for entry in entries} - current_page_ids

    # A page's link target is only ever invalidated by removal, not by the target's
    # content changing (links are keyed by the target's stable page id/path), so only
    # removed pages propagate impact to whoever referenced them.
    _add_referrers_of(impacted_page_ids, removed_page_ids, entries)

    previous_module_page_ids = {entry.pageId for entry in entries if entry.kind == "module"}
    requires_home_regeneration = previous_module_page_ids != current_module_page_ids

    return RegenerationImpactSet(
        changedFileIds=tuple(sorted(changed_file_ids)),
        changedSymbolIds=tuple(sorted(direct_symbol_ids)),
        changedDependencyEdgeIds=tuple(changed_edges),
        impactedPageIds=tuple(sorted(impacted_page_ids)),
        removedPageIds=tuple(sorted(removed_page_ids)),
        requiresHomePageRegeneration=requires_home_regeneration,
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
