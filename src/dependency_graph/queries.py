from __future__ import annotations

from typing import Iterable

from .models import DependencyEdge, DependencyNode, GraphQuery


def filter_edges(
    edges: Iterable[DependencyEdge],
    *,
    relation_type: str | None = None,
    source_ids: set[str] | None = None,
    target_ids: set[str] | None = None,
) -> list[DependencyEdge]:
    result: list[DependencyEdge] = []
    for edge in edges:
        if relation_type is not None and edge.type != relation_type:
            continue
        if source_ids is not None and edge.sourceId not in source_ids:
            continue
        if target_ids is not None and edge.targetId not in target_ids:
            continue
        result.append(edge)
    return result


def ordered_nodes(nodes: Iterable[DependencyNode]) -> list[DependencyNode]:
    return sorted(nodes, key=lambda node: (node.kind, node.name, node.id))


def query_to_dict(query: GraphQuery) -> dict[str, object]:
    return {
        "focusId": query.focusId,
        "direction": query.direction,
        "relationType": query.relationType,
        "depth": query.depth,
    }

