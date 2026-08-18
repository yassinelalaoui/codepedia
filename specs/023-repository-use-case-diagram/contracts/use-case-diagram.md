# Repository Use Case Diagram Contract

## Purpose

Define the new `doc_generator` functions that turn 022's already-identified
entry points into one, single, repository-wide use-case diagram page, and
how it participates in incremental regeneration — the same role
`021-repository-class-diagram`'s `class-diagram.md` contract plays for the
class diagram. As with 021/022, this is two functions in two places
(selection, then rendering), not one, and neither touches
`entry_point_diagram.py`, `parser_engine`, `repository_metadata`, or
`dependency_graph`.

## Core functions (new module: `doc_generator/use_case_diagram.py`)

### `select_use_cases(bundle: RepositoryBundle, graph: DependencyGraph) -> UseCaseDiagramSelection`

Expected behavior:
- Calls `entry_point_diagram.identify_entry_points(bundle, graph)` exactly
  once, unmodified — no new entry-point detection (Research Decision 1).
- Returns `UseCaseDiagramSelection()` (both `actors` and `useCases` empty)
  when `identify_entry_points()` returns `()` — mirrors
  `select_major_classes()`'s empty-selection contract (021).
- Otherwise, builds one `UseCase` per identified entry point (label:
  `Module[.Class].name`, Research Decision 4) in `identify_entry_points()`'s
  existing deterministic order, and one `Actor` per distinct `EntryPointKind`
  present, in fixed canonical order (CLI, API, generic — Research
  Decision 3) — never one actor per individual entry point.

### `mermaid_diagram.build_use_case_diagram_mermaid_source(selection: UseCaseDiagramSelection) -> UseCaseDiagramSource`

Expected behavior:
- Emits one oval actor node per `selection.actors` entry (synthetic id `a0`,
  `a1`, ...) and one oval use-case node per `selection.useCases` entry
  (synthetic id `u0`, `u1`, ...), using the same `flowchart`
  UML-use-case-diagram workaround as `docs/diagrams/use-case-diagram.md`
  (Research Decision 2): actor nodes outside a system-boundary `subgraph`,
  use-case nodes inside it.
- Emits one plain `-->` arrow from each use case's actor to that use case
  (`selection.useCases[i].actorKind` resolved to its `Actor`'s synthetic id)
  — no `include`/`extend`-labeled edges are generated (Research Decision 2).
- A selection with `useCases == ()` still produces syntactically valid
  (if degenerate) `sourceText` — callers are expected not to invoke this on
  an empty selection in practice (see `generateUseCaseDiagramPage` below),
  but the function itself does not special-case or reject it.
- Deterministic: the same `UseCaseDiagramSelection` always produces
  byte-identical `sourceText`.
- Labels sanitized against a literal, unescaped `"` via the existing
  `_escape_label` helper (already used by the flowchart-based dependency
  diagram).
- Added to the existing `doc_generator/mermaid_diagram.py` (not a new
  file), alongside `build_mermaid_source`/`build_class_diagram_mermaid_source`/
  `build_sequence_diagram_mermaid_source`.

## `DocGenerator` page method

### `generateUseCaseDiagramPage() -> DocPage | None`

- Calls `select_use_cases()` once per generation run; returns `None`
  immediately when `selection.useCases` is empty (spec FR-005) — no page
  written, no home-page link emitted (mirrors
  `generateClassDiagramPage()`'s `None`-when-empty contract exactly).
- Otherwise: page id `links.use_case_diagram_page_id()` (fixed constant,
  `"diagram:use-case-overview"`); output path
  `links.use_case_diagram_output_paths()` (fixed constant,
  `diagrams/use-case-overview.md`/`.html`) — mirrors
  `CLASS_DIAGRAM_PAGE_ID`/`class_diagram_output_paths()` exactly (021).
- The page is linked once from the wiki's overview/home page
  (`generateOverviewPage`, mirroring the existing `class_diagram_link`
  parameter/rendering) — never from a per-module or per-entry-point page.

## Incremental regeneration expectations

- `compute_regeneration_impact` (extended per Research Decision 6): the
  fixed `diagram:use-case-overview` page id is added to `impactedPageIds`
  whenever the repository has at least one identified entry point and this
  run has any direct symbol or dependency-edge change — the same condition
  021 already uses for its own repository-wide class-diagram page, applied
  to "has any entry point" instead of "has any class". This reuses the
  entry-point list `impact.py` already computes for 022's sequence-diagram
  invalidation; no second `identify_entry_points()` call is added.
- A full, from-scratch run (`incremental=False`, or no previous manifest
  entries) regenerates the use-case-diagram page unconditionally (when it
  exists), same as every existing page kind.
- When the repository has zero entry points, the page id is excluded from
  `current_page_ids`, so a previously generated page is removed via the
  existing `removedPageIds` mechanism (`impact.removed_page_ids`) — same as
  021's class diagram when the last class is removed.

## Failure expectations

- A repository with zero identifiable entry points: no use-case-diagram
  page is written, and the home page contains no link to a missing page
  (spec FR-005, Edge Case "repository with no identifiable entry point").
- An actor/use-case label containing a literal, unescaped `"` must never
  reach `sourceText` unsanitized — asserted directly in tests against a
  fixture entry point name containing that character, not just trusted to
  not occur in practice (same standard 021/022 held themselves to).
- A repository exposing entry points of only one kind (e.g. only CLI
  commands): the diagram must show only that one actor node — no empty or
  unused actor nodes for kinds with zero entry points (spec Edge Case).
