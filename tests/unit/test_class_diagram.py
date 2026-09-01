from __future__ import annotations

from dependency_graph import DependencyGraph, DependencyNode
from repository_metadata.models import (
    ClassSymbol,
    FunctionSymbol,
)
from repository_metadata.models import DependencyGraph as MetadataDependencyGraph
from repository_metadata.models import (
    Repository,
    RepositoryBundle,
    SourceFile,
    SourceFileBundle,
)
from repository_metadata import ModuleSymbol

from doc_generator.class_diagram import select_major_classes


def _module_symbol() -> ModuleSymbol:
    return ModuleSymbol(
        id="module1",
        sourceFileId="file1",
        kind="module",
        name="mod",
        lineStart=1,
        lineEnd=100,
        filePath="mod.py",
    )


def _source_file() -> SourceFile:
    return SourceFile(
        id="file1",
        repositoryId="repo1",
        path="mod.py",
        language="python",
        contentHash="hash",
        lastModified="2026-08-17T00:00:00Z",
    )


def _class_symbol(class_id: str, name: str, methods: tuple[str, ...] = ()) -> ClassSymbol:
    return ClassSymbol(id=class_id, sourceFileId="file1", kind="class", name=name, lineStart=1, lineEnd=5, methods=methods)


def _method_symbol(method_id: str, name: str) -> FunctionSymbol:
    return FunctionSymbol(id=method_id, sourceFileId="file1", kind="function", name=name, lineStart=1, lineEnd=2, owner="class")


def _bundle(classes: tuple[ClassSymbol, ...], functions: tuple[FunctionSymbol, ...] = ()) -> RepositoryBundle:
    file_bundle = SourceFileBundle(file=_source_file(), module=_module_symbol(), classes=classes, functions=functions)
    return RepositoryBundle(
        repository=Repository(id="repo1", rootPath="/repo"),
        files=(file_bundle,),
        graph=MetadataDependencyGraph(id="g1", repositoryId="repo1"),
    )


def _add_class_node(graph: DependencyGraph, class_id: str, name: str) -> DependencyNode:
    return graph.add_node(DependencyNode(id=class_id, kind="symbol", name=name, sourceFile="mod.py", symbolType="class"))


def _add_noise_edges(graph: DependencyGraph, class_id: str, count: int) -> None:
    for index in range(count):
        leaf_id = f"leaf::{class_id}::{index}"
        graph.add_node(DependencyNode(id=leaf_id, kind="symbol", name=leaf_id, sourceFile="mod.py", symbolType="function"))
        graph.addEdge(class_id, leaf_id, "call")


def test_select_major_classes_returns_empty_selection_for_zero_classes():
    bundle = _bundle(classes=())
    graph = DependencyGraph(id="g1", sourceFile="repo")

    result = select_major_classes(bundle, graph)

    assert result.includedClasses == ()
    assert result.inheritanceEdges == ()
    assert result.omittedClassCount == 0


def test_select_major_classes_includes_a_class_with_no_methods():
    classes = (_class_symbol("c1", "Lonely", methods=()),)
    bundle = _bundle(classes=classes)
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_class_node(graph, "c1", "Lonely")

    result = select_major_classes(bundle, graph)

    assert len(result.includedClasses) == 1
    assert result.includedClasses[0].classId == "c1"
    assert result.includedClasses[0].methods == ()


def test_select_major_classes_prioritizes_inheritance_participants_over_higher_edge_count_ties():
    """45 candidates: a Parent/Child inheritance pair (edge count 1 each) plus
    43 non-participant classes with distinct edge counts 1..43. The cap (40)
    is tight enough that the participants must displace a same-or-higher-edge-
    count non-participant to prove inheritance participation, not just edge
    count, decides inclusion."""
    classes = [
        _class_symbol("parent", "Parent"),
        _class_symbol("child", "Child"),
    ]
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_class_node(graph, "parent", "Parent")
    _add_class_node(graph, "child", "Child")
    graph.addEdge("child", "parent", "inheritance")

    for index in range(1, 44):
        class_id = f"noise{index:02d}"
        classes.append(_class_symbol(class_id, class_id))
        _add_class_node(graph, class_id, class_id)
        _add_noise_edges(graph, class_id, index)

    bundle = _bundle(classes=tuple(classes))

    result = select_major_classes(bundle, graph)

    included_ids = {selected.classId for selected in result.includedClasses}
    assert len(result.includedClasses) == 40
    assert result.omittedClassCount == 5
    assert "parent" in included_ids
    assert "child" in included_ids
    # The 5 lowest-edge-count non-participants (noise01..noise05, edge count
    # 1..5) must be excluded in favor of the two participants.
    for index in range(1, 6):
        assert f"noise{index:02d}" not in included_ids
    for index in range(6, 44):
        assert f"noise{index:02d}" in included_ids
    assert (("child", "parent")) in result.inheritanceEdges


def test_select_major_classes_tie_break_is_edge_count_then_name_then_id():
    """41 non-participant classes all tied at edge count 5; only the cap (40)
    fit, so the deterministic tie-break (name ascending) must decide which
    one is excluded."""
    classes = []
    graph = DependencyGraph(id="g1", sourceFile="repo")
    for index in range(40):
        class_id = f"a{index:02d}"
        name = f"A{index:02d}"
        classes.append(_class_symbol(class_id, name))
        _add_class_node(graph, class_id, name)
        _add_noise_edges(graph, class_id, 5)

    classes.append(_class_symbol("z-extra", "Z-extra"))
    _add_class_node(graph, "z-extra", "Z-extra")
    _add_noise_edges(graph, "z-extra", 5)

    bundle = _bundle(classes=tuple(classes))

    result = select_major_classes(bundle, graph)

    included_ids = {selected.classId for selected in result.includedClasses}
    assert len(result.includedClasses) == 40
    assert result.omittedClassCount == 1
    assert "z-extra" not in included_ids
    for index in range(40):
        assert f"a{index:02d}" in included_ids


def test_select_major_classes_skips_documentation_headings():
    # A `##` in a README is stored as a ClassSymbol so prose reuses the wiki
    # pipeline. Left in, headings compete with the repository's real classes for
    # this diagram's 40 slots - and on a documentation-heavy repository they win.
    prose_module = ModuleSymbol(
        id="module2", sourceFileId="file2", kind="module", name="README", lineStart=1, lineEnd=10, filePath="README.md"
    )
    prose_file = SourceFile(
        id="file2",
        repositoryId="repo1",
        path="README.md",
        language="markdown",
        contentHash="hash2",
        lastModified="2026-08-17T00:00:00Z",
    )
    code_bundle = SourceFileBundle(
        file=_source_file(), module=_module_symbol(), classes=(_class_symbol("c1", "RealClass"),), functions=()
    )
    prose_bundle = SourceFileBundle(
        file=prose_file,
        module=prose_module,
        classes=(ClassSymbol(id="h1", sourceFileId="file2", kind="class", name="Installation", lineStart=1, lineEnd=5),),
        functions=(),
    )
    bundle = RepositoryBundle(
        repository=Repository(id="repo1", rootPath="/repo"),
        files=(code_bundle, prose_bundle),
        graph=MetadataDependencyGraph(id="g1", repositoryId="repo1"),
    )
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_class_node(graph, "c1", "RealClass")
    _add_class_node(graph, "h1", "Installation")

    result = select_major_classes(bundle, graph)

    assert [selected.classId for selected in result.includedClasses] == ["c1"]
    assert result.omittedClassCount == 0, "a heading is not an omitted class, it is not a class"
