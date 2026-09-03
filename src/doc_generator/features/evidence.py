from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Mapping

from dependency_graph import DependencyGraph
from repository_metadata.models import RepositoryBundle

from ..entry_point_diagram import identify_entry_points

# The same bound `entry_point_diagram.MAX_CALL_DEPTH` uses, deliberately: a
# module is "reached by" an entry point on the same terms the sequence diagram
# would draw it, so the two never disagree about what an entry point touches.
MAX_EVIDENCE_CALL_DEPTH = 6

# ~375 tokens of the planner's budget. The README is the only place a
# repository states its capabilities in its own words, which is exactly what
# naming a feature needs - but it is also unbounded in size, so it is capped
# like every other input to that call.
MAX_README_PROMPT_CHARS = 1500

# `.md` first, and that is the point. `chat.retrieval.read_readme_content`
# deliberately omits `.md` because a `README.md` is indexed like any other file
# and retrieval returns the relevant parts of it; returning it whole there would
# pay for the same text twice. Here the opposite is wanted - the repository's
# own statement of what it does - and `.md` is the overwhelmingly common case.
_README_CANDIDATES = ("README.md", "README.rst", "README.txt", "readme.md", "Readme.md")

# A README's capability lines: list items and headings. Prose paragraphs are
# skipped - they are the project's history, licence and install instructions,
# none of which names a feature.
_BULLET_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.*)$")
_HEADING_PATTERN = re.compile(r"^\s*#{1,3}\s+(.*)$")


@dataclass(frozen=True, slots=True)
class FeatureEvidence:
    """What is known about one module before any grouping is decided.

    Derived with no model call, and the sole input to candidate formation.
    """

    moduleKey: str
    moduleName: str
    filePath: str
    directoryPath: str
    reachingEntryPointKeys: tuple[str, ...] = ()
    exportedSymbolNames: tuple[str, ...] = ()
    #: Kept apart rather than merged, because the feature page renders the
    #: author's own docstring in preference to a model-written summary and has
    #: to be able to tell which it has.
    docstring: str = ""
    generatedSummary: str = ""


@dataclass(frozen=True, slots=True)
class RepositoryEvidence:
    modules: tuple[FeatureEvidence, ...] = ()
    readmeBullets: tuple[str, ...] = ()
    entryPointModuleKeys: tuple[str, ...] = ()
    entryPointKeysByModuleKey: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def by_module_key(self) -> dict[str, FeatureEvidence]:
        return {evidence.moduleKey: evidence for evidence in self.modules}


def build_repository_evidence(
    bundle: RepositoryBundle,
    graph: DependencyGraph,
    *,
    repository_root: str | Path,
) -> RepositoryEvidence:
    """Everything the grouping stage needs, derived with no model call.

    Takes no LLM engine - see this package's docstring for why that is a
    signature and not a convention.

    One `FeatureEvidence` per module in `bundle.files`, always: a module with no
    entry points reaching it, no exports and no summary still gets a row with
    empty tuples. `candidates.build_candidates` has to be able to place *every*
    module, and a missing row would not raise - it would quietly leave that
    module out of the navigation, which is the one failure this whole feature
    exists to prevent.
    """
    entry_points = identify_entry_points(bundle, graph)

    reached_by: dict[str, set[str]] = {}
    for entry_point in entry_points:
        for symbol_id in _reachable_symbol_ids(graph, entry_point.symbolId):
            reached_by.setdefault(symbol_id, set()).add(entry_point.stableKey)

    modules: list[FeatureEvidence] = []
    entry_point_keys_by_module: dict[str, set[str]] = {}
    for file_bundle in bundle.files:
        module = file_bundle.module
        module_key = module.sourceFileId

        owned_symbol_ids = {module.id}
        owned_symbol_ids.update(symbol.id for symbol in file_bundle.classes)
        owned_symbol_ids.update(symbol.id for symbol in file_bundle.functions)

        reaching: set[str] = set()
        for symbol_id in owned_symbol_ids:
            reaching |= reached_by.get(symbol_id, set())

        nested_ids = {
            nested_id for function in file_bundle.functions for nested_id in function.nestedSymbols
        }
        exported = sorted(
            {symbol.name for symbol in file_bundle.classes if not symbol.name.startswith("_")}
            | {
                function.name
                for function in file_bundle.functions
                if function.owner == "module"
                and function.id not in nested_ids
                and not function.name.startswith("_")
            }
        )

        modules.append(
            FeatureEvidence(
                moduleKey=module_key,
                moduleName=module.name,
                filePath=module.filePath,
                directoryPath=relative_directory(module.filePath, repository_root),
                reachingEntryPointKeys=tuple(sorted(reaching)),
                exportedSymbolNames=tuple(exported),
                docstring=module.docstring or "",
                generatedSummary=module.generatedSummary or "",
            )
        )

    for entry_point in entry_points:
        entry_point_keys_by_module.setdefault(entry_point.moduleKey, set()).add(entry_point.stableKey)

    return RepositoryEvidence(
        modules=tuple(sorted(modules, key=lambda evidence: evidence.moduleKey)),
        readmeBullets=read_readme_bullets(repository_root),
        entryPointModuleKeys=tuple(sorted(entry_point_keys_by_module)),
        entryPointKeysByModuleKey={
            module_key: tuple(sorted(keys)) for module_key, keys in entry_point_keys_by_module.items()
        },
    )


