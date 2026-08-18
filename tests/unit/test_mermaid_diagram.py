from __future__ import annotations

from dependency_graph import DependencyNode, DiagramExport

from doc_generator.class_diagram import ClassDiagramSelection, SelectedClass, SelectedMethod
from doc_generator.entry_point_diagram import CallStep, EntryPoint, SequenceDiagramSelection
from doc_generator.mermaid_diagram import (
    build_class_diagram_mermaid_source,
    build_mermaid_source,
    build_sequence_diagram_mermaid_source,
    build_use_case_diagram_mermaid_source,
)
from doc_generator.use_case_diagram import Actor, UseCase, UseCaseDiagramSelection


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


def _entry_point(name: str = "entry", class_name: str | None = None) -> EntryPoint:
    return EntryPoint(
        symbolId="ep1",
        stableKey=f"file1::module::{name}",
        name=name,
        moduleKey="file1",
        moduleName="mod",
        className=class_name,
        kind="function",
    )


def test_build_sequence_diagram_mermaid_source_renders_participants_and_messages_in_order():
    entry_point = _entry_point()
    steps = (
        CallStep(
            depth=1,
            callerSymbolId="ep1",
            calleeSymbolId="c1",
            calleeName="process",
            calleeModuleKey="file2",
            calleeModuleName="service",
            calleeClassName=None,
            order=0,
        ),
        CallStep(
            depth=2,
            callerSymbolId="c1",
            calleeSymbolId="c2",
            calleeName="save",
            calleeModuleKey="file3",
            calleeModuleName="repository",
            calleeClassName=None,
            order=1,
        ),
    )
    selection = SequenceDiagramSelection(entryPoint=entry_point, steps=steps, truncatedAtMaxDepth=False)

    result = build_sequence_diagram_mermaid_source(selection)

    assert result.sourceText.startswith("sequenceDiagram")
    assert result.participantIds == ("p0", "p1", "p2")
    assert "participant p0 as mod.entry" in result.sourceText
    assert "participant p1 as service.process" in result.sourceText
    assert "participant p2 as repository.save" in result.sourceText
    assert "p0->>p1: process()" in result.sourceText
    assert "p1->>p2: save()" in result.sourceText
    assert result.stepCount == 2


def test_build_sequence_diagram_mermaid_source_zero_steps_renders_minimal_diagram():
    selection = SequenceDiagramSelection(entryPoint=_entry_point("noop"), steps=(), truncatedAtMaxDepth=False)

    result = build_sequence_diagram_mermaid_source(selection)

    assert result.sourceText.startswith("sequenceDiagram")
    assert result.sourceText.count("participant ") == 1
    assert "->>" not in result.sourceText
    assert result.stepCount == 0


def test_build_sequence_diagram_mermaid_source_sanitizes_semicolons_and_quotes():
    entry_point = _entry_point('Foo;Bar"Baz')
    step = CallStep(
        depth=1,
        callerSymbolId="ep1",
        calleeSymbolId="c1",
        calleeName='do;It"Now',
        calleeModuleKey=None,
        calleeModuleName=None,
        calleeClassName=None,
        order=0,
    )
    selection = SequenceDiagramSelection(entryPoint=entry_point, steps=(step,), truncatedAtMaxDepth=False)

    result = build_sequence_diagram_mermaid_source(selection)

    assert ";" not in result.sourceText
    assert '"' not in result.sourceText


def test_build_use_case_diagram_mermaid_source_renders_actors_and_use_cases_in_order():
    selection = UseCaseDiagramSelection(
        actors=(
            Actor(kind="cli-command", label="CLI"),
            Actor(kind="api-route", label="API"),
        ),
        useCases=(
            UseCase(entryPointStableKey="key1", label="cli.run_index", actorKind="cli-command"),
            UseCase(entryPointStableKey="key2", label="api.get_sessions", actorKind="api-route"),
        ),
    )

    result = build_use_case_diagram_mermaid_source(selection)

    assert result.sourceText.startswith("flowchart LR")
    assert result.actorNodeIds == ("a0", "a1")
    assert result.useCaseNodeIds == ("u0", "u1")
    assert 'a0(["CLI"])' in result.sourceText
    assert 'a1(["API"])' in result.sourceText
    assert 'u0(["cli.run_index"])' in result.sourceText
    assert 'u1(["api.get_sessions"])' in result.sourceText
    assert "a0 --> u0" in result.sourceText
    assert "a1 --> u1" in result.sourceText


def test_build_use_case_diagram_mermaid_source_multiple_use_cases_share_one_actor():
    selection = UseCaseDiagramSelection(
        actors=(Actor(kind="cli-command", label="CLI"),),
        useCases=(
            UseCase(entryPointStableKey="key1", label="cli.run_a", actorKind="cli-command"),
            UseCase(entryPointStableKey="key2", label="cli.run_b", actorKind="cli-command"),
        ),
    )

    result = build_use_case_diagram_mermaid_source(selection)

    assert result.actorNodeIds == ("a0",)
    assert "a0 --> u0" in result.sourceText
    assert "a0 --> u1" in result.sourceText


def test_build_use_case_diagram_mermaid_source_sanitizes_quotes():
    selection = UseCaseDiagramSelection(
        actors=(Actor(kind="function", label='External"Caller'),),
        useCases=(UseCase(entryPointStableKey="key1", label='mod.do"Thing', actorKind="function"),),
    )

    result = build_use_case_diagram_mermaid_source(selection)

    assert '"Caller' not in result.sourceText
    assert '"Thing' not in result.sourceText
