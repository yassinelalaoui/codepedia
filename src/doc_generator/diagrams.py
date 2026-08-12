from __future__ import annotations

from dependency_graph import DependencyGraph, DiagramExport
from repository_metadata import ModuleSymbol


def build_module_diagram(graph: DependencyGraph, module: ModuleSymbol) -> DiagramExport:
    return graph.exportDiagram(module.filePath, selectionType="file")
