from __future__ import annotations

from .models import DiagramExport, DependencyEdge, DependencyNode, SelectionType


def build_diagram_export(
    *,
    root_id: str,
    selection_type: SelectionType,
    nodes: list[DependencyNode],
    edges: list[DependencyEdge],
) -> DiagramExport:
    return DiagramExport(
        rootId=root_id,
        selectionType=selection_type,
        nodes=tuple(nodes),
        edges=tuple(edges),
    )
