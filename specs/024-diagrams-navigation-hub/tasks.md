# Tasks: Diagrams Navigation Hub

**Input**: Design documents from `/specs/024-diagrams-navigation-hub/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/diagrams-index-page.md, quickstart.md

## Phase 1: Setup

**Goal:** N/A for this feature — no new package, dependency, or vendored asset is needed. The `doc_generator` package and its existing `layout.html.jinja`/`html_render.py`/`generator.py`/`impact.py` are reused/lightly extended; `frontend/` is untouched.

*(No tasks in this phase.)*

## Phase 2: Foundational

**Goal:** Add the one new `PageKind` value, the new `RegenerationImpactSet` field, and the fixed page-id/output-path helpers every other task needs, per `data-model.md`'s `PageKind`/`RegenerationImpactSet` extensions and `contracts/diagrams-index-page.md`.

**Independent test criteria:** `links.diagrams_index_page_id()` and `links.diagrams_index_output_paths()` return the fixed id/paths from `contracts/diagrams-index-page.md` (`"diagrams-index"`, `("diagrams-index.md", "diagrams-index.html")`); `"diagrams-index"` is a valid `DocPage.kind`; `RegenerationImpactSet` has a `requiresDiagramsIndexRegeneration: bool = False` field (and `to_dict()` includes it).

- [X] T001 [P] In `src/doc_generator/models.py`: extend the `PageKind` literal to include `"diagrams-index"`, and add `requiresDiagramsIndexRegeneration: bool = False` to `RegenerationImpactSet` (including its `to_dict()` output), per `data-model.md`'s `PageKind`/`RegenerationImpactSet` extensions.
- [X] T002 [P] In `src/doc_generator/links.py`: add `DIAGRAMS_INDEX_PAGE_ID = "diagrams-index"`, `DIAGRAMS_INDEX_OUTPUT_MARKDOWN = "diagrams-index.md"`, `DIAGRAMS_INDEX_OUTPUT_HTML = "diagrams-index.html"` (unprefixed, sibling to `HOME_PAGE_ID`/`HOME_OUTPUT_MARKDOWN`/`HOME_OUTPUT_HTML` — this is a navigation page, not a diagram, so it does not use the `"diagram:"` id prefix), plus `diagrams_index_page_id() -> str` and `diagrams_index_output_paths() -> tuple[str, str]`, mirroring `class_diagram_page_id()`/`class_diagram_output_paths()`'s shape, per `data-model.md` and `research.md` Decision 1.

**Checkpoint**: Foundation ready — user story implementation can now begin.

## Phase 3: User Story 1 - Find any diagram without navigating module by module

**Goal:** Add one always-generated "Diagrams" page listing every diagram the wiki currently produces (class diagram, per-entry-point sequence diagrams, use-case diagram, per-module dependency diagrams — never a module's own documentation page), and a "Diagrams" link in the shared page nav so the page is reachable in one click from anywhere in the wiki, kept current after incremental regeneration.

**Independent test criteria:** `quickstart.md` Scenario A + Scenario B — against a fixture repository with several modules, at least one class, and at least one identified entry point, `diagrams-index.html` lists exactly one entry per existing diagram (grouped by category, no module-documentation entries), and every generated page's shared nav contains a working "Diagrams" link to it (SC-001, SC-002).

### Aggregation page

- [X] T003 [US1] Create `src/doc_generator/templates/diagrams_index.md.jinja`: renders up to four labeled sections in a fixed order — Class diagram, Use-case diagram, Entry point sequence diagrams, Module dependency diagrams — each rendered only when it has at least one entry (per `research.md` Decision 5); when every section is empty, renders an explicit "No diagrams yet" message instead of any section heading (`research.md` Decision 2, spec Edge Case).
- [X] T004 [US1] Implement `DocGenerator.generateDiagramsIndexPage(*, classDiagramPage: DocPage | None, useCaseDiagramPage: DocPage | None, entryPointPages: tuple[DocPage, ...], modules: tuple[ModuleSymbol, ...]) -> DocPage` in `src/doc_generator/generator.py`, per `contracts/diagrams-index-page.md`:
  - **Never returns `None`** (`research.md` Decision 2) — even with every input empty, returns a valid page whose content states there are no diagrams yet.
  - Assembles up to four groups of entries: one for `classDiagramPage` when not `None` (label `"Repository class diagram"`, matching `generateOverviewPage`'s own class-diagram link label exactly); one for `useCaseDiagramPage` when not `None` (label `"Repository use-case diagram"`); one per page in `entryPointPages`, in the given order (label = that page's own `.title`); one per module in `modules`, **sorted by module name** (label `f"{module.name} dependencies"`), with its target computed via `links.page_slug`/`links.diagram_output_paths`/`links.diagram_page_id` — the same per-module dependency-diagram identity `generateOverviewPage` already computes for its own "dependencies" link. Factor that shared identity computation out of `generateOverviewPage`'s inline code into one small private helper (e.g. `_dependency_diagram_identity(module) -> tuple[str, str, str]` returning `(page_id, output_path_markdown, output_path_html)`) reused by both methods, per `research.md` Decision 4 — never build a link to that module's own `"module"`-kind documentation page (FR-004).
  - Builds one `PageLink` per entry via `links.build_page_link(from_page_id=links.diagrams_index_page_id(), from_output_path_markdown=..., ...)`, and passes `links=tuple(...)` on the returned `DocPage` (needed for `impact.py`'s referrer-propagation).
  - Fixed identity: `id=links.diagrams_index_page_id()`, `outputPathMarkdown`/`outputPathHtml=links.diagrams_index_output_paths()`, `kind="diagrams-index"`, `sourceEntityId=""` (repository-wide, no single owning symbol, same as `generateClassDiagramPage`'s precedent).
  - Renders content via `diagrams_index.md.jinja` (T003).
  Depends on T001, T002, T003.

### Wiring

- [X] T005 [US1] Wire `generateDiagramsIndexPage()` into `DocGenerator.generateRepositoryDocumentation` in `src/doc_generator/generator.py`: compute the sorted module list once per run (same list `generateOverviewPage` already builds); call `generateDiagramsIndexPage(classDiagramPage=class_diagram_page, useCaseDiagramPage=use_case_diagram_page, entryPointPages=entry_point_pages, modules=modules)` **unconditionally every run** (mirrors how the home page is always computed, `research.md` Decision 2 — never gated behind `target_page_ids`); write it and append it to `pages` when `target_page_ids is None or impact.requiresDiagramsIndexRegeneration or links.diagrams_index_page_id() in target_page_ids`, mirroring exactly how `HOME_PAGE_ID` is added via `impact.requiresHomePageRegeneration` today. Depends on T004.
- [X] T006 [US1] Extend `compute_regeneration_impact` in `src/doc_generator/impact.py` per `research.md` Decision 6: compute `requiresDiagramsIndexRegeneration = True` whenever any of the following differ from the previous manifest snapshot (`entries`) — the current module-page-id set (reuse the same comparison `requiresHomePageRegeneration` already makes), the current sequence-diagram page-id set (`current_sequence_diagram_page_ids`, already computed in this function, vs. `{entry.pageId for entry in entries if entry.kind == "sequence-diagram"}`), whether a class-diagram page currently exists (`has_any_class`) vs. whether one existed previously (`links.class_diagram_page_id() in {entry.pageId for entry in entries}`), or whether a use-case-diagram page currently exists (`has_any_entry_point`) vs. previously (`links.use_case_diagram_page_id() in {entry.pageId for entry in entries}`); set this on the returned `RegenerationImpactSet`. Also add `links.diagrams_index_page_id()` **unconditionally** to `current_page_ids` (the diagrams-index page is always generated and must never appear in `removedPageIds` — `research.md` Decision 2, contract's "never a member of removedPageIds"). Depends on T001, T002.
- [X] T007 [US1] Add `diagrams_href` to `src/doc_generator/html_render.py`'s `render_page_html`, computed via the same `relative_output_link(from_output_path=output_path_html, to_output_path=...)` pattern already used for `home_href`, targeting `links.diagrams_index_output_paths()[1]`; pass it to `layout.html.jinja` alongside the existing `home_href`, per `research.md` Decision 3. Depends on T002.
- [X] T008 [US1] Add a second link, `<a href="{{ diagrams_href }}">Diagrams</a>`, inside the existing `<nav>` element in `src/doc_generator/templates/layout.html.jinja`, next to the existing Home link — present unconditionally on every generated page (home, module, diagram, class-diagram, sequence-diagram, use-case-diagram, diagrams-index itself), satisfying FR-002. Depends on T007.

### Integration tests

- [X] T009 [P] [US1] Add `tests/integration/test_diagrams_index.py` (new file, extending `_doc_generator_support.build_indexed_repo`'s alpha/beta/gamma fixture — or a similarly-shaped fixture — with at least one CLI/API-decorated entry point so every diagram category exists) asserting a full generation run produces a `"diagrams-index"` page containing exactly: one class-diagram entry, one use-case-diagram entry, one sequence-diagram entry per identified entry point, and one dependency-diagram entry per module — and that none of the page's `PageLink`s target a `"module"`-kind `DocPage` (US1 Acceptance Scenario 2, FR-003, FR-004). Depends on T005.
- [X] T010 [P] [US1] Add an integration test (same file) asserting the "Diagrams" link is present in the rendered HTML of every generated page kind in the fixture (home, a module page, the class-diagram page, a sequence-diagram page, the use-case-diagram page, and the diagrams-index page itself) and resolves to the diagrams-index page's own output path from each — FR-002, SC-002, and the spec's Edge Case ("reached from a diagram page... still lists every diagram, including the one currently open"). Depends on T008, T009.
- [X] T011 [US1] Add an integration test (same file) asserting a repository with modules but zero classes and zero identifiable entry points produces a diagrams-index page containing only the "Module dependency diagrams" section — no "Class diagram" or "Use-case diagram" heading at all, empty or otherwise (Acceptance Scenario 5, FR-006). Depends on T005.
- [X] T012 [US1] Add an integration test (same file) asserting a repository producing zero diagrams of any kind (e.g. zero modules) still produces a valid `diagrams-index` page with an explicit "no diagrams yet" message — never a missing file or a broken/empty page (spec Edge Case). Depends on T005.
- [X] T013 [US1] Add integration tests (same file) asserting incremental regeneration, one per independent branch of `requiresDiagramsIndexRegeneration` (`research.md` Decision 6) — after a full run: (a) adding a new module and regenerating with `incremental=True` adds a new dependency-diagram entry to the diagrams-index page without a full reindex (module-page-set branch); (b) removing the fixture's only class and regenerating with `incremental=True` removes the "Class diagram" section (class-diagram-existence branch); (c) adding a new identifiable entry point (e.g. a new `@app.command()`-decorated function, per spec Acceptance Scenario 4's own example) and regenerating with `incremental=True` adds a new sequence-diagram entry to the diagrams-index page (sequence-diagram-page-set branch); (d) removing the fixture's only entry point so the repository has zero entry points and regenerating with `incremental=True` removes the "Use-case diagram" section (use-case-diagram-existence branch). All four driven by `requiresDiagramsIndexRegeneration` (SC-003, FR-007), mirroring `test_doc_generator_links.py`'s incremental-impact test pattern. Depends on T006, T009.

**Checkpoint**: At this point, User Story 1 (the only story in this feature) is fully functional and independently testable — this is also the complete feature.

## Phase 4: Polish & Cross-Cutting Concerns

**Goal:** Confirm the quickstart passes end to end and this repository's own documentation stays in sync with the new capability.

**Independent test criteria:** `quickstart.md`'s five scenarios pass end to end; `docs/architecture.md`, `docs/diagrams/`, and `README.md` accurately describe the new capability.

- [X] T014 Validate the end-to-end flow against `specs/024-diagrams-navigation-hub/quickstart.md` (all five scenarios) and fix any mismatches across `src/doc_generator/`.
- [X] T015 Update `docs/diagrams/class-diagram.md` (add `generateDiagramsIndexPage()` to the `DocGenerator` class's method list in the `DocGeneratorPackage` namespace — no new dataclass is introduced, per `data-model.md`), `docs/architecture.md` (note the new always-reachable "Diagrams" navigation page in the `doc_generator` layer's description), and `README.md` (feature list) per this project's diagrams-maintenance convention (root `README.md`, `docs/architecture.md`, `docs/stack.md`, `docs/diagrams/` must stay in sync with every implemented feature).

## Dependencies

- `T001` and `T002` have no dependencies and can start immediately, in parallel (different files).
- `T003` has no dependency on T001/T002 — the template's variable shape doesn't need the page-id plumbing to be written first, but it does need `generateDiagramsIndexPage` (T004) to actually supply those variables, so in practice write it alongside/just before T004.
- `T004` depends on `T001`, `T002`, `T003` (assembles the page from the id/path helpers and renders via the template).
- `T005` depends on `T004`.
- `T006` depends on `T001` (needs the new field to exist) and `T002` (needs the page-id helper).
- `T007` depends on `T002` (needs `diagrams_index_output_paths()`).
- `T008` depends on `T007` (needs `diagrams_href` to exist in the template context).
- `T009` depends on `T005`.
- `T010` depends on `T008` and `T009` (needs both the nav link and a working generation pipeline to source pages from).
- `T011` and `T012` depend on `T005`; can run in parallel (independent test functions in the same new file, though as tasks they touch the same file so treat as sequential edits).
- `T013` depends on `T006` and `T009` (needs both the impact-tracking change and the base fixture-driven test setup already in the file).
- `T014` is a final validation after `T008` through `T013`.
- `T015` can start once the feature's shape is stable (after `T008`) and has no code dependency.

## Parallel Execution Examples

### Foundational

```text
Task: T001 -> extend PageKind + RegenerationImpactSet in src/doc_generator/models.py
Task: T002 -> add diagrams_index_page_id/diagrams_index_output_paths in src/doc_generator/links.py
```

### User Story 1

```text
Task: T009 -> integration test: full catalog in tests/integration/test_diagrams_index.py
Task: T010 -> integration test: nav link present on every page kind (after T009 lands)
```

## Implementation Strategy

1. Complete the two tiny Foundational tasks (T001, T002) — nothing else is blocked long by them, but the page-assembly step (T004) needs both.
2. Build the aggregation page itself (T003, T004) — this is the feature's actual content logic, reusing `generateOverviewPage`'s existing per-module identity computation via one small shared helper rather than duplicating it.
3. Wire everything into `DocGenerator` (T005), extend incremental regeneration (T006), and add the shared nav link (T007, T008) — this is the slice that makes the feature visible and reachable in the generated wiki, and is this feature's entire MVP (there is only one user story).
4. Verify the full catalog, nav-link reachability, omitted-category, zero-diagram, and incremental-regeneration behaviors with integration tests (T009-T013).
5. Finish with a full quickstart pass (T014) and the repository's own documentation sync (T015).
