# Data Model: Repository Use Case Diagram

Mirrors the existing two-stage split `021-repository-class-diagram` and
`022-entry-point-sequence-diagram` established (selection → Mermaid
rendering), applied to actors/use-cases derived from 022's entry-point list.

## New entities (selection stage — `use_case_diagram.py`, new module)

### `Actor`

- `kind: EntryPointKind` (reused from `entry_point_diagram`, unmodified:
  `Literal["cli-command", "api-route", "function"]`) — the actor's category,
  and its identity within a selection (at most one `Actor` per `kind`).
- `label: str` — the fixed display label for this category: `"CLI"` for
  `"cli-command"`, `"API"` for `"api-route"`, `"External Caller"` for
  `"function"` (Research Decision 3).

### `UseCase`

- `entryPointStableKey: str` — the originating entry point's
  `EntryPoint.stableKey` (022), reused verbatim as this use case's stable
  identity; not a new key scheme.
- `label: str` — `Module[.Class].name`, the same label convention 022's
  sequence-diagram rendering already uses (Research Decision 4).
- `actorKind: EntryPointKind` — which `Actor` this use case connects to;
  always equal to the originating `EntryPoint.kind`.

### `UseCaseDiagramSelection`

- `actors: tuple[Actor, ...]` — every distinct actor kind present among the
  identified entry points, in fixed canonical order (CLI, API, generic —
  Research Decision 3); `()` when there are no entry points at all.
- `useCases: tuple[UseCase, ...]` — one per identified entry point, in the
  same deterministic order `identify_entry_points()` already returns
  (`(moduleName, name, stableKey)`); `()` when the repository exposes no
  identifiable entry point (spec FR-005 — no diagram is generated in that
  case, per the rendering/page contracts below).

## New entities (rendering stage — `mermaid_diagram.py`, new function `build_use_case_diagram_mermaid_source`)

### `UseCaseDiagramSource`

- `sourceText: str` — the full Mermaid `flowchart` block using the
  UML-use-case-diagram workaround already established by
  `docs/diagrams/use-case-diagram.md` (Research Decision 2).
- `actorNodeIds: tuple[str, ...]` — synthetic Mermaid node ids (`a0`, `a1`,
  ...) for each actor, in `selection.actors` order.
- `useCaseNodeIds: tuple[str, ...]` — synthetic Mermaid node ids (`u0`,
  `u1`, ...) for each use case, in `selection.useCases` order.

## Existing entities this feature reads but does not modify

- `entry_point_diagram.EntryPoint`, `EntryPointKind`,
  `identify_entry_points(bundle, graph)` (022) — read-only; this feature's
  entire entry-point candidate pool, classification, and ordering come from
  here unmodified (Research Decision 1).
- `RepositoryBundle`, `DependencyGraph` (`repository_metadata`,
  `dependency_graph`) — read-only, passed through unchanged to
  `identify_entry_points()`; this feature does not read them directly.

## Existing entities this feature extends

### `PageKind` (`doc_generator.models`)

Add `"use-case-diagram"` to the existing
`Literal["home", "module", "diagram", "class-diagram", "sequence-diagram"]`.

### `RegenerationImpactSet` / `compute_regeneration_impact` (`doc_generator.impact`)

No new fields on `RegenerationImpactSet` itself; `impactedPageIds` gains the
fixed `diagram:use-case-overview` page id whenever the repository has at
least one identified entry point and this run has any direct symbol or
dependency-edge change (Research Decision 6); `removedPageIds` gains that
same id when the repository transitions from having at least one entry
point to having none.
