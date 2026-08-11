from pathlib import Path

from dependency_graph import DependencyGraph
from parser_engine import SourceFile, extract_symbols


def _inventories() -> list:
    fixture_root = Path("tests/integration/fixtures/dependency-graph")
    return [
        extract_symbols(SourceFile(path=fixture_root / "alpha.py", language="python")),
        extract_symbols(SourceFile(path=fixture_root / "beta.py", language="python")),
        extract_symbols(SourceFile(path=fixture_root / "gamma.py", language="python")),
    ]


def _names(nodes):
    return [node.name for node in nodes]


def test_dependency_graph_finds_exact_direct_dependencies_and_dependents():
    graph = DependencyGraph.build_from_inventories(_inventories())
    alpha_file = next(node for node in graph.nodes.values() if node.kind == "file" and node.name == "alpha")
    beta_file = next(node for node in graph.nodes.values() if node.kind == "file" and node.name == "beta")
    helper = next(node for node in graph.nodes.values() if node.kind == "symbol" and node.name == "helper")
    base = next(node for node in graph.nodes.values() if node.kind == "symbol" and node.name == "BaseThing")

    assert set(_names(graph.dependencies(alpha_file, relation_type="import"))) == {"beta", "gamma"}
    assert set(_names(graph.files_importing(beta_file))) == {"alpha"}
    assert set(_names(graph.functions_calling(helper))) == {"inner"}
    assert set(_names(graph.classes_inheriting(base))) == {"Child"}
    assert set(_names(graph.functions_called_by(next(node for node in graph.nodes.values() if node.kind == "symbol" and node.name == "alpha_entry")))) == {"inner", "shared_value"}


def test_dependency_graph_round_trips_through_sqlite(tmp_path):
    graph = DependencyGraph.build_from_inventories(_inventories())
    db_path = tmp_path / "graph.sqlite"

    saved = graph.save(db_path)
    reloaded = DependencyGraph.load(db_path, graph_id=saved.graphId)

    alpha_file = next(node for node in graph.nodes.values() if node.kind == "file" and node.name == "alpha")
    reload_alpha = next(node for node in reloaded.nodes.values() if node.kind == "file" and node.name == "alpha")

    assert saved.nodeCount == len(graph.nodes)
    assert saved.edgeCount == len(graph.edges)
    assert set(_names(reloaded.dependencies(reload_alpha, relation_type="import"))) == {"beta", "gamma"}
    assert set(_names(reloaded.files_importing(next(node for node in reloaded.nodes.values() if node.kind == "file" and node.name == "beta")))) == {"alpha"}
    assert set(_names(reloaded.dependencies(reload_alpha, relation_type="import"))) == set(_names(graph.dependencies(alpha_file, relation_type="import")))


def test_dependency_graph_exports_filtered_slice_without_unrelated_nodes():
    graph = DependencyGraph.build_from_inventories(_inventories())
    gamma_file = next(node for node in graph.nodes.values() if node.kind == "file" and node.name == "gamma")

    export = graph.exportDiagram(gamma_file, selectionType="file")

    exported_names = {node.name for node in export.nodes}
    assert "gamma" in exported_names
    assert "alpha" in exported_names or "beta" in exported_names
    assert all(edge.sourceId in {node.id for node in export.nodes} and edge.targetId in {node.id for node in export.nodes} for edge in export.edges)
