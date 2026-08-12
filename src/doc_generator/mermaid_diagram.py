from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from dependency_graph import DiagramExport

from . import links


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
