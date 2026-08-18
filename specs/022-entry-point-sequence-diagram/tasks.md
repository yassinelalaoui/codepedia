# Tasks: Entry Point Sequence Diagrams

**Input**: Design documents from `/specs/022-entry-point-sequence-diagram/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/sequence-diagram.md, quickstart.md

## Phase 1: Setup

**Goal:** N/A for this feature — no new package, dependency, or vendored asset is needed. The `doc_generator` and `parser_engine` packages, their test directories, and the vendored `mermaid.min.js` (013) already exist and are reused/lightly extended.

*(No tasks in this phase.)*

## Phase 2: Foundational

**Goal:** Add the one new `PageKind` value, the page-id helper, and the decorator-capture data path every later task needs — the small, scoped `parser_engine`/`repository_metadata` extension (Research Decision 3) plus the `doc_generator` plumbing (Research Decisions 6/7) that everything else builds on.

**Independent test criteria:** `links.sequence_diagram_page_id(key)` returns `f"sequence:{key}"`; `"sequence-diagram"` is a valid `DocPage.kind`; extracting a Python function decorated `@app.command("x")` produces `FunctionSymbol.decorators == ("app.command('x')",)` (exact unparsed text may vary slightly with `ast.unparse` formatting — assert the attribute name `app.command` appears), and an undecorated function has `decorators == ()`; the same decorator text round-trips into `repository_metadata.FunctionSymbol.metadata["decorators"]`.

- [X] T001 [P] Extend the `PageKind` literal in `src/doc_generator/models.py` to include `"sequence-diagram"`, per `data-model.md`'s `PageKind` extension.
- [X] T002 [P] Add `sequence_diagram_page_id(key: str) -> str` (returns `f"sequence:{key}"`) to `src/doc_generator/links.py`, mirroring `class_diagram_page_id()`/`diagram_page_id()`. Reuses the existing, unmodified `diagram_output_paths(slug)` and `page_slug(name, entity_id)` for output paths — no new path helper needed, per `research.md` Decision 7.
- [X] T003 [P] Add `decorators: tuple[str, ...] = ()` to `parser_engine.symbols.FunctionSymbol` in `src/parser_engine/symbols.py`, per `data-model.md`.
- [X] T004 In `src/parser_engine/extractor.py`, extend `_python_build_module`'s `build_function(...)` (Python extraction path only) to set `decorators=tuple(_python_unparse(d) for d in node.decorator_list)` on the constructed `FunctionSymbol`, reusing the existing `_python_unparse` helper. The brace-language path (`_extract_brace_inventory`) is left unchanged — its `FunctionSymbol`s keep `decorators == ()`, per `research.md` Decision 3 / `plan.md` Complexity Tracking. Depends on T003.
- [X] T005 [P] In `src/repository_metadata/sqlite_store.py`, extend `_convert_function_symbol` to add `"decorators": list(function_symbol.decorators)` to the `metadata` dict it already builds (alongside `owner`/`returnType`) — no schema change, `metadata` is already a generic persisted JSON column. Depends on T003.
- [X] T006 [P] Add a unit test to `tests/unit/test_symbol_extractor.py` asserting: a Python function decorated `@app.command("index")` has a `decorators` tuple containing text matching `app.command`; a function decorated `@app.get("/sessions")` has `decorators` matching `app.get`; a plain undecorated function has `decorators == ()`; a class method decorated similarly is also captured (decorators apply per-function regardless of `owner`). Depends on T004.

**Checkpoint**: Foundation ready — user story implementation can now begin.

## Phase 3: User Story 1 - View an entry point's call sequence

**Goal:** Identify every entry point in the repository (CLI command, API route handler, or uncalled public function/method), generate one bounded, correctly-ordered, correctly-attributed sequence diagram per entry point, link it from that entry point's existing documentation section, and wire it into incremental regeneration.

**Independent test criteria:** `quickstart.md` Scenario A — against a fixture repository with an entry point calling two or more functions across multiple modules, the entry point's own module page links to a sequence diagram showing the calls in real order with correct module/class attribution (SC-001, SC-002).

### Selection layer

- [X] T007 [P] [US1] Create `src/doc_generator/entry_point_diagram.py` with the `EntryPointKind`, `EntryPoint`, `CallStep`, and `SequenceDiagramSelection` dataclasses (per `data-model.md`) and `identify_entry_points(bundle: RepositoryBundle, graph: DependencyGraph) -> tuple[EntryPoint, ...]`: candidate pool is every non-`_`-prefixed, non-nested `FunctionSymbol` across `bundle.files[*].functions` (module-level and class methods, per `research.md` Decision 1); a candidate qualifies as `"cli-command"`/`"api-route"` when its `metadata["decorators"]` matches `\.(command|callback)\(` / `\.(get|post|put|delete|patch)\(` respectively (FR-002, always an entry point regardless of callers), else as `"function"` when `graph.functions_calling(candidate.id) == []` (FR-001, Decision 2). Each `EntryPoint.stableKey` is `f"{sourceFileId}::{owner}::{name}"` (Decision 6), `moduleKey`/`moduleName` resolved the same way `generator.py::_resolve_module_key_by_path` already does, `className` resolved by walking `bundle.files[*].classes[*].methods` (Decision 5). Returns `()` for a repository with no qualifying candidates. Deterministic ordering by `(moduleName, name, stableKey)`.
- [X] T008 [US1] In `src/doc_generator/entry_point_diagram.py`, add `build_entry_point_call_sequence(graph: DependencyGraph, entry_point: EntryPoint, *, max_depth: int = 6) -> SequenceDiagramSelection`: pre-order DFS over `graph.functions_called_by(focus)`, re-sorted at each step by the originating call edge's `graph.edges[(focus_id, callee.id, "call")].metadata["lineStart"]` (never the raw unordered helper result — `research.md` Decision 4); stops descending once `depth == max_depth`, setting `truncatedAtMaxDepth = True` only when a cut-off node still had further outgoing calls of its own; an entry point with no outgoing calls returns `steps == ()` (FR-006); a call whose target's module cannot be resolved still produces a `CallStep` with `calleeModuleKey/Name = None` (Edge Case 4); each `CallStep.calleeClassName` resolved via the same method-ownership lookup as T007. Depends on T007.
- [X] T009 [P] [US1] Add `tests/unit/test_entry_point_diagram.py` for `identify_entry_points`: hand-built `RepositoryBundle`/`DependencyGraph` (no fixture files, mirroring `tests/unit/test_class_diagram.py`'s style) asserting — a module-level function nothing calls qualifies as `"function"`; a function called by another function does not qualify; a method decorated with a CLI/API-route-matching decorator qualifies as `"cli-command"`/`"api-route"` even when another function calls it (FR-002); a function called only from module-level top-level code (not from another function) still qualifies (Decision 2's `main()`-guard case); a `_private` or nested function never qualifies regardless of decorators/callers; a repository with zero qualifying candidates returns `()`. Depends on T007.
- [X] T010 [P] [US1] Add `tests/unit/test_entry_point_diagram.py` (same file) for `build_entry_point_call_sequence`: a hand-built 3-node chain across distinct "modules" produces steps in call-site line order (not construction/insertion order); a leaf entry point (no outgoing calls) produces `steps == ()`; a self-recursive function's diagram has exactly `max_depth` steps with `truncatedAtMaxDepth == True`; a 2-function cycle (A calls B calls A) alternates for `max_depth` steps without hanging; a call targeting an unresolved/external symbol still produces one `CallStep` with `calleeModuleKey is None`; two distinct call sites from the same caller to the same callee still produce exactly one `CallStep` (the natural consequence of reusing `functions_called_by`, per Clarifications/Decision 4 — assert this rather than assume it). Depends on T008.

### Rendering layer

- [X] T011 [US1] Add the `SequenceDiagramSource` dataclass and `build_sequence_diagram_mermaid_source(selection: SequenceDiagramSelection) -> SequenceDiagramSource` to the existing `src/doc_generator/mermaid_diagram.py`: one Mermaid `participant` per distinct symbol (entry point + every step's callee) in first-appearance order with a synthetic id (`p0`, `p1`, ...) and a sanitized `Module[.Class].function` label (falling back to just the raw callee name when unresolved), followed by one `->>` message per `CallStep` in `selection.steps` order; a `steps == ()` selection still renders a valid `sequenceDiagram` block containing only the entry point's `participant` line (FR-006/SC-004); labels sanitized against literal `;`/unescaped `"` per the same standard `_escape_label`/`_sanitize_class_diagram_label` already use, per `research.md` Decision 9. Depends on T008.
- [X] T012 [P] [US1] Add unit tests to `tests/unit/test_mermaid_diagram.py` for `build_sequence_diagram_mermaid_source`: valid non-empty `sequenceDiagram` text; participant count and order match first-appearance across entry point + steps; one `->>` line per step in `selection.steps` order; a zero-step selection renders exactly one `participant` line and zero `->>` lines; a symbol name containing a literal `;` or `"` is sanitized in the rendered label. Depends on T011.
- [X] T013 [US1] Create `src/doc_generator/templates/sequence_diagram.md.jinja` embedding the ` ```mermaid ` fenced block (`sequence_diagram_source.sourceText`) plus a note when `selection.truncatedAtMaxDepth` is true, mirroring `class_diagram.md.jinja`'s structure. Depends on T011.

### Wiring

- [X] T014 [US1] Implement `DocGenerator.generateEntryPointSequenceDiagramPages() -> tuple[DocPage, ...]` in `src/doc_generator/generator.py`: calls `entry_point_diagram.identify_entry_points` once, then for each entry point `build_entry_point_call_sequence` → `build_sequence_diagram_mermaid_source` → one `DocPage` of kind `"sequence-diagram"` at page id `links.sequence_diagram_page_id(entryPoint.stableKey)` and output path `links.diagram_output_paths(links.page_slug(entryPoint.name, entryPoint.stableKey))`, rendered via `sequence_diagram.md.jinja` (T013). Returns `()` when there are no qualifying entry points, per `contracts/sequence-diagram.md`. Depends on T001, T002, T007, T008, T011, T013.
- [X] T015 [US1] Wire `generateEntryPointSequenceDiagramPages()` into `DocGenerator.generateRepositoryDocumentation` in `src/doc_generator/generator.py` (called once per run, each returned page written); add an optional per-function/method `[View call sequence](...)` link in `src/doc_generator/templates/module.md.jinja` (mirroring the existing module-level `diagram_link` pattern) for functions/methods that are entry points, wired via a new `entryPointLinks` mapping `generateModulePage` passes to the template. Once sequence-diagram pages are included in `doc_set.pages`, the existing generic `tests/integration/test_mermaid_diagram.py::test_no_cdn_reference_and_classic_script_tag` (which iterates `for page in doc_set.pages`, not a fixed page-kind list) automatically asserts zero `http://`/`https://` references and a local, non-CDN Mermaid script tag for the new page kind too — this is what satisfies spec SC-006 for sequence-diagram pages; no new network-check test is needed (mirrors 021 T009's identical reasoning for the class-diagram page). Depends on T014.
- [X] T016 [US1] Extend `compute_regeneration_impact` in `src/doc_generator/impact.py` per `research.md` Decision 8: a changed function/class symbol adds `sequence:{stableKey}` to `impactedPageIds` for any entry-point page rooted at that symbol, and for any entry-point page whose previously recorded call sequence (tracked via the manifest's existing `linkedPageIds`-style reasoning) included that symbol as a step; entry-point set membership itself is recomputed from the freshly-loaded bundle/graph every run (not incrementally diffed), mirroring 021 Decision 3's precedent; a no-longer-qualifying entry point's page is removed via the existing `removedPageIds` mechanism with no further change needed. Depends on T002.

### Integration tests

- [X] T017 [P] [US1] Add `tests/integration/test_entry_point_diagram.py` (new file, reusing `_doc_generator_support.build_indexed_repo`'s alpha/beta/gamma fixture, which already has `alpha_entry` → `beta_helper` as a cross-module call not called by anything else) asserting a full generation run produces a sequence-diagram page for `alpha_entry` showing `alpha_entry → beta_helper` in order with `beta` as `beta_helper`'s correct originating module, and that `alpha.py`'s module page links to it (US1 Acceptance Scenario 2, SC-001, SC-002). In the same test/fixture, also assert `beta_helper` — called from both `alpha_entry` and `Child.run`, so not itself an entry point — gets no `sequence:*` page and no dead link anywhere (FR-007, complementing T018's zero-entry-points-repo case with the more common "some entry points, some non-entry-point functions coexist" case). Depends on T015.
- [X] T018 [P] [US1] Add an integration test (same file) asserting: a leaf entry point (a fixture function with no outgoing calls) produces a minimal one-participant diagram (Acceptance Scenario 4, SC-004); a fixture repository where every function is called by something and none is CLI/route-decorated produces zero sequence-diagram pages and no broken links on any module page (Edge Case 5, FR-007). Depends on T015.
- [X] T019 [US1] Add an integration test (same file, extending the fixture with one Typer-style `@app.command()`-decorated function that something else in the fixture also calls) asserting that function is still treated as an entry point and gets its own sequence-diagram page (Acceptance Scenario 1, FR-002). Depends on T015, T004.
- [X] T020 [US1] Add an integration test (same file) asserting incremental regeneration: after a full run, a change to a function two hops down `alpha_entry`'s call chain, followed by `generateRepositoryDocumentation(incremental=True, ...)`, still regenerates `alpha_entry`'s sequence-diagram page (SC-005, Decision 8), mirroring `test_doc_generator_links.py`'s incremental-impact test pattern. Depends on T016, T017.

**Checkpoint**: At this point, User Story 1 (the only story in this feature) is fully functional and independently testable — this is also the complete feature.

## Phase 4: Polish & Cross-Cutting Concerns

**Goal:** Confirm the Mermaid output is actually parseable (not just plausible-looking), the quickstart passes end to end including the recursion/cycle scenarios, and this repository's own documentation stays in sync with the new capability.

**Independent test criteria:** The generated `sequenceDiagram` block for a label containing `;`/`"` parses cleanly under a real Mermaid parser; `quickstart.md`'s five scenarios pass end to end; `docs/diagrams/`, `docs/architecture.md`, and `README.md` accurately describe the new capability.

- [X] T021 [P] Add an integration test (`tests/integration/test_entry_point_diagram.py`) asserting the Mermaid output for a symbol name containing `;`/`"` is well-formed (no bare `;`, balanced quotes/braces, valid `sequenceDiagram` header) — same hand-built-selection level as T012 if a real parseable identifier can't carry those characters, matching 021's T014 precedent and its documented rationale for not adding a permanent Node/mermaid-parser test dependency.
- [X] T022 Validate the end-to-end flow against `specs/022-entry-point-sequence-diagram/quickstart.md` (all five scenarios, including recursion/cycle) and fix any mismatches across `src/parser_engine/`, `src/repository_metadata/`, and `src/doc_generator/`.
- [X] T023 Update `docs/diagrams/` (add `EntryPoint`/`CallStep`/`SequenceDiagramSelection`/`SequenceDiagramSource` and their relationships to the `DocGeneratorPackage` namespace), `docs/architecture.md` (note the new per-entry-point sequence-diagram capability in the `doc_generator` layer's description), and `README.md` (if the wiki's feature list is documented there) per this project's diagrams-maintenance convention (root `README.md`, `docs/architecture.md`, `docs/stack.md`, `docs/diagrams/` must stay in sync with every implemented feature).

## Dependencies

- `T001`, `T002`, `T003` have no dependencies and can start immediately, in parallel (different files).
- `T004` depends on `T003` (needs the `decorators` field to exist before populating it).
- `T005` depends on `T003` (reads `function_symbol.decorators`); can run in parallel with `T004` (different files) once `T003` lands.
- `T006` depends on `T004`.
- `T007` has no dependency on T001-T006 — `entry_point_diagram.py`'s `identify_entry_points` needs only `RepositoryBundle`/`DependencyGraph` plus the `metadata["decorators"]` values `T005` starts populating; it can be written/tested against hand-built fixtures before `T005` lands, but a real end-to-end decorator-driven test needs `T004`+`T005`.
- `T008` depends on `T007` (needs the dataclasses and stable-key logic).
- `T009` depends on `T007`; `T010` depends on `T008` — both pure unit tests, can run in parallel with each other.
- `T011` depends on `T008` (needs `SequenceDiagramSelection`'s shape).
- `T012` depends on `T011`.
- `T013` depends on `T011` (needs `SequenceDiagramSource`'s field names).
- `T014` depends on `T001`, `T002`, `T007`, `T008`, `T011`, `T013` (assembles all of them into one page per entry point).
- `T015` depends on `T014`.
- `T016` depends on `T002` only (needs the page-id helper, not the page itself).
- `T017` and `T018` depend on `T015`; can run in parallel (independent test functions in the same new file, though as tasks they touch the same file so treat as sequential edits).
- `T019` depends on `T015` and `T004` (needs real decorator capture working end to end).
- `T020` depends on `T016` and `T017` (needs both the impact-tracking change and the base fixture-driven test setup already in the file).
- `T021` depends on `T012` (label sanitization) and `T017` (a working generation pipeline to source real output from).
- `T022` is a final validation after `T013` through `T021`.
- `T023` can start once the feature's shape is stable (after `T015`) and has no code dependency.

## Parallel Execution Examples

### Foundational

```text
Task: T001 -> extend PageKind in src/doc_generator/models.py
Task: T002 -> add sequence_diagram_page_id in src/doc_generator/links.py
Task: T003 -> add decorators field in src/parser_engine/symbols.py
```

### User Story 1

```text
Task: T009 -> unit test identify_entry_points in tests/unit/test_entry_point_diagram.py
Task: T010 -> unit test build_entry_point_call_sequence in tests/unit/test_entry_point_diagram.py
Task: T012 -> unit test build_sequence_diagram_mermaid_source in tests/unit/test_mermaid_diagram.py
```

## Implementation Strategy

1. Complete the Foundational phase (T001-T006): the tiny `doc_generator` plumbing (PageKind, page-id helper) plus the decorator-capture path (`parser_engine` → `repository_metadata`) — the latter is the one piece of genuinely new data-extraction work in this feature and is worth landing and testing (T006) before building selection logic on top of it.
2. Build the selection layer (T007, T008) and its unit tests (T009, T010) — this is the feature's core logic (entry-point qualification, bounded/ordered traversal) and is fully testable against hand-built graphs without touching `generator.py` at all, exactly like `class_diagram.py` already is.
3. Build the rendering layer (T011, T013) and its unit test (T012), then wire everything into `DocGenerator` (T014, T015) — this is the slice that makes the feature visible in a generated wiki.
4. Extend incremental regeneration (T016) and verify all of the above with integration tests (T017-T020), including the CLI/route-decorator branch and the multi-hop-change-propagates-to-entry-point-page case.
5. Finish with real-parser-adjacent Mermaid validation (T021), a full quickstart pass covering recursion/cycle (T022), and the repository's own documentation sync (T023).
