# Tasks: Local Wiki Documentation Generator

## Phase 1: Setup

**Goal:** Create the `doc_generator` package scaffolding and declare its new dependencies.

**Independent test criteria:** The new `src/doc_generator` package can be imported and exposes the core page/documentation-set types without side effects.

- [X] T001 [P] Add `Jinja2` and `markdown` dependencies to `pyproject.toml`, and create the `src/doc_generator/` package skeleton (`__init__.py`, `templates/` directory).
- [X] T002 [P] Create `src/doc_generator/models.py` with `DocPage`, `PageLink`, `DocumentationSet`, `PageManifestEntry`, and `RegenerationImpactSet` dataclasses as defined in `specs/012-wiki-doc-generator/data-model.md`.

## Phase 2: Foundational

**Goal:** Build the shared rendering, linking, manifest, and writing infrastructure every page kind depends on.

**Independent test criteria:** A hand-built `DocPage` can be rendered to Markdown and HTML, resolved into `PageLink`s, and written to a documentation folder through the manifest-tracked writer.

- [X] T003 Create `src/doc_generator/links.py` with deterministic page-id derivation (`kind` + `sourceEntityId`) and `PageLink` resolution that drops any target no longer present in repository metadata.
- [X] T004 Create `src/doc_generator/manifest_store.py` with a new SQLite page-manifest table (reusing the existing `repository_metadata` sqlite connection pattern) and load/save/list helpers for `PageManifestEntry` rows, including the managed output-path set per page.
- [X] T005 Create `src/doc_generator/markdown_render.py` with a Jinja2 `Environment` loading `src/doc_generator/templates/` and a `render_markdown_template(template_name, **context)` helper.
- [X] T006 [P] Create `src/doc_generator/templates/layout.html.jinja`, a base HTML layout (nav/header/footer) for the rendered site.
- [X] T007 Create `src/doc_generator/html_render.py` that converts a `DocPage.contentMarkdown` to HTML and wraps it with `templates/layout.html.jinja` to produce `renderedHtml`.
- [X] T008 Create `src/doc_generator/writer.py` with `DocumentationWriter.write_page(DocPage)` that writes the Markdown and HTML files under a given `outputRoot`, records the written paths via `manifest_store`, and refuses to write outside `outputRoot`.

**Checkpoint**: Foundation ready - user story implementation can now begin.

## Phase 3: User Story 1 - Browse the project architecture from a home page

**Goal:** Produce a home page that lists the project's real modules and dependency structure, with links to every module and diagram page.

**Independent test criteria:** Calling `DocGenerator.generateOverviewPage(repository)` returns a `DocPage` whose content lists the sample repository's actual modules, and writing that page produces an openable home page (Markdown + HTML).

- [X] T009 [P] [US1] Create `src/doc_generator/templates/home.md.jinja` rendering the project name, module list, and dependency overview.
- [X] T010 [US1] Create `src/doc_generator/generator.py` with the `DocGenerator` class constructor (`metadataStore`, `dependencyGraph`, `manifestStore`, `outputRoot`) and implement `generateOverviewPage(repository: Repository) -> DocPage` using `RepositoryMetadataStore.load_repository(...)` and `links.py` for module/diagram page links.
- [X] T011 [US1] Create `src/doc_generator/__init__.py` exporting `DocGenerator` and the `doc_generator` public model types.
- [X] T012 [US1] Wire `generateOverviewPage` output through `DocumentationWriter` in `src/doc_generator/generator.py` so a generated home page (Markdown + HTML) can be written and opened directly.

**Checkpoint**: At this point, the home page should be fully generatable and browsable independently.

## Phase 4: User Story 2 - Read a module's role, symbols, and summaries

**Goal:** Produce one page per module listing its role and its classes/functions with their generated summaries.

**Independent test criteria:** Calling `DocGenerator.generateModulePage(moduleSymbol)` returns a `DocPage` that lists the module's actual classes/functions and shows each symbol's generated summary, or an explicit "summary pending" marker when one is missing.

- [X] T013 [P] [US2] Create `src/doc_generator/templates/module.md.jinja` rendering a module's role, its classes/functions, and each symbol's `generatedSummary`, with an explicit "summary pending" marker when missing.
- [X] T014 [US2] Implement `generateModulePage(moduleSymbol: ModuleSymbol) -> DocPage` in `src/doc_generator/generator.py`, sourcing classes/functions and summaries from the module's `SourceFileBundle` and resolving `relatedSymbols` links via `links.py`.
- [X] T015 [US2] Handle modules with no classes/functions and modules with colliding names across directories/languages in `src/doc_generator/generator.py` and `src/doc_generator/links.py`, per `spec.md` Edge Cases, so each still gets an unambiguous page.

