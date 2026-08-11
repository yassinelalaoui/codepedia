from pathlib import Path

import sqlite3

from dependency_graph import DependencyEdge, DependencyGraph, DependencyNode
from parser_engine import SourceFile, extract_symbols


def _fixture_inventories() -> list:
    fixture_root = Path("tests/integration/fixtures/dependency-graph")
    return [
        extract_symbols(SourceFile(path=fixture_root / "alpha.py", language="python")),
        extract_symbols(SourceFile(path=fixture_root / "beta.py", language="python")),
        extract_symbols(SourceFile(path=fixture_root / "gamma.py", language="python")),
    ]


def test_add_edge_deduplicates_identical_relations():
    graph = DependencyGraph(id="graph_1", sourceFile="repo")
    left = DependencyNode(id="file::alpha", kind="file", name="alpha", sourceFile="alpha.py")
    right = DependencyNode(id="file::beta", kind="file", name="beta", sourceFile="beta.py")
    graph.add_node(left)
    graph.add_node(right)

    first = graph.addEdge(left, right, "import")
    second = graph.addEdge("file::alpha", "file::beta", "import")

    assert first is second
    assert len(graph.edges) == 1


def test_build_from_inventories_creates_file_symbol_and_relation_nodes():
    graph = DependencyGraph.build_from_inventories(_fixture_inventories())

    assert "file::tests/integration/fixtures/dependency-graph/alpha.py" in graph.nodes
    assert any(node.kind == "symbol" and node.name == "Child" for node in graph.nodes.values())
    assert any(edge.type == "import" for edge in graph.edges.values())
    assert any(edge.type == "call" for edge in graph.edges.values())
    assert any(edge.type == "inheritance" for edge in graph.edges.values())


def test_query_helpers_return_direct_dependencies():
    graph = DependencyGraph.build_from_inventories(_fixture_inventories())
    beta_file = next(node for node in graph.nodes.values() if node.kind == "file" and node.name == "beta")
    alpha_file = next(node for node in graph.nodes.values() if node.kind == "file" and node.name == "alpha")
    helper = next(node for node in graph.nodes.values() if node.kind == "symbol" and node.name == "helper")

    assert {node.name for node in graph.files_importing(beta_file)} == {"alpha"}
    assert {node.name for node in graph.dependencies(alpha_file, relation_type="import")} == {"beta", "gamma"}
    assert {node.name for node in graph.functions_calling(helper)} == {"inner"}


def test_export_diagram_returns_connected_slice():
    graph = DependencyGraph.build_from_inventories(_fixture_inventories())
    beta_file = next(node for node in graph.nodes.values() if node.kind == "file" and node.name == "beta")

    export = graph.exportDiagram(beta_file, selectionType="file")

    assert export.rootId == beta_file.id
    assert export.selectionType == "file"
    assert any(node.name == "alpha" for node in export.nodes)
    assert any(edge.type == "import" for edge in export.edges)


def test_save_overwrites_existing_snapshot_without_duplicate_rows(tmp_path):
    graph = DependencyGraph.build_from_inventories(_fixture_inventories())
    db_path = tmp_path / "graph.sqlite"

    first = graph.save(db_path)
    second = graph.save(db_path)

    with sqlite3.connect(db_path) as connection:
        graph_count = connection.execute("SELECT COUNT(*) FROM graphs").fetchone()[0]
        node_count = connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    assert first.nodeCount == second.nodeCount == len(graph.nodes)
    assert first.edgeCount == second.edgeCount == len(graph.edges)
    assert graph_count == 1
    assert node_count == len(graph.nodes)
    assert edge_count == len(graph.edges)


def test_export_diagram_returns_empty_export_for_missing_root():
    graph = DependencyGraph.build_from_inventories(_fixture_inventories())

    export = graph.exportDiagram("missing-root", selectionType="symbol")

    assert export.rootId == "missing-root"
    assert export.selectionType == "symbol"
    assert export.nodes == ()
    assert export.edges == ()
