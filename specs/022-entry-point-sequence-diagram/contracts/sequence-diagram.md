# Entry Point Sequence Diagram Contract

## Purpose

Define the new `doc_generator` (and one small `parser_engine` /
`repository_metadata`) functions that turn already-captured call edges into
one bounded, ordered sequence diagram per identified entry point, the page
each is embedded in, and how they participate in incremental regeneration —
the same role `021-repository-class-diagram`'s `class-diagram.md` contract
plays for the class diagram, and `013`'s `mermaid-diagram-render.md` for the
per-module dependency diagram. As with both, this is two functions in two
places (selection, then rendering), not one.

## Extraction-layer function

### `parser_engine.extractor._python_build_module` (modified, Python path only)

- `build_function(...)` additionally reads `node.decorator_list` and sets
  `FunctionSymbol.decorators = tuple(_python_unparse(d) for d in
  node.decorator_list)`.
- No change to any other language's extraction path; their `FunctionSymbol`s
  keep `decorators == ()`.
- `repository_metadata.sqlite_store._convert_function_symbol` adds
  `"decorators": list(function_symbol.decorators)` to the `metadata` dict it
  already builds (alongside `owner`/`returnType`) — no schema change.

## Core functions (new module: `doc_generator/entry_point_diagram.py`)

### `identify_entry_points(bundle: RepositoryBundle, graph: DependencyGraph) -> tuple[EntryPoint, ...]`

Expected behavior:
- Candidate pool: every `FunctionSymbol` across `bundle.files[*].functions`
  whose name does not start with `_` and whose id is not in any function's
  `nestedSymbols` (Research Decision 1).
- A candidate qualifies if either:
  - its `metadata["decorators"]` (from `repository_metadata.FunctionSymbol`)
    contains an entry matching the CLI or API-route pattern (Research
    Decision 3) — classified `"cli-command"` / `"api-route"` respectively,
    regardless of `functions_calling` (FR-002); or
  - `graph.functions_calling(candidate.id) == []` (Research Decision 2) —
    classified `"function"`.
- Returns `()` for a repository with no qualifying candidates (not an
  error) — mirrors `select_major_classes`'s empty-selection contract.
- Deterministic ordering (e.g. by `(moduleName, name, stableKey)`) so page
  generation order — and therefore any test asserting on generated file
  lists — is stable across runs.

### `build_entry_point_call_sequence(graph: DependencyGraph, entry_point: EntryPoint, *, max_depth: int = 6) -> SequenceDiagramSelection`

Expected behavior:
- Pre-order DFS over `graph.functions_called_by(focus)`, re-sorted at each
  step by the originating call edge's `metadata["lineStart"]` (Research
  Decision 4) — never the raw (unordered) helper return order.
- Stops descending a branch once `depth == max_depth`; sets
  `truncatedAtMaxDepth = True` if that cutoff actually discarded further
  calls on any branch (i.e. the cut-off node still had outgoing calls of its
  own), `False` otherwise.
- An entry point with no outgoing calls returns `SequenceDiagramSelection(
  entryPoint=..., steps=())` — never a fabricated step (spec FR-006).
- A call whose target's owning module cannot be resolved still produces a
  `CallStep` (with `calleeModuleKey/Name = None`), using the best available
  name (Edge Case 4) — traversal never breaks or drops the step.
- Repeated calls from the same caller to the same target collapse to one
  `CallStep`, a direct, unavoidable consequence of reusing
  `functions_called_by` as-is (Clarifications session, Research Decision 4)
  — not additional logic to implement or test as a special case beyond
  confirming the natural behavior.

### `mermaid_diagram.build_sequence_diagram_mermaid_source(selection: SequenceDiagramSelection) -> SequenceDiagramSource`

Expected behavior:
- Emits one Mermaid `participant` per distinct symbol appearing in
  `[selection.entryPoint] + [step.callee for step in selection.steps]`, in
  first-appearance order, each with a synthetic id (`p0`, `p1`, ...) and a
  sanitized `Module[.Class].function` label (Research Decision 9).
- Emits one `->>` message per `CallStep`, in `selection.steps` order
  (already the real call order per Decision 4) — never reordered or
  deduplicated again at this stage.
- An entry point with `steps == ()` still renders a valid `sequenceDiagram`
  block containing only its own `participant` line — a minimal diagram, not
  an empty/broken one (spec FR-006 / SC-004).
- Deterministic: the same `SequenceDiagramSelection` always produces
  byte-identical `sourceText`.
- Added to the existing `doc_generator/mermaid_diagram.py` (not a new
  file), alongside `build_mermaid_source` / `build_class_diagram_mermaid_source`.

## `DocGenerator` page method

### `generateEntryPointSequenceDiagramPages() -> tuple[DocPage, ...]`

- Calls `identify_entry_points` once per generation run, then for each
  entry point: `build_entry_point_call_sequence` →
  `build_sequence_diagram_mermaid_source` → one `DocPage` of kind
  `"sequence-diagram"`.
- Page id: `sequence:{entryPoint.stableKey}` (Research Decision 6/7). Output
  path: `links.diagram_output_paths(links.page_slug(entryPoint.name,
  entryPoint.stableKey))` — the existing, unmodified `diagrams/{slug}.md`
  convention (Research Decision 7).
- Each page is linked from its entry point's existing `###`/`####` section
  on the owning module's page (`module.md.jinja`, one new optional link per
  function/method, mirroring the existing `diagram_link` pattern already
  used for the module-level dependency diagram).
- Returns `()` when `identify_entry_points` returns `()` — no pages written,
  no broken links emitted anywhere (spec Edge Case 5).

## Incremental regeneration expectations

- `compute_regeneration_impact` (extended per Research Decision 8): a
  changed function/class symbol invalidates any `sequence:{key}` page
  rooted at that symbol, and any `sequence:{key}` page whose previously
  recorded call sequence included that symbol as a step.
- Entry-point *membership* (which functions currently qualify at all) is
  recomputed from the freshly-loaded bundle + graph every run — cheap,
  in-memory, no source re-parse — the same non-incremental-selection
  precedent 021 established for major-class ranking.
- A full, from-scratch run (`incremental=False`, or no previous manifest
  entries) regenerates every entry point's sequence-diagram page
  unconditionally, same as every existing page kind.
- An entry point that no longer qualifies (e.g. it gained a caller, or was
  deleted) has its page removed via the existing removed-page-id mechanism
  (`impact.removed_page_ids`), same as every existing page kind.

## Failure expectations

- A repository with zero qualifying entry points: no sequence-diagram pages
  are written, no broken/dead links appear on any module page (spec Edge
  Case 5, FR-007).
- A Mermaid participant label containing a literal `;` or unescaped `"` must
  never reach `sourceText` unsanitized — asserted directly in tests against
  a fixture function/class name containing those characters, not just
  trusted to not occur in practice (same standard 021 held itself to).
- A call chain containing recursion or a cycle must still produce a
  complete, valid `sequenceDiagram` block bounded at `MAX_CALL_DEPTH` — 
  asserted directly against a fixture with a self-recursive function and a
  fixture with a two-function cycle (spec Edge Case 1 / Acceptance Scenario
  3 / SC-003).
