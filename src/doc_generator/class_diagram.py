from __future__ import annotations

from dataclasses import dataclass

from dependency_graph import DependencyGraph
from repository_metadata.models import RepositoryBundle

MAX_INCLUDED_CLASSES = 40


@dataclass(frozen=True, slots=True)
class SelectedMethod:
    name: str


@dataclass(frozen=True, slots=True)
class SelectedClass:
    classId: str
    name: str
    methods: tuple[SelectedMethod, ...] = ()


@dataclass(frozen=True, slots=True)
class ClassDiagramSelection:
    includedClasses: tuple[SelectedClass, ...] = ()
    inheritanceEdges: tuple[tuple[str, str], ...] = ()
    omittedClassCount: int = 0


def select_major_classes(bundle: RepositoryBundle, graph: DependencyGraph) -> ClassDiagramSelection:
    """Select the repository's structurally major classes for the class diagram.

    A class is included if it participates in an inheritance relationship, or
    if it ranks among the remaining classes with the most incoming/outgoing
    dependency-graph edges (all edge types), capped at MAX_INCLUDED_CLASSES
    total, per research.md Decision 2.
    """
    candidates = _gather_candidates(bundle)
    total_class_count = len(candidates)
    if total_class_count == 0:
        return ClassDiagramSelection()

    participant_ids = {
        candidate.classId for candidate in candidates if _is_inheritance_participant(graph, candidate.classId)
    }
    participants = [candidate for candidate in candidates if candidate.classId in participant_ids]
    non_participants = [candidate for candidate in candidates if candidate.classId not in participant_ids]

    def by_edge_count_desc(candidate: SelectedClass) -> tuple[int, str, str]:
        return (-_edge_count(graph, candidate.classId), candidate.name, candidate.classId)

    if len(participants) <= MAX_INCLUDED_CLASSES:
        remaining_slots = MAX_INCLUDED_CLASSES - len(participants)
        filler = sorted(non_participants, key=by_edge_count_desc)[:remaining_slots]
        included = participants + filler
    else:
        included = sorted(participants, key=by_edge_count_desc)[:MAX_INCLUDED_CLASSES]

    included_sorted = tuple(sorted(included, key=lambda candidate: (candidate.name, candidate.classId)))
    included_ids = {candidate.classId for candidate in included_sorted}

    inheritance_edges: list[tuple[str, str]] = []
    for candidate in included_sorted:
        for parent_node in graph.dependencies(candidate.classId, relation_type="inheritance"):
            if parent_node.id in included_ids:
                inheritance_edges.append((candidate.classId, parent_node.id))

    return ClassDiagramSelection(
        includedClasses=included_sorted,
        inheritanceEdges=tuple(inheritance_edges),
        omittedClassCount=total_class_count - len(included_sorted),
    )


def _gather_candidates(bundle: RepositoryBundle) -> list[SelectedClass]:
    candidates: list[SelectedClass] = []
    for file_bundle in bundle.files:
        functions_by_id = {function.id: function for function in file_bundle.functions}
        for class_symbol in file_bundle.classes:
            methods = tuple(
                SelectedMethod(name=functions_by_id[method_id].name)
                for method_id in class_symbol.methods
                if method_id in functions_by_id
            )
            candidates.append(SelectedClass(classId=class_symbol.id, name=class_symbol.name, methods=methods))
    return candidates


def _is_inheritance_participant(graph: DependencyGraph, class_id: str) -> bool:
    return bool(
        graph.dependencies(class_id, relation_type="inheritance")
        or graph.dependents(class_id, relation_type="inheritance")
    )


def _edge_count(graph: DependencyGraph, class_id: str) -> int:
    return len(graph.dependencies(class_id)) + len(graph.dependents(class_id))
