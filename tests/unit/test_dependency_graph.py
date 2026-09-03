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


def _package_repo(tmp_path: Path) -> list:
    """Two packages that each contain a `models.py`, plus a stdlib import.

    The shape that broke import resolution: a bare module name that is not
    unique, reached by a relative import from inside each package.
    """
    for package in ("alpha_pkg", "beta_pkg"):
        directory = tmp_path / package
        directory.mkdir()
        (directory / "__init__.py").write_text("", encoding="utf-8")
        (directory / "models.py").write_text(
            f'"""{package} models."""\n\n\nclass Thing:\n    """A thing."""\n',
            encoding="utf-8",
        )
        (directory / "service.py").write_text(
            "from __future__ import annotations\n\n"
            "from .models import Thing\n\n\n"
            "def run() -> Thing:\n"
            "    return Thing()\n",
            encoding="utf-8",
        )
    paths = sorted(tmp_path.rglob("*.py"))
    return [extract_symbols(SourceFile(path=path, language="python")) for path in paths]


def _file_node(graph, relative: str):
    return next(
        node
        for node in graph.nodes.values()
        if node.kind == "file" and node.sourceFile and node.sourceFile.replace("\\", "/").endswith(relative)
    )


def test_relative_import_resolves_inside_its_own_package(tmp_path):
    """`from .models import Thing` must reach the sibling, not a namesake.

    Before this was fixed, `_resolve_file_candidate` matched on the last path
    segment and returned the first node it happened to iterate over, so every
    `.models` in a repository resolved to whichever `models.py` was inserted
    first. On the real repository that gave one `models.py` 158 import edges and
    left the other ten with none.
    """
    graph = DependencyGraph.build_from_inventories(_package_repo(tmp_path))

    for package in ("alpha_pkg", "beta_pkg"):
        service = _file_node(graph, f"{package}/service.py")
        imported = [
            node
            for node in graph.dependencies(service.sourceFile, relation_type="import")
            if node.name == "models"
        ]
        assert len(imported) == 1, f"{package}/service.py should import exactly one `models`"
        assert imported[0].sourceFile.replace("\\", "/").endswith(f"{package}/models.py")


def test_each_same_named_module_keeps_its_own_importers(tmp_path):
    """Neither `models.py` may absorb the other's incoming edges."""
    graph = DependencyGraph.build_from_inventories(_package_repo(tmp_path))

    for package in ("alpha_pkg", "beta_pkg"):
        models = _file_node(graph, f"{package}/models.py")
        importers = {node.sourceFile.replace("\\", "/") for node in graph.files_importing(models)}
        assert any(path.endswith(f"{package}/service.py") for path in importers)
        other = "beta_pkg" if package == "alpha_pkg" else "alpha_pkg"
        assert not any(path.endswith(f"{other}/service.py") for path in importers)


def test_an_unresolved_import_claims_no_source_file(tmp_path):
    """`__future__` does not live in whichever file mentioned it first.

    The node is created once and reused by every later importer, so a
    non-empty `sourceFile` here made every module writing
    `from __future__ import annotations` look like an importer of that one file.
    Measured on the real repository: degree 131 of 139, against a true degree
    of 4.
    """
    graph = DependencyGraph.build_from_inventories(_package_repo(tmp_path))

    external = [
        node
        for node in graph.nodes.values()
        if node.kind == "file" and node.metadata.get("unresolved")
    ]
    assert external, "the stdlib import should have produced an external node"
    assert all(node.sourceFile == "" for node in external)


def test_an_ambiguous_bare_import_stays_external(tmp_path):
    """A name several files carry resolves to none of them, not to a guess."""
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    for package in ("one", "two"):
        (tmp_path / package / "shared.py").write_text('"""Shared."""\n', encoding="utf-8")
    (tmp_path / "caller.py").write_text(
        '"""Caller."""\n\nimport shared\n', encoding="utf-8"
    )
    inventories = [
        extract_symbols(SourceFile(path=path, language="python"))
        for path in sorted(tmp_path.rglob("*.py"))
    ]
    graph = DependencyGraph.build_from_inventories(inventories)

    caller = _file_node(graph, "caller.py")
    resolved = [
        node
        for node in graph.dependencies(caller.sourceFile, relation_type="import")
        if node.name == "shared" and not node.metadata.get("unresolved")
    ]
    assert resolved == [], "an ambiguous bare import must not pick one arbitrarily"


def test_an_unambiguous_bare_import_still_resolves(tmp_path):
    """The flat-repository case must keep working - it is the common one."""
    (tmp_path / "only.py").write_text('"""Only."""\n', encoding="utf-8")
    (tmp_path / "caller.py").write_text('"""Caller."""\n\nimport only\n', encoding="utf-8")
    inventories = [
        extract_symbols(SourceFile(path=path, language="python"))
        for path in sorted(tmp_path.rglob("*.py"))
    ]
    graph = DependencyGraph.build_from_inventories(inventories)

    caller = _file_node(graph, "caller.py")
    resolved = [
        node
        for node in graph.dependencies(caller.sourceFile, relation_type="import")
        if node.name == "only"
    ]
    assert len(resolved) == 1
    assert resolved[0].sourceFile.replace("\\", "/").endswith("only.py")
