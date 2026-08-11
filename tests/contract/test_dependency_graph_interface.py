from dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    GraphQuery,
    assemble_dependency_graph,
    build_diagram_export,
)


def test_dependency_graph_public_api_is_available():
    graph = DependencyGraph(id="graph_1", sourceFile="repo")
    assert graph.id == "graph_1"
    assert graph.sourceFile == "repo"
    assert hasattr(graph, "addEdge")
    assert hasattr(graph, "exportDiagram")


def test_dependency_graph_supports_core_public_types():
    node = DependencyNode(id="file::alpha", kind="file", name="alpha", sourceFile="alpha.py")
    edge = DependencyEdge(sourceId="file::alpha", targetId="file::beta", type="import")
    query = GraphQuery(focusId="file::alpha")
    export = build_diagram_export(root_id="file::alpha", selection_type="file", nodes=[], edges=[])
    graph = assemble_dependency_graph([])

    assert node.kind == "file"
    assert edge.type == "import"
    assert query.direction == "outgoing"
    assert export.rootId == "file::alpha"
    assert graph.id.startswith("graph_")