def _reachable_symbol_ids(
    graph: DependencyGraph, start_symbol_id: str, *, max_depth: int = MAX_EVIDENCE_CALL_DEPTH
) -> set[str]:
    """Every symbol one entry point reaches, with its own visited set.

    Deliberately *not* `build_entry_point_call_sequence`. That walk has no
    visited set on purpose ([entry_point_diagram.py] `walk`), because a sequence
    diagram must draw a repeated call twice - reusing it here would mean
    deduplicating its output afterwards, and would inherit a bound that belongs
    to diagrams rather than to evidence. It is also unbounded on a call cycle
    except through `max_depth`, so a pathological graph really can blow up.

    "Which entry points reach this module" is a set question and gets a set
    answer.
    """
    seen = {start_symbol_id}
    frontier: deque[tuple[str, int]] = deque([(start_symbol_id, 0)])
    while frontier:
        symbol_id, depth = frontier.popleft()
        if depth >= max_depth:
            continue
        for callee in graph.functions_called_by(symbol_id):
            if callee.id not in seen:
                seen.add(callee.id)
                frontier.append((callee.id, depth + 1))
    return seen


def read_readme_bullets(
    repository_root: str | Path, *, max_chars: int = MAX_README_PROMPT_CHARS
) -> tuple[str, ...]:
    """The analysed repository's own statement of what it does.

    A *read* of the analysed repository, which constitution 2.7 permits - it
    forbids writes. Best-effort throughout: a missing, unreadable, non-text or
    empty README yields `()`. An unreadable README must degrade the planner's
    prompt, never the run.
    """
    root = Path(repository_root)
    for candidate in _README_CANDIDATES:
        path = root / candidate
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # A README that exists but cannot be read is the same outcome as no
            # README at all. Never the run's problem.
            return ()
        bullets = _extract_bullets(text)
        if bullets:
            return _truncate_bullets(bullets, max_chars)
        return ()
    return ()


def _extract_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for raw_line in text.splitlines():
        match = _BULLET_PATTERN.match(raw_line) or _HEADING_PATTERN.match(raw_line)
        if match is None:
            continue
        line = " ".join(match.group(1).split()).strip("*_`#").strip()
        if line:
            bullets.append(line)
    return bullets


def _truncate_bullets(bullets: list[str], max_chars: int) -> tuple[str, ...]:
    """Truncate at a line boundary, never mid-bullet.

    Half a capability description is worse than one fewer capability: the model
    would be asked to name a feature from a sentence that stops mid-word.
    """
    kept: list[str] = []
    used = 0
    for bullet in bullets:
        cost = len(bullet) + 1
        if used + cost > max_chars:
            break
        kept.append(bullet)
        used += cost
    return tuple(kept)


def relative_directory(file_path: str, repository_root: str | Path) -> str:
    """The module's repository-relative directory, `"."` at the root.

    Shared with `fallback.py`, which groups by exactly this string. Defined here
    because evidence is the earlier stage and the fallback consumes evidence,
    not the other way round.
    """
    path = Path(file_path)
    root = Path(repository_root)
    try:
        relative = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        # A path outside the repository root, or one this filesystem cannot
        # resolve, still has to land somewhere; its own parent name is the
        # closest honest answer.
        return path.parent.name or "."
    directory = relative.parent.as_posix()
    return directory if directory not in ("", ".") else "."


def normalize_path(path: str) -> str:
    return PurePosixPath(Path(path).as_posix().replace("\\", "/")).as_posix()
