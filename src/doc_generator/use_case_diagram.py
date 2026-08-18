from __future__ import annotations

from dataclasses import dataclass

from dependency_graph import DependencyGraph
from repository_metadata.models import RepositoryBundle

from .entry_point_diagram import EntryPoint, EntryPointKind, identify_entry_points

_ACTOR_LABELS: dict[EntryPointKind, str] = {
    "cli-command": "CLI",
    "api-route": "API",
    "function": "External Caller",
}
_ACTOR_KIND_ORDER: tuple[EntryPointKind, ...] = ("cli-command", "api-route", "function")


@dataclass(frozen=True, slots=True)
class Actor:
    kind: EntryPointKind
    label: str


@dataclass(frozen=True, slots=True)
class UseCase:
    entryPointStableKey: str
    label: str
    actorKind: EntryPointKind


@dataclass(frozen=True, slots=True)
class UseCaseDiagramSelection:
    actors: tuple[Actor, ...] = ()
    useCases: tuple[UseCase, ...] = ()


def select_use_cases(bundle: RepositoryBundle, graph: DependencyGraph) -> UseCaseDiagramSelection:
    """Select the actors and use cases for the repository's use-case diagram.

    Reuses 022's ``identify_entry_points`` unmodified (Research Decision 1) -
    this module introduces no new entry-point detection. Each identified
    entry point becomes its own use case; each distinct ``EntryPointKind``
    present becomes one shared actor, in fixed canonical order (CLI, API,
    generic - Research Decision 3), never one actor per individual entry
    point.
    """
    entry_points = identify_entry_points(bundle, graph)
    if not entry_points:
        return UseCaseDiagramSelection()

    use_cases = tuple(
        UseCase(
            entryPointStableKey=entry_point.stableKey,
            label=_use_case_label(entry_point),
            actorKind=entry_point.kind,
        )
        for entry_point in entry_points
    )
    present_kinds = {entry_point.kind for entry_point in entry_points}
    actors = tuple(
        Actor(kind=kind, label=_ACTOR_LABELS[kind]) for kind in _ACTOR_KIND_ORDER if kind in present_kinds
    )
    return UseCaseDiagramSelection(actors=actors, useCases=use_cases)


def _use_case_label(entry_point: EntryPoint) -> str:
    if entry_point.className:
        return f"{entry_point.moduleName}.{entry_point.className}.{entry_point.name}"
    return f"{entry_point.moduleName}.{entry_point.name}"
