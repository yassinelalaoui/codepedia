from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from dependency_graph import DiagramExport

from . import links
from .class_diagram import ClassDiagramSelection
from .entry_point_diagram import SequenceDiagramSelection
from .sections import Section
from .use_case_diagram import UseCaseDiagramSelection


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


@dataclass(frozen=True, slots=True)
class SequenceDiagramSource:
    sourceText: str
    participantIds: tuple[str, ...] = ()
    stepCount: int = 0


def build_sequence_diagram_mermaid_source(selection: SequenceDiagramSelection) -> SequenceDiagramSource:
    """Render a SequenceDiagramSelection as Mermaid sequenceDiagram text.

    Each distinct symbol (the entry point plus every call step's callee) gets
    a short synthetic id (``p0``, ``p1``, ...) in first-appearance order - real
    symbol names are not guaranteed unique across modules, so are never used
    directly as Mermaid ids (same reasoning as
    ``build_class_diagram_mermaid_source``). A step's caller is always an
    already-registered participant: the traversal that produced ``selection``
    is pre-order, so a caller is either the entry point or a callee from an
    earlier step.
    """
    participant_id_by_symbol: dict[str, str] = {}
    lines: list[str] = ["sequenceDiagram"]

    def ensure_participant(symbol_id: str, label: str) -> str:
        synthetic_id = participant_id_by_symbol.get(symbol_id)
        if synthetic_id is None:
            synthetic_id = f"p{len(participant_id_by_symbol)}"
            participant_id_by_symbol[symbol_id] = synthetic_id
            lines.append(f"    participant {synthetic_id} as {_sanitize_sequence_diagram_label(label)}")
        return synthetic_id

    entry_point = selection.entryPoint
    ensure_participant(entry_point.symbolId, _entry_point_label(entry_point))

    message_lines: list[str] = []
    for step in selection.steps:
        caller_id = participant_id_by_symbol[step.callerSymbolId]
        callee_id = ensure_participant(step.calleeSymbolId, _call_step_label(step))
        message_lines.append(f"    {caller_id}->>{callee_id}: {_sanitize_sequence_diagram_label(step.calleeName)}()")
    lines.extend(message_lines)

    return SequenceDiagramSource(
        sourceText="\n".join(lines),
        participantIds=tuple(participant_id_by_symbol.values()),
        stepCount=len(selection.steps),
    )


def _entry_point_label(entry_point) -> str:
    if entry_point.className:
        return f"{entry_point.moduleName}.{entry_point.className}.{entry_point.name}"
    return f"{entry_point.moduleName}.{entry_point.name}"


def _call_step_label(step) -> str:
    if not step.calleeModuleName:
        return step.calleeName
    if step.calleeClassName:
        return f"{step.calleeModuleName}.{step.calleeClassName}.{step.calleeName}"
    return f"{step.calleeModuleName}.{step.calleeName}"


def _sanitize_sequence_diagram_label(name: str) -> str:
    return name.replace('"', "'").replace(";", ",")


@dataclass(frozen=True, slots=True)
class UseCaseDiagramSource:
    sourceText: str
    actorNodeIds: tuple[str, ...] = ()
    useCaseNodeIds: tuple[str, ...] = ()


def build_use_case_diagram_mermaid_source(selection: UseCaseDiagramSelection) -> UseCaseDiagramSource:
    """Render a UseCaseDiagramSelection as a Mermaid flowchart use-case-diagram workaround.

    Mermaid has no native UML use-case-diagram grammar, so this reuses the
    same convention already established for this project's own hand-authored
    documentation (``docs/diagrams/use-case-diagram.md``): an oval node per
    actor placed outside a system-boundary ``subgraph``, an oval node per use
    case placed inside it, and a plain ``-->`` arrow from each use case's
    actor to that use case - no ``include``/``extend``-labeled edges, since
    an entry point has no such relationship with another (Research
    Decision 2). Actor/use-case ids are short synthetic ids (``a0``/``u0``,
    ...), mirroring ``build_class_diagram_mermaid_source``'s ``c0`` convention
    - real labels are not guaranteed unique, so are never used as ids.
    """
    actor_node_id_by_kind: dict[str, str] = {}
    actor_lines: list[str] = []
    for index, actor in enumerate(selection.actors):
        synthetic_id = f"a{index}"
        actor_node_id_by_kind[actor.kind] = synthetic_id
        actor_lines.append(f'    {synthetic_id}(["{_escape_label(actor.label)}"])')

    use_case_node_ids: list[str] = []
    use_case_lines: list[str] = []
    arrow_lines: list[str] = []
    for index, use_case in enumerate(selection.useCases):
        synthetic_id = f"u{index}"
        use_case_node_ids.append(synthetic_id)
        use_case_lines.append(f'        {synthetic_id}(["{_escape_label(use_case.label)}"])')
        actor_id = actor_node_id_by_kind[use_case.actorKind]
        arrow_lines.append(f"    {actor_id} --> {synthetic_id}")

    lines: list[str] = ["flowchart LR", *actor_lines, "", '    subgraph sys["Use Cases"]', *use_case_lines, "    end", "", *arrow_lines]

    return UseCaseDiagramSource(
        sourceText="\n".join(lines),
        actorNodeIds=tuple(actor_node_id_by_kind.values()),
        useCaseNodeIds=tuple(use_case_node_ids),
    )


