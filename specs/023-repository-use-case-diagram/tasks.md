# Tasks: Repository Use Case Diagram

**Input**: Design documents from `/specs/023-repository-use-case-diagram/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/use-case-diagram.md, quickstart.md

## Phase 1: Setup

**Goal:** N/A for this feature — no new package, dependency, or vendored asset is needed. The `doc_generator` package, its test directories, `entry_point_diagram.py` (022), and the vendored `mermaid.min.js` (013) already exist and are reused/lightly extended.

*(No tasks in this phase.)*

## Phase 2: Foundational

**Goal:** Add the one new `PageKind` value and the fixed page-id/output-path helpers every other task needs to address the use-case-diagram page, per `data-model.md`'s `PageKind` extension and `contracts/use-case-diagram.md`.

**Independent test criteria:** `links.use_case_diagram_page_id()` and `links.use_case_diagram_output_paths()` return the fixed id/paths from `contracts/use-case-diagram.md` (`diagram:use-case-overview`, `diagrams/use-case-overview.md`/`.html`); `"use-case-diagram"` is a valid `DocPage.kind`.

- [X] T001 [P] Extend the `PageKind` literal in `src/doc_generator/models.py` to include `"use-case-diagram"`, per `data-model.md`'s `PageKind` extension.
- [X] T002 [P] Add `use_case_diagram_page_id()` (returns the fixed id `"diagram:use-case-overview"`) and `use_case_diagram_output_paths()` (returns the fixed pair `("diagrams/use-case-overview.md", "diagrams/use-case-overview.html")`) to `src/doc_generator/links.py`, mirroring the existing `class_diagram_page_id()`/`class_diagram_output_paths()` helpers, per `contracts/use-case-diagram.md` and `research.md` Decision 5.

**Checkpoint**: Foundation ready — user story implementation can now begin.

## Phase 3: User Story 1 - View the repository's use-case diagram

**Goal:** Generate a single, repository-wide use-case diagram (one shared actor per exposure kind — CLI, API, or generic fallback — each linked to every entry point of that kind, shown as its own use case) and link it from the wiki's home page, fully wired into incremental regeneration. Consumes 022's `identify_entry_points()` unmodified — no new entry-point detection.

**Independent test criteria:** `quickstart.md` Scenario A — against a fixture repository exposing at least one CLI command and one API route handler, the generated diagram shows two distinct actor nodes (CLI, API), each connected to its own use-case node, and the home page links to the diagram page (SC-001).

### Selection layer

- [X] T003 [P] [US1] Create `src/doc_generator/use_case_diagram.py` with the `Actor`, `UseCase`, and `UseCaseDiagramSelection` dataclasses (per `data-model.md`) and `select_use_cases(bundle: RepositoryBundle, graph: DependencyGraph) -> UseCaseDiagramSelection`: calls `entry_point_diagram.identify_entry_points(bundle, graph)` exactly once, unmodified (`research.md` Decision 1); returns `UseCaseDiagramSelection()` (both `actors` and `useCases` empty) when it returns `()`; otherwise builds one `UseCase` per entry point (`entryPointStableKey`, label `Module[.Class].name` per Decision 4, `actorKind` = the entry point's `EntryPointKind`) preserving `identify_entry_points()`'s existing deterministic order, and one `Actor` per distinct `EntryPointKind` present, in fixed canonical order (`"cli-command"` → label `"CLI"`, `"api-route"` → label `"API"`, `"function"` → label `"External Caller"`, per Decision 3) — never one actor per individual entry point.
- [X] T004 [US1] Add the `UseCaseDiagramSource` dataclass and `build_use_case_diagram_mermaid_source(selection: UseCaseDiagramSelection) -> UseCaseDiagramSource` to the existing `src/doc_generator/mermaid_diagram.py`: emits a `flowchart LR` block using the same UML-use-case-diagram workaround already used by `docs/diagrams/use-case-diagram.md` (`research.md` Decision 2) — one oval actor node per `selection.actors` entry (synthetic id `a0`, `a1`, ...) placed outside a system-boundary `subgraph`, one oval use-case node per `selection.useCases` entry (synthetic id `u0`, `u1`, ...) placed inside it, followed by one plain `-->` arrow per use case from its actor's synthetic id to its own — no `include`/`extend`-labeled edges. Sanitize every label against a literal `"` via the existing `_escape_label` helper. Depends on T003 for the `UseCaseDiagramSelection` shape.
- [X] T005 [P] [US1] Add a unit test `tests/unit/test_use_case_diagram.py` for `select_use_cases`: hand-built `RepositoryBundle`/`DependencyGraph` (no fixture files, mirroring `tests/unit/test_entry_point_diagram.py`'s style) asserting — a CLI-decorated function and an API-decorated function produce two distinct actors (`"CLI"`, `"API"`), each with exactly one use case; a plain uncalled function produces a use case whose `actorKind` is `"function"`, connected to the single generic `"External Caller"` actor; two CLI-decorated functions produce two `UseCase`s that both reference the *same* single CLI actor, not two separate CLI actors; a bundle/graph with zero qualifying entry points returns `UseCaseDiagramSelection()` (both `actors == ()` and `useCases == ()`); `selection.actors` is always ordered CLI, then API, then generic, regardless of the entry points' encounter order. Depends on T003.
- [X] T006 [P] [US1] Add unit tests to `tests/unit/test_mermaid_diagram.py` for `build_use_case_diagram_mermaid_source`: valid non-empty `flowchart LR` text; one actor node and one use-case node per selection entry, with synthetic ids assigned in `selection.actors`/`selection.useCases` order; exactly one `-->` line per use case, each pointing from its actor's synthetic id to its own use-case synthetic id; an actor or use-case label containing a literal `"` is sanitized (no bare unescaped `"` reaching `sourceText`). Depends on T004.
- [X] T007 [US1] Create `src/doc_generator/templates/use_case_diagram.md.jinja` embedding the ` ```mermaid ` fenced block (`use_case_diagram_source.sourceText`), mirroring `class_diagram.md.jinja`'s minimal structure. Depends on T004.

### Wiring

- [X] T008 [US1] Implement `DocGenerator.generateUseCaseDiagramPage() -> DocPage | None` in `src/doc_generator/generator.py`: calls `use_case_diagram.select_use_cases` then, only if `selection.useCases` is non-empty, `mermaid_diagram.build_use_case_diagram_mermaid_source` (the same two-step call shape `generateClassDiagramPage` already uses), returning `None` for an empty selection; otherwise builds a `DocPage` of kind `"use-case-diagram"` at `links.use_case_diagram_page_id()`/`links.use_case_diagram_output_paths()`, rendered via `use_case_diagram.md.jinja` (T007), per `contracts/use-case-diagram.md`. Depends on T001, T002, T003, T004, T007.
- [X] T009 [US1] Wire `generateUseCaseDiagramPage()` into `DocGenerator.generateRepositoryDocumentation` in `src/doc_generator/generator.py` (called once per run, not per module or per entry point; written only when it returns a page) and into `DocGenerator.generateOverviewPage`/`src/doc_generator/templates/home.md.jinja` to add a `[View the repository use-case diagram]` link only when the page exists, mirroring the existing `class_diagram_link` pattern exactly, per spec FR-007 and the brief's "Une seule page, liée depuis la page d'accueil du wiki généré." Once this page is included in `doc_set.pages`, the existing generic `tests/integration/test_mermaid_diagram.py::test_no_cdn_reference_and_classic_script_tag` (which iterates `for page in doc_set.pages`, not a fixed page-kind list) automatically asserts zero `http://`/`https://` references and a local, non-CDN Mermaid script tag for the new page kind too — this is what satisfies spec SC-004; no new network-check test is needed. Depends on T008.
- [X] T010 [US1] Extend `compute_regeneration_impact` in `src/doc_generator/impact.py` per `research.md` Decision 6: reuse the entry-point list `impact.py` already computes for 022's sequence-diagram invalidation (no second `identify_entry_points()` call); add `links.use_case_diagram_page_id()` to `impactedPageIds` whenever that list is non-empty and (`direct_symbol_ids` or `changed_dependency_edge_ids`) is non-empty this run — the same condition already used for the class diagram's `has_any_class` check. Include the page id in `current_page_ids` only when the entry-point list is non-empty, so the existing `removedPageIds` mechanism naturally covers "the repository went from having entry points to having none" with no further change needed. Depends on T002.

### Integration tests

- [X] T011 [P] [US1] Add `tests/integration/test_use_case_diagram.py` (new file, extending `_doc_generator_support.build_indexed_repo`'s alpha/beta/gamma fixture with one `@app.command()`-decorated function and one `@app.get(...)`-decorated function, mirroring 022's decorator-fixture pattern) asserting a full generation run produces a use-case-diagram page containing two distinct actor nodes (`CLI`, `API`), each connected by its own arrow to its own use-case node, and that the home page links to it (US1 Acceptance Scenario 1, SC-001). Depends on T009.
- [X] T012 [P] [US1] Add an integration test (same file) asserting: a plain, uncalled function entry point already present in the fixture (`alpha_entry`) connects to the single generic `"External Caller"` actor, not `CLI`/`API` (Acceptance Scenario 2, FR-004); two entry points of the same kind (the fixture's two CLI-decorated functions, or two API-decorated functions) both connect to the *same* single actor node rather than duplicating it (Acceptance Scenario 3). Depends on T009.
- [X] T013 [US1] Add an integration test (same file) asserting a repository with zero identifiable entry points (reusing 022's "zero entry points" fixture pattern — a mutually-calling pair with no CLI/API decoration) produces no use-case-diagram page, and the home page contains no broken/dead link to one (FR-005, Edge Case). Depends on T009.
- [X] T014 [US1] Add an integration test (same file) asserting incremental regeneration: after a full run, adding a new `@app.get(...)`-decorated function to the fixture followed by `generateRepositoryDocumentation(incremental=True, ...)` regenerates the use-case-diagram page and shows a new use-case node connected to the existing `API` actor (SC-005), mirroring `test_doc_generator_links.py`'s incremental-impact test pattern. Depends on T010, T011.

**Checkpoint**: At this point, User Story 1 (the only story in this feature) is fully functional and independently testable — this is also the complete feature.

## Phase 4: Polish & Cross-Cutting Concerns

**Goal:** Confirm the Mermaid output is actually parseable (not just plausible-looking), the quickstart passes end to end, and this repository's own documentation stays in sync with the new capability.

**Independent test criteria:** The generated `flowchart` block for a label containing a literal `"` parses cleanly (no bare unescaped `"` inside a node's oval brackets, balanced brackets, valid `flowchart LR` header); `quickstart.md`'s five scenarios pass end to end; `docs/diagrams/`, `docs/architecture.md`, and `README.md` accurately describe the new capability.

- [X] T015 [P] Add an integration test (`tests/integration/test_use_case_diagram.py`) asserting the Mermaid output for an actor/use-case label containing a literal `"` is well-formed (no bare unescaped `"`, balanced `[`/`(`/brackets, valid `flowchart LR` header) — same hand-built-selection level as T006, matching 021's T014 precedent and its documented rationale for not adding a permanent Node/mermaid-parser test dependency.
- [X] T016 Validate the end-to-end flow against `specs/023-repository-use-case-diagram/quickstart.md` (all five scenarios) and fix any mismatches across `src/doc_generator/`.
- [X] T017 Update `docs/diagrams/class-diagram.md` (add `Actor`/`UseCase`/`UseCaseDiagramSelection`/`UseCaseDiagramSource` and their relationships to the `DocGeneratorPackage` namespace), `docs/architecture.md` (note the new repository-wide use-case-diagram capability in the `doc_generator` layer's description), and `README.md` (feature list / documentation table) per this project's diagrams-maintenance convention (root `README.md`, `docs/architecture.md`, `docs/stack.md`, `docs/diagrams/` must stay in sync with every implemented feature).

## Dependencies

- `T001` and `T002` have no dependencies and can start immediately, in parallel (different files).
- `T003` has no dependency on T001/T002 — `use_case_diagram.py`'s `select_use_cases` needs only `RepositoryBundle`/`DependencyGraph` (passed through to `identify_entry_points`), not the page-id plumbing.
- `T004` depends on `T003` for the `UseCaseDiagramSelection` shape it consumes.
- `T005` depends on `T003`; `T006` depends on `T004` — both are pure unit tests and can run in parallel with each other.
- `T007` depends on `T004` (needs `UseCaseDiagramSource`'s field names).
- `T008` depends on `T001`, `T002`, `T003`, `T004`, and `T007` (assembles all of them into one page).
- `T009` depends on `T008`.
- `T010` depends on `T002` only (needs the page id, not the page itself).
- `T011` and `T012` depend on `T009`; can run in parallel (independent test functions in the same new file, though as tasks they touch the same file so treat as sequential edits).
- `T013` depends on `T009`.
- `T014` depends on `T010` and `T011` (needs both the impact-tracking change and the base fixture-driven test setup already in the file).
- `T015` depends on `T006` (label sanitization) and `T011` (a working generation pipeline to source real output from).
- `T016` is a final validation after `T007` through `T015`.
- `T017` can start once the feature's shape is stable (after `T009`) and has no code dependency.

## Parallel Execution Examples

### Foundational

```text
Task: T001 -> extend PageKind in src/doc_generator/models.py
Task: T002 -> add use_case_diagram_page_id/use_case_diagram_output_paths in src/doc_generator/links.py
```

### User Story 1

```text
Task: T005 -> unit test select_use_cases in tests/unit/test_use_case_diagram.py
Task: T006 -> unit test build_use_case_diagram_mermaid_source in tests/unit/test_mermaid_diagram.py
```

## Implementation Strategy

1. Complete the two tiny Foundational tasks (T001, T002) — nothing else is blocked long by them, but the final page-assembly step (T008) needs both.
2. Build the selection/rendering pair (T003, T004) and their unit tests (T005, T006) first — this is the feature's actual logic and is fully testable against hand-built fixtures without touching `generator.py`, exactly like `class_diagram.py`/`entry_point_diagram.py` already are for their own diagrams. `select_use_cases` itself is a thin wrapper around 022's already-tested `identify_entry_points`, so its own tests focus on actor derivation/grouping, not entry-point detection.
3. Add the template (T007) and wire everything into `DocGenerator` (T008, T009) — this is the only slice needed to make the feature visible in a generated wiki, and is this feature's entire MVP (there is only one user story).
4. Extend incremental regeneration (T010) and verify it, along with the CLI/API-distinct-actor, generic-fallback, shared-actor, and zero-entry-point scenarios, with integration tests (T011-T014).
5. Finish with real-parser-adjacent Mermaid validation (T015), a full quickstart pass (T016), and the repository's own documentation sync (T017).