**Checkpoint**: At this point, the home page and module pages should both work independently, with the home page linking to real module pages.

## Phase 5: User Story 3 - Navigate dependency diagrams like a wiki

**Goal:** Produce one page per module's dependency diagram, linked to and from its module page and the home page.

**Independent test criteria:** Calling `DocGenerator.generateDependencyDiagramPage(diagram)` returns a `DocPage` showing the diagram's modules and edges, each module page links back to the diagram page(s) that reference it, and the home page links to every diagram page.

- [X] T016 [P] [US3] Create `src/doc_generator/diagrams.py` building one `DiagramExport` per module (its direct dependency neighborhood) using `dependency_graph.queries.filter_edges`/`ordered_nodes` and `dependency_graph.export.build_diagram_export`.
- [X] T017 [P] [US3] Create `src/doc_generator/templates/diagram.md.jinja` rendering a `DiagramExport`'s modules and edges with links to each module's page.
- [X] T018 [US3] Implement `generateDependencyDiagramPage(diagram: DiagramExport) -> DocPage` in `src/doc_generator/generator.py`.
- [X] T019 [US3] Add bidirectional links between `generateModulePage` and `generateDependencyDiagramPage` output in `src/doc_generator/generator.py` so each module page links to the diagram page(s) that reference it.
- [X] T020 [US3] Wire `generateOverviewPage`'s diagram links in `src/doc_generator/generator.py` to the diagram pages produced by `generateDependencyDiagramPage`, completing the home page's required links to every dependency diagram page.

**Checkpoint**: All three page kinds (home, module, diagram) should now be fully cross-linked and independently browsable.

## Phase 6: User Story 4 - Regenerate only impacted pages after incremental re-indexing

**Goal:** Regenerate only the pages affected by a re-indexed change instead of the entire documentation set.

**Independent test criteria:** After an incremental re-index affecting one module, `DocGenerator.generateRepositoryDocumentation(..., incremental=True, ...)` rewrites only that module's page, its diagram page, and any page linking to them, while every other previously generated page and manifest entry stays unchanged.