@dataclass(frozen=True, slots=True)
class SectionDiagramSource:
    sourceText: str
    nodeIdMap: dict[str, str] = field(default_factory=dict)
    clickTargets: tuple[MermaidClickTarget, ...] = ()
    omittedModuleCount: int = 0


# A section diagram is a map of one area, not of the repository: past this many
# nodes a Mermaid flowchart stops being readable, and the per-module dependency
# diagrams remain the place to see a single module's full neighbourhood.
MAX_SECTION_DIAGRAM_MODULES = 24


def build_section_diagram_mermaid_source(
    section: Section, *, section_output_path_html: str
) -> SectionDiagramSource:
    """Render one section's *internal* import structure as a Mermaid flowchart.

    Only edges between two members are drawn. A section page answers "how does
    this area hang together"; edges leaving the area are already listed as
    neighbouring sections, and drawing them would make every section diagram a
    partial repository diagram.

    When a section is larger than `MAX_SECTION_DIAGRAM_MODULES`, the most
    internally connected modules are kept - the ones that carry the area's
    shape - and the remainder is reported as `omittedModuleCount` rather than
    silently dropped.
    """
    included, omitted_count = _select_section_diagram_members(section)
    included_keys = {member.moduleKey for member in included}

    node_id_map: dict[str, str] = {}
    lines: list[str] = ["flowchart LR"]
    click_targets: list[MermaidClickTarget] = []

    for index, member in enumerate(included):
        synthetic_id = f"m{index}"
        node_id_map[member.moduleKey] = synthetic_id
        lines.append(f'    {synthetic_id}["{_escape_label(member.name)}"]')

        target_slug = links.page_slug(member.name, member.moduleKey)
        _, target_output_path_html = links.module_output_paths(target_slug)
        href = links.relative_output_link(
            from_output_path=section_output_path_html,
            to_output_path=target_output_path_html,
        )
        click_targets.append(
            MermaidClickTarget(
                nodeId=synthetic_id,
                targetPageId=links.module_page_id(member.moduleKey),
                href=href,
            )
        )

    for source_key, target_key in section.internalEdges:
        if source_key not in included_keys or target_key not in included_keys:
            continue
        lines.append(f"    {node_id_map[source_key]} ---|import| {node_id_map[target_key]}")

    for click_target in click_targets:
        lines.append(f'    click {click_target.nodeId} href "{click_target.href}" "_self"')

    return SectionDiagramSource(
        sourceText="\n".join(lines),
        nodeIdMap=node_id_map,
        clickTargets=tuple(click_targets),
        omittedModuleCount=omitted_count,
    )


def _select_section_diagram_members(section: Section):
    members = section.members
    if len(members) <= MAX_SECTION_DIAGRAM_MODULES:
        return members, 0

    degree: dict[str, int] = {member.moduleKey: 0 for member in members}
    for source_key, target_key in section.internalEdges:
        if source_key in degree:
            degree[source_key] += 1
        if target_key in degree:
            degree[target_key] += 1

    ranked = sorted(members, key=lambda member: (-degree[member.moduleKey], member.name, member.moduleKey))
    kept = ranked[:MAX_SECTION_DIAGRAM_MODULES]
    included = tuple(sorted(kept, key=lambda member: (member.name, member.moduleKey)))
    return included, len(members) - len(included)
