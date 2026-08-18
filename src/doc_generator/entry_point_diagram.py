from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Literal

from dependency_graph import DependencyGraph
from repository_metadata.models import FunctionSymbol, RepositoryBundle

MAX_CALL_DEPTH = 6

_CLI_DECORATOR_PATTERN = re.compile(r"\.(command|callback)\(")
_API_DECORATOR_PATTERN = re.compile(r"\.(get|post|put|delete|patch)\(")

EntryPointKind = Literal["cli-command", "api-route", "function"]


@dataclass(frozen=True, slots=True)
class EntryPoint:
    symbolId: str
    stableKey: str
    name: str
    moduleKey: str
    moduleName: str
    className: str | None
    kind: EntryPointKind


@dataclass(frozen=True, slots=True)
class CallStep:
    depth: int
    callerSymbolId: str
    calleeSymbolId: str
    calleeName: str
    calleeModuleKey: str | None
    calleeModuleName: str | None
    calleeClassName: str | None
    order: int


@dataclass(frozen=True, slots=True)
class SequenceDiagramSelection:
    entryPoint: EntryPoint
    steps: tuple[CallStep, ...] = ()
    truncatedAtMaxDepth: bool = False


def build_method_class_index(bundle: RepositoryBundle) -> dict[str, str]:
    """Map every method symbol id to its owning class's name (Research Decision 5)."""
    index: dict[str, str] = {}
    for file_bundle in bundle.files:
        for class_symbol in file_bundle.classes:
            for method_id in class_symbol.methods:
                index[method_id] = class_symbol.name
    return index


def identify_entry_points(bundle: RepositoryBundle, graph: DependencyGraph) -> tuple[EntryPoint, ...]:
    """Identify every CLI command, API route handler, or uncalled public function/method.

    Candidate pool: every non-``_``-prefixed, non-nested FunctionSymbol across
    ``bundle.files[*].functions`` (Research Decision 1). A candidate qualifies
    as a CLI command / API route regardless of callers (FR-002) when its
    captured decorator text matches the relevant framework pattern (Research
    Decision 3); otherwise it qualifies as a plain function when nothing else
    in the repository calls it (Research Decision 2).
    """
    method_class_index = build_method_class_index(bundle)
    nested_ids = {
        nested_id
        for file_bundle in bundle.files
        for function in file_bundle.functions
        for nested_id in function.nestedSymbols
    }

    candidates: list[EntryPoint] = []
    for file_bundle in bundle.files:
        module_key = file_bundle.module.sourceFileId
        module_name = file_bundle.module.name
        for function in file_bundle.functions:
            if function.name.startswith("_") or function.id in nested_ids:
                continue
            kind = _classify_entry_point(function, graph)
            if kind is None:
                continue
            class_name = method_class_index.get(function.id)
            stable_key = f"{module_key}::{class_name or 'module'}::{function.name}"
            candidates.append(
                EntryPoint(
                    symbolId=function.id,
                    stableKey=stable_key,
                    name=function.name,
                    moduleKey=module_key,
                    moduleName=module_name,
                    className=class_name,
                    kind=kind,
                )
            )

    return tuple(sorted(candidates, key=lambda entry_point: (entry_point.moduleName, entry_point.name, entry_point.stableKey)))


def _classify_entry_point(function: FunctionSymbol, graph: DependencyGraph) -> EntryPointKind | None:
    decorators = function.metadata.get("decorators") or ()
    if any(_CLI_DECORATOR_PATTERN.search(decorator) for decorator in decorators):
        return "cli-command"
    if any(_API_DECORATOR_PATTERN.search(decorator) for decorator in decorators):
        return "api-route"
    if graph.functions_calling(function.id) == []:
        return "function"
    return None


def build_entry_point_call_sequence(
    graph: DependencyGraph,
    entry_point: EntryPoint,
    *,
    max_depth: int = MAX_CALL_DEPTH,
    resolve_module: Callable[[str | None], tuple[str, str] | None] = lambda _sourceFile: None,
    resolve_class_name: Callable[[str], str | None] = lambda _symbolId: None,
) -> SequenceDiagramSelection:
    """Build an entry point's bounded, ordered call sequence.

    Pre-order DFS over ``graph.functions_called_by``, re-sorted at each step
    by the originating call edge's ``lineStart`` (Research Decision 4 - the
    raw helper result order is not real call order). ``resolve_module``/
    ``resolve_class_name`` attribute each call step's callee to its owning
    module/class using data callers already have loaded (Research Decision
    5); a callee that cannot be resolved still produces a step (Edge Case 4).
    """
    steps: list[CallStep] = []
    truncated = False

    def edge_line_start(caller_id: str, callee_id: str) -> int:
        edge = graph.edges.get((caller_id, callee_id, "call"))
        line_start = edge.metadata.get("lineStart") if edge is not None else None
        return line_start if isinstance(line_start, int) else 0

    def walk(focus_id: str, depth: int) -> None:
        nonlocal truncated
        callees = graph.functions_called_by(focus_id)
        if not callees:
            return
        ordered_callees = sorted(callees, key=lambda node: (edge_line_start(focus_id, node.id), node.id))
        for callee in ordered_callees:
            resolved_module = resolve_module(callee.sourceFile)
            steps.append(
                CallStep(
                    depth=depth + 1,
                    callerSymbolId=focus_id,
                    calleeSymbolId=callee.id,
                    calleeName=callee.name,
                    calleeModuleKey=resolved_module[0] if resolved_module else None,
                    calleeModuleName=resolved_module[1] if resolved_module else None,
                    calleeClassName=resolve_class_name(callee.id),
                    order=len(steps),
                )
            )
            if depth + 1 >= max_depth:
                if graph.functions_called_by(callee.id):
                    truncated = True
            else:
                walk(callee.id, depth + 1)

    walk(entry_point.symbolId, 0)
    return SequenceDiagramSelection(entryPoint=entry_point, steps=tuple(steps), truncatedAtMaxDepth=truncated)
