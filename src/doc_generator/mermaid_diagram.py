from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from dependency_graph import DiagramExport

from . import links
from .class_diagram import ClassDiagramSelection


@dataclass(frozen=True, slots=True)
class MermaidClickTarget:
    nodeId: str
    targetPageId: str
    href: str


@dataclass(frozen=True, slots=True)
class MermaidDiagramSource:
    diagramPageId: str
    sourceText: str
    nodeIdMap: dict[str, str] = field(default_factory=dict)
    clickTargets: tuple[MermaidClickTarget, ...] = ()


def build_mermaid_source(
    diagram: DiagramExport,
    *,
    diagram_page_id: str,
    diagram_output_path_html: str,
    resolve_module: Callable[[str | None], tuple[str, str] | None],
) -> MermaidDiagramSource:
    """Render a DiagramExport as Mermaid flowchart text.

    ``resolve_module`` maps a DependencyNode's ``sourceFile`` path to
    ``(module page key, module name)`` for the module that owns that file, or
    ``None`` if it no longer resolves to a current documentation page (e.g.,
    the file was removed since this diagram was last generated). A node that
    does not resolve still renders, just without a `click` directive.
    """
    node_id_map: dict[str, str] = {}
    lines: list[str] = ["flowchart LR"]
    click_targets: list[MermaidClickTarget] = []

    for index, node in enumerate(diagram.nodes):
        synthetic_id = f"n{index}"
        node_id_map[node.id] = synthetic_id
        lines.append(f'    {synthetic_id}["{_escape_label(node.name)}"]')

        resolved = resolve_module(node.sourceFile) if node.kind == "file" else None
        if resolved is None:
            continue
        module_key, module_name = resolved
        target_page_id = links.module_page_id(module_key)
        target_slug = links.page_slug(module_name, module_key)
        _, target_output_path_html = links.module_output_paths(target_slug)
        href = links.relative_output_link(
            from_output_path=diagram_output_path_html,
            to_output_path=target_output_path_html,
        )
        click_targets.append(MermaidClickTarget(nodeId=synthetic_id, targetPageId=target_page_id, href=href))

    for edge in diagram.edges:
        source_synthetic = node_id_map.get(edge.sourceId)
        target_synthetic = node_id_map.get(edge.targetId)
        if source_synthetic is None or target_synthetic is None:
            continue
        lines.append(f"    {source_synthetic} -->|{edge.type}| {target_synthetic}")

    for click_target in click_targets:
        lines.append(f'    click {click_target.nodeId} href "{click_target.href}" "_self"')

    return MermaidDiagramSource(
        diagramPageId=diagram_page_id,
        sourceText="\n".join(lines),
        nodeIdMap=node_id_map,
        clickTargets=tuple(click_targets),
    )


def _escape_label(name: str) -> str:
    return name.replace('"', "'")


@dataclass(frozen=True, slots=True)
class ClassDiagramSource:
    sourceText: str
    includedClassIds: tuple[str, ...] = ()
    omittedClassCount: int = 0


def build_class_diagram_mermaid_source(selection: ClassDiagramSelection) -> ClassDiagramSource:
    """Render a ClassDiagramSelection as Mermaid classDiagram text.

    Each included class gets a short synthetic id (``c0``, ``c1``, ...) as its
    Mermaid class identifier, with the real (sanitized) class name shown only
    as its display label - real class names are not guaranteed unique across
    modules, so using them directly as Mermaid ids would silently merge two
    unrelated same-named classes into one node.
    """
    node_id_map: dict[str, str] = {}
    lines: list[str] = ["classDiagram"]

    for index, selected_class in enumerate(selection.includedClasses):
        synthetic_id = f"c{index}"
        node_id_map[selected_class.classId] = synthetic_id
        label = _sanitize_class_diagram_label(selected_class.name)
        if selected_class.methods:
            lines.append(f'    class {synthetic_id}["{label}"] {{')
            for method in selected_class.methods:
                lines.append(f"        +{_sanitize_class_diagram_label(method.name)}()")
            lines.append("    }")
        else:
            lines.append(f'    class {synthetic_id}["{label}"]')

    for child_id, parent_id in selection.inheritanceEdges:
        child_synthetic = node_id_map.get(child_id)
        parent_synthetic = node_id_map.get(parent_id)
        if child_synthetic is None or parent_synthetic is None:
            continue
        # Mermaid's `<|--` hollow arrowhead points at the parent/base class,
        # so the parent is written first: `Parent <|-- Child` means "Child
        # inherits from Parent" (matches this repo's own docs/diagrams/
        # class-diagram.md, e.g. `Symbol <|-- ModuleSymbol`).
        lines.append(f"    {parent_synthetic} <|-- {child_synthetic}")

    return ClassDiagramSource(
        sourceText="\n".join(lines),
        includedClassIds=tuple(selected_class.classId for selected_class in selection.includedClasses),
        omittedClassCount=selection.omittedClassCount,
    )


def _sanitize_class_diagram_label(name: str) -> str:
    return name.replace('"', "'").replace(";", ",")
