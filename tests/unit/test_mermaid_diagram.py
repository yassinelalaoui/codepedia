from __future__ import annotations

from dependency_graph import DependencyNode, DiagramExport

from doc_generator.class_diagram import ClassDiagramSelection, SelectedClass, SelectedMethod
from doc_generator.mermaid_diagram import build_class_diagram_mermaid_source, build_mermaid_source


def test_build_mermaid_source_handles_zero_edges():
    root_node = DependencyNode(
        id="file::isolated.py",
        kind="file",
        name="isolated",
        sourceFile="isolated.py",
        symbolType="module",
        metadata={},
    )
    diagram = DiagramExport(
        rootId=root_node.id,
        selectionType="file",
        nodes=(root_node,),
        edges=(),
    )

    def resolve_module(path):
        if path == "isolated.py":
            return ("module-key-isolated", "isolated")
        return None

    result = build_mermaid_source(
        diagram,
        diagram_page_id="diagram:module-key-isolated",
        diagram_output_path_html="diagrams/isolated.html",
        resolve_module=resolve_module,
    )

    assert result.sourceText.strip() != ""
    assert result.sourceText.startswith("flowchart LR")
    assert 'n0["isolated"]' in result.sourceText
    assert "-->" not in result.sourceText
    assert len(result.clickTargets) == 1
    assert result.clickTargets[0].targetPageId == "module:module-key-isolated"
    assert result.clickTargets[0].href.startswith("../modules/") and result.clickTargets[0].href.endswith(".html")


def test_build_mermaid_source_omits_click_for_unresolved_node():
    root_node = DependencyNode(
        id="file::a.py",
        kind="file",
        name="a",
        sourceFile="a.py",
        symbolType="module",
        metadata={},
    )
    removed_node = DependencyNode(
        id="file::removed.py",
        kind="file",
        name="removed",
        sourceFile="removed.py",
        symbolType="module",
        metadata={},
    )
    diagram = DiagramExport(
        rootId=root_node.id,
        selectionType="file",
        nodes=(root_node, removed_node),
        edges=(),
    )

    def resolve_module(path):
        if path == "a.py":
            return ("module-key-a", "a")
        return None

    result = build_mermaid_source(
        diagram,
        diagram_page_id="diagram:module-key-a",
        diagram_output_path_html="diagrams/a.html",
        resolve_module=resolve_module,
    )

    assert 'n0["a"]' in result.sourceText
    assert 'n1["removed"]' in result.sourceText
    assert len(result.clickTargets) == 1
    assert "click n1" not in result.sourceText
    assert "click n0" in result.sourceText


def test_build_class_diagram_mermaid_source_renders_classes_and_inheritance():
    selection = ClassDiagramSelection(
        includedClasses=(
            SelectedClass(classId="parent", name="Parent", methods=(SelectedMethod(name="run"),)),
            SelectedClass(classId="child", name="Child", methods=(SelectedMethod(name="run"), SelectedMethod(name="extra"))),
        ),
        inheritanceEdges=(("child", "parent"),),
        omittedClassCount=0,
    )

    result = build_class_diagram_mermaid_source(selection)

    assert result.sourceText.startswith("classDiagram")
    assert 'class c0["Parent"]' in result.sourceText
    assert 'class c1["Child"]' in result.sourceText
    assert "+run()" in result.sourceText
    assert "+extra()" in result.sourceText
    # Parent must come first: Mermaid's <|-- hollow arrowhead points at the
    # parent/base class (`Parent <|-- Child` means "Child inherits from
    # Parent"), matching this repo's own docs/diagrams/class-diagram.md.
    assert "c0 <|-- c1" in result.sourceText
    assert result.includedClassIds == ("parent", "child")
    assert result.omittedClassCount == 0
    assert "no attribute" not in result.sourceText.lower()


def test_build_class_diagram_mermaid_source_renders_class_with_no_methods():
    selection = ClassDiagramSelection(
        includedClasses=(SelectedClass(classId="lonely", name="Lonely", methods=()),),
        inheritanceEdges=(),
        omittedClassCount=0,
    )

    result = build_class_diagram_mermaid_source(selection)

    assert 'class c0["Lonely"]' in result.sourceText
    assert "{" not in result.sourceText
    assert "}" not in result.sourceText


def test_build_class_diagram_mermaid_source_drops_inheritance_edge_to_excluded_class():
    selection = ClassDiagramSelection(
        includedClasses=(SelectedClass(classId="child", name="Child", methods=()),),
        inheritanceEdges=(("child", "excluded-parent"),),
        omittedClassCount=1,
    )

    result = build_class_diagram_mermaid_source(selection)

    assert "<|--" not in result.sourceText


def test_build_class_diagram_mermaid_source_sanitizes_semicolons():
    selection = ClassDiagramSelection(
        includedClasses=(
            SelectedClass(classId="c1", name="Foo;Bar", methods=(SelectedMethod(name="do;It"),)),
        ),
        inheritanceEdges=(),
        omittedClassCount=0,
    )

    result = build_class_diagram_mermaid_source(selection)

    assert ";" not in result.sourceText
    assert 'class c0["Foo,Bar"]' in result.sourceText
    assert "+do,It()" in result.sourceText