- [X] T021 [US4] Create `src/doc_generator/impact.py` computing `RegenerationImpactSet` from changed file/symbol ids, changed dependency edges (edges added/removed since the last run, per `spec.md`'s Incremental Regeneration FR), `dependency_graph.DependencyGraph.dependents(...)`, and the manifest store's stored `PageManifestEntry` set, following the same impact-propagation approach as `repository_metadata/summary_pipeline.py`'s `ImpactedSymbolSet` computation. A diagram page must be marked impacted whenever one of its module's edges changed, even if neither endpoint symbol's own content changed.
- [X] T022 [US4] Implement `generateRepositoryDocumentation(repositoryRoot, *, incremental=True, changedPaths=(), changedSymbolIds=()) -> DocumentationSet` in `src/doc_generator/generator.py`, orchestrating `generateOverviewPage`/`generateModulePage`/`generateDependencyDiagramPage` and `DocumentationWriter` for a full run.
- [X] T023 [US4] Extend `generateRepositoryDocumentation` in `src/doc_generator/generator.py` to compute a `RegenerationImpactSet` on incremental runs and regenerate only impacted pages (plus pages whose links would otherwise become inconsistent), leaving unaffected `PageManifestEntry` rows and files untouched.
- [X] T024 [US4] Limit home page regeneration in `src/doc_generator/generator.py` to incremental runs where the module list or dependency structure it presents actually changed.

**Checkpoint**: Full and incremental documentation generation should both work end to end.

## Phase 7: User Story 5 - Export versionable documentation into the analyzed repository

**Goal:** Guarantee the generated documentation stays isolated to its own folder, is plain-text and diff-friendly, and never disturbs files it does not manage.

**Independent test criteria:** Generating documentation for a sample repository writes only inside the configured documentation folder, never modifies a file elsewhere in the repository, and leaves a manually added file inside the documentation folder untouched across a re-run.

- [X] T025 [US5] Enforce in `src/doc_generator/writer.py` that `DocumentationWriter` only creates, overwrites, or removes files recorded in its own manifest-tracked managed set, leaving any manually added or unrelated file inside `outputRoot` untouched.
- [X] T026 [US5] Add an `outputRoot` containment guard in `src/doc_generator/writer.py` that rejects any resolved output path falling outside the configured documentation folder, and validate that `outputRoot` is kept separate from the analyzed repository's detected source folders in `src/doc_generator/generator.py`.
- [X] T027 [US5] Add an integration validation in `tests/integration/test_doc_generator_export.py` that generates documentation for a sample repository and asserts every file lives under `outputRoot`, no source file elsewhere in the repository was modified, and a manually added file in `outputRoot` survives a re-run.

**Checkpoint**: All five user stories should now be independently functional and safe to run against a real repository.

## Phase 8: Polish & Cross-Cutting Concerns

**Goal:** Make the documentation generator easy to consume and verify from the rest of the codebase.

**Independent test criteria:** The feature's public API is coherent, the quickstart scenarios match the implementation, and the full generated documentation set has zero broken links.

- [X] T028 [P] Update `src/doc_generator/__init__.py` for stable public exports of `DocGenerator`, `DocPage`, `DocumentationSet`, and `RegenerationImpactSet`.
- [X] T029 Validate the end-to-end generation flow against `specs/012-wiki-doc-generator/quickstart.md` and fix any mismatches across `src/doc_generator/`.
- [X] T030 Add an integration validation in `tests/integration/test_doc_generator_links.py` that generates a full `DocumentationSet` for a sample repository, asserts zero broken `PageLink`s across the home page, every module page, and every diagram page, then changes one module and re-runs `generateRepositoryDocumentation` incrementally, and re-asserts zero broken `PageLink`s across the entire regenerated documentation set, per `spec.md`'s "links must remain valid after a partial, incremental regeneration" requirement and `quickstart.md`'s incremental-regeneration validation steps.

## Dependencies

- `T001` and `T002` can run in parallel.
- `T003` through `T008` depend on the package scaffolding and models from Phase 1.
- `T006` can run in parallel with `T003`, `T004`, and `T005`.
- `T007` depends on `T005` and `T006`.
- `T008` depends on `T004` and `T007`.
- `T009` can run in parallel with `T010` and `T011` (different files); `T010` depends on `T003`, `T004`, and `T005`.
- `T011` depends on `T010`.
- `T012` depends on `T008`, `T009`, `T010`, and `T011`.
- `T013` can run in parallel with `T016` and `T017` (different files).
- `T014` depends on `T003`, `T010`, and `T013`.
- `T015` depends on `T014`.
- `T016` depends on `T003`.
- `T017` depends on `T005`.
- `T018` depends on `T016` and `T017`.
- `T019` depends on `T014` and `T018`.
- `T020` depends on `T010` and `T018`.
- `T021` depends on `T004` and `T016`.
- `T022` depends on `T012`, `T014`, `T018`, `T019`, and `T020`.
- `T023` depends on `T021` and `T022`.
- `T024` depends on `T023`.
- `T025` and `T026` depend on `T008` and `T023`.
- `T027` depends on `T025` and `T026`.
- `T028` depends on `T010` through `T024`.
- `T029` is a final validation after `T028`.
- `T030` depends on `T028` and specifically on `T023` and `T024` (the
  incremental regeneration path it now also exercises).

## Parallel Execution Examples

### User Story 1

```text
Task: T009 -> create home.md.jinja in src/doc_generator/templates/home.md.jinja
Task: T010 -> implement DocGenerator.generateOverviewPage in src/doc_generator/generator.py
```

### User Story 2

```text
Task: T013 -> create module.md.jinja in src/doc_generator/templates/module.md.jinja
Task: T014 -> implement DocGenerator.generateModulePage in src/doc_generator/generator.py
```

### User Story 3

```text
Task: T016 -> build per-module DiagramExport in src/doc_generator/diagrams.py
Task: T017 -> create diagram.md.jinja in src/doc_generator/templates/diagram.md.jinja
```

## Implementation Strategy

1. Build the package scaffolding, data model, and shared rendering/linking/manifest/writer infrastructure first so every page kind has a stable foundation.
2. Add the home page (US1) as the MVP slice - it proves the repository metadata can drive a real, browsable page.
3. Add module pages (US2) so the wiki carries the actual documentation payload: roles, symbols, and summaries.
4. Add diagram pages and bidirectional linking (US3) to complete wiki-style navigation across all three page kinds.
5. Add incremental regeneration (US4) once the full generation path is proven, so impact computation has real pages and a real manifest to reason about.
6. Harden folder isolation and non-destructive writing (US5) last, then validate the whole flow against quickstart.md and check for zero broken links.