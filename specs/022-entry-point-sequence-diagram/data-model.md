# Data Model: Entry Point Sequence Diagrams

Mirrors the existing two-stage split `021-repository-class-diagram`
established (selection → Mermaid rendering), applied to entry points instead
of classes.

## New field on an existing entity

### `FunctionSymbol.decorators` (`parser_engine.symbols.FunctionSymbol`)

- `decorators: tuple[str, ...] = ()` — the unparsed source text of each
  decorator applied to this function, in source order. Populated only by
  the Python extraction path (Research Decision 3); always `()` for
  brace-language symbols. Threaded into
  `repository_metadata.models.FunctionSymbol.metadata["decorators"]`
  (a `list[str]` in the persisted JSON, alongside the existing
  `owner`/`returnType` entries — no new column, no schema migration).

## New entities (selection stage — `entry_point_diagram.py`, new module)

### `EntryPointKind`

`Literal["cli-command", "api-route", "function"]` — which of the spec's
three entry-point categories a given `EntryPoint` was classified as (FR-001,
FR-002). Purely descriptive (e.g. for diagram titling); does not affect
traversal.

### `EntryPoint`

- `symbolId: str` — the `FunctionSymbol.id` for *this run* (content-hash;
  valid for in-graph traversal within the current generation only — never
  persisted as a page-identity key, per Research Decision 6).
- `stableKey: str` — `f"{sourceFileId}::{owner}::{name}"`; the
  regeneration-stable identity used for the page id, slug, and output path
  (Research Decision 6).
- `name: str`
- `moduleKey: str` / `moduleName: str` — the owning module's `sourceFileId`
  and display name (resolved via the existing `_resolve_module_key_by_path`
  pattern).
- `className: str | None` — the owning class's name, if this entry point is
  a method (Research Decision 5); `None` for a module-level function.
- `kind: EntryPointKind`

### `CallStep`

- `depth: int` — 1-based hop count from the entry point (`1` = a call the
  entry point makes directly).
- `callerSymbolId: str` / `calleeSymbolId: str` — this run's graph node ids.
- `calleeName: str`
- `calleeModuleKey: str | None` / `calleeModuleName: str | None` — `None`
  only when the target's owning module cannot be resolved from the graph
  (Edge Case 4: unresolved/external target).
- `calleeClassName: str | None` — set when the callee is a method.
- `order: int` — 0-based position of this step in the full pre-order
  traversal of the entry point's call sequence (the sequence diagram's
  message order — see Research Decision 4).

### `SequenceDiagramSelection`

- `entryPoint: EntryPoint`
- `steps: tuple[CallStep, ...]` — depth-bounded, ordered per Research
  Decision 4; `()` when the entry point calls nothing (spec FR-006 — a
  minimal, entry-point-only diagram, never fabricated).
- `truncatedAtMaxDepth: bool` — `True` when at least one branch of the
  traversal was cut off by `MAX_CALL_DEPTH` rather than running out of real
  outgoing calls (surfaced so the rendered page can note the diagram was
  bounded, per spec Edge Case 1 / Acceptance Scenario 3 — informational
  only, does not change what's rendered).

## New entities (rendering stage — `mermaid_diagram.py`, new function
`build_sequence_diagram_mermaid_source`)

### `SequenceDiagramSource`

- `sourceText: str` — the full Mermaid `sequenceDiagram` block (Research
  Decision 9).
- `participantIds: tuple[str, ...]` — synthetic Mermaid participant ids
  (`p0`, `p1`, ...) in first-appearance order, mirroring
  `MermaidDiagramSource.nodeIdMap`'s synthetic-id pattern (real symbol names
  are not guaranteed unique across modules, so are never used directly as
  Mermaid ids — same reasoning as `build_class_diagram_mermaid_source`).
- `stepCount: int` — `len(selection.steps)`, exposed for testing/assertions
  without re-parsing `sourceText`.

## Existing entities this feature reads but does not modify

- `RepositoryBundle`, `SourceFileBundle`, `ClassSymbol.methods`,
  `FunctionSymbol.owner/nestedSymbols` (`repository_metadata`) — read-only,
  used for candidate discovery (Decision 1) and class attribution
  (Decision 5).
- `DependencyGraph.functions_calling`, `.functions_called_by`, `.edges`
  (`dependency_graph`) — read-only, used for entry-point qualification
  (Decision 2) and bounded traversal (Decision 4). No new
  `DependencyGraph`/`DependencyNode` fields.

## Existing entities this feature extends

### `PageKind` (`doc_generator.models`)

Add `"sequence-diagram"` to the existing
`Literal["home", "module", "diagram", "class-diagram"]`.

### `RegenerationImpactSet` / `compute_regeneration_impact` (`doc_generator.impact`)

No new fields on `RegenerationImpactSet` itself; `impactedPageIds` gains
entries for affected `sequence:{stableKey}` page ids per Research Decision 8.
