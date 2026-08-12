from __future__ import annotations

from dependency_graph import DependencyNode, DiagramExport

from doc_generator.mermaid_diagram import build_mermaid_source


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
