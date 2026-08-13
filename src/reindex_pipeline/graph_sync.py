from __future__ import annotations

from pathlib import Path
from typing import Iterable

from dependency_graph import DependencyGraph
from parser_engine import FileSymbolInventory

from .models import EdgeId


def sync_graph(
    *,
    graph: DependencyGraph,
    dependency_graph_path: str | Path,
    inventories_to_ingest: Iterable[FileSymbolInventory],
    source_files_to_remove: Iterable[str],
) -> tuple[EdgeId, ...]:
    edges_before = set(graph.edges.keys())

    inventories = list(inventories_to_ingest)
    changed_sources = {inventory.sourceFile for inventory in inventories} | set(source_files_to_remove)
    # A symbol's id is content-hash-derived (data-model.md), so re-ingesting a changed
    # file replaces its symbols' ids outright. remove_source_file() correctly drops
    # edges pointing at the old ids — including ones from *unchanged* caller files
    # elsewhere in the repository, which are not being re-ingested this batch and so
    # would never get their edge back. Capture those before removal and re-link them
    # by name afterward, so "who calls this symbol" (dependents()) survives the
    # symbol's identity change even though its caller wasn't reprocessed.
    external_edges = _capture_external_incoming_edges(graph, changed_sources)

    for source_file in source_files_to_remove:
        graph.remove_source_file(source_file)

    for inventory in inventories:
        graph.remove_source_file(inventory.sourceFile)
        graph.ingest_inventory(inventory)

    _relink_external_edges(graph, external_edges)

    edges_after = set(graph.edges.keys())
    changed_edge_ids = tuple(edges_before.symmetric_difference(edges_after))

    graph.save(dependency_graph_path)
    return changed_edge_ids


def _capture_external_incoming_edges(graph: DependencyGraph, changed_sources: set[str]) -> list[tuple[str, str, str, str]]:
    normalized_changed = {_normalize(source) for source in changed_sources}
    captured: list[tuple[str, str, str, str]] = []
    for (source_id, target_id, edge_type) in graph.edges:
        target_node = graph.nodes.get(target_id)
        source_node = graph.nodes.get(source_id)
        if target_node is None or source_node is None:
            continue
        if _normalize(target_node.sourceFile) not in normalized_changed:
            continue
        if _normalize(source_node.sourceFile) in normalized_changed:
            continue  # both sides are being reprocessed; ingest_inventory recreates this edge naturally
        captured.append((source_id, target_node.name, target_node.symbolType or "", edge_type))
    return captured


def _relink_external_edges(graph: DependencyGraph, captured: list[tuple[str, str, str, str]]) -> None:
    for source_id, target_name, target_symbol_type, edge_type in captured:
        if source_id not in graph.nodes:
            continue
        candidates = [
            node
            for node in graph.nodes.values()
            if node.kind == "symbol" and node.symbolType == target_symbol_type and node.name == target_name
        ]
        if len(candidates) != 1:
            continue  # ambiguous or no longer exists; matches _resolve_symbol_target's own precedent
        try:
            graph.addEdge(source_id, candidates[0].id, edge_type)
        except ValueError:
            continue


def _normalize(path: str) -> str:
    return Path(path).as_posix().replace("\\", "/")
