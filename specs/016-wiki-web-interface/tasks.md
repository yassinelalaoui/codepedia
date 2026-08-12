# Tasks: Wiki Web Interface

## Phase 1: Setup

**Goal:** Stand up the `frontend/` npm project and the small `doc_generator` change every downstream task needs.

**Independent test criteria:** `npm run build` in `frontend/` produces a classic (non-module), IIFE-format bundle targeting `src/doc_generator/assets/`; `attr_list` is registered as a markdown extension.

- [X] T001 Initialize the `frontend/` npm project (`package.json`, `tsconfig.json`, `vite.config.ts`) with `react`, `react-dom`, `typescript`, `vite`, `vitest`, `@testing-library/react` as dependencies, and Vite's build configured for a classic (non-`type="module"`) IIFE bundle output to `../src/doc_generator/assets/wiki-ui.js`/`wiki-ui.css`, per `research.md` Decision 2 and Decision 8.
- [X] T002 [P] Add `"attr_list"` to `_MARKDOWN_EXTENSIONS` in `src/doc_generator/html_render.py`, per `research.md` Decision 7.

## Phase 2: Foundational

**Goal:** Build the search index, the vendored bundle plumbing, and the shared layout mount points every user story depends on.

**Independent test criteria:** `build_search_index(...)` returns entries whose anchors match real rendered heading ids; `search-index.json` and the vendored bundle both exist under `outputRoot` after generation; every generated page has `#wiki-search-root`/`#wiki-chat-root` containers and loads the bundle via a classic script tag.

- [X] T003 Give each function/class/method heading in `src/doc_generator/templates/module.md.jinja` an explicit `{: #<symbol-id-slug> }` attribute derived from that symbol's existing stable id, per `research.md` Decision 7. Depends on T002.
- [X] T004 Create `src/doc_generator/search_index.py` with `SearchIndexEntry`/`SearchIndexDocument` dataclasses and a `build_search_index(...)` function that produces one entry per documented module/class/method/function (name, kind, symbolId, filePath, `pageUrl` with the same anchor T003's headings render, per `contracts/search-index.md`), omitting any symbol whose owning page cannot currently be resolved. Depends on T003.
- [X] T005 Extend `src/doc_generator/writer.py` with `ensure_wiki_ui_assets()` (copies `wiki-ui.js`/`wiki-ui.css` into `outputRoot/assets/`, mirroring `ensure_mermaid_asset()`) and a way to write `search-index.json` as a regular writer-managed generated file (content-hash compared like a page, not a static vendored asset), per `data-model.md`.
- [X] T006 Wire `build_search_index(...)` + writing `search-index.json` + `ensure_wiki_ui_assets()` into `generateRepositoryDocumentation` in `src/doc_generator/generator.py`, so both exist after any full or incremental generation run that writes at least one page. Depends on T004, T005.
- [X] T007 [P] Update `src/doc_generator/templates/layout.html.jinja` to load the vendored `wiki-ui.css` (`<link rel="stylesheet">`) and `wiki-ui.js` (classic `<script>`, loaded after the containers) and add `<div id="wiki-search-root"></div>` / `<div id="wiki-chat-root"></div>`, per `contracts/ui-mount-points.md`. Depends on T005 (script/style href computation mirrors `mermaid_script_href`).
- [X] T008 Create `frontend/src/main.tsx` (mounts placeholder `SearchWidget`/`ChatPanel` into the two containers) and `frontend/src/lib/searchIndex.ts` (fetches and parses `assets/search-index.json`, exposing a query function; renders a clear unavailable state on fetch failure), per `contracts/ui-mount-points.md`. Depends on T001, T007.

**Checkpoint**: Foundation ready - user story implementation can now begin.

## Phase 3: User Story 1 - Understand the project from the home page

**Goal:** Present a real architecture overview on the wiki's home page.

**Independent test criteria:** The generated home page includes an architecture summary (module/symbol counts, grouping) beyond the existing flat module list, and links to every module's documentation page.

- [X] T009 [US1] Extend `generateOverviewPage` in `src/doc_generator/generator.py` to compute an architecture summary (module count, symbol count, simple grouping) from the current bundle and pass it into the home page's render context, per `research.md` Decision 6.
- [X] T010 [US1] Update `src/doc_generator/templates/home.md.jinja` to render the architecture summary above the existing module list, keeping the module list intact. Depends on T009.
- [X] T011 [US1] Add a unit test in `tests/unit/test_doc_generator_home_overview.py` asserting the generated home page's content includes the architecture summary fields for a known sample repository. Depends on T010.

**Checkpoint**: At this point, the home page presents a real architecture overview, independently of search (US2), diagram navigation (US3), or the chat panel (US4).

## Phase 4: User Story 2 - Find a specific symbol or function quickly

**Goal:** Let a user search for a symbol/function by name from anywhere in the wiki and land on its exact page location.

**Independent test criteria:** Typing a known symbol name into the search widget shows a matching result with disambiguating context; selecting it navigates to the correct page and anchor; an unmatched query shows a clear "no results" message.

- [X] T012 [US2] Implement the query/match logic in `frontend/src/lib/searchIndex.ts` (substring match over `name` and `filePath`, ranked results, enough context per result to disambiguate similarly named matches), per `contracts/search-index.md`. Depends on T008.
- [X] T013 [US2] Implement `frontend/src/components/SearchWidget.tsx` (input box, live-filtered results list using T012's query function, a clear "no results" state), per `spec.md` US2 acceptance criteria. Depends on T012.
- [X] T014 [US2] Add a Vitest component test in `frontend/tests/SearchWidget.test.tsx` verifying: typing a query filters results, selecting a result navigates to its `pageUrl`, and a query with no match shows the "no results" message. Depends on T013.
- [X] T015 [US2] Add a unit test in `tests/unit/test_search_index.py` asserting `build_search_index(...)` (T004) produces entries whose anchors match the real ids `module.md.jinja` (T003) renders for a known sample repository, and that a symbol whose page cannot be resolved is omitted rather than given a broken `pageUrl`. Depends on T004.

**Checkpoint**: At this point, US1 and US2 both work independently — a user can read the home page and search for a symbol by name.

## Phase 5: User Story 3 - Explore a module's dependencies visually

**Goal:** Confirm dependency-diagram click navigation (013, unchanged) still works correctly alongside the new search/chat mount points, and that those mount points render on every page kind reached directly, not only via the home page.

**Independent test criteria:** A generated diagram page still contains a working Mermaid `click` navigation directive, and also contains the new search/chat mount points and script tags, with neither interfering with the other; a module page opened directly (without navigating from the home page) also carries the same mount points and script/style references.

- [X] T016 [US3] Add an integration test in `tests/integration/test_wiki_ui_assets.py` (new file) generating documentation for a repository with dependent modules and asserting a diagram page's rendered HTML contains both a working Mermaid `click` directive (per `specs/013-interactive-dependency-diagram/contracts/mermaid-diagram-render.md`) and the `#wiki-search-root`/`#wiki-chat-root` containers, per `contracts/ui-mount-points.md` "Non-collision with existing content". Depends on T007.

**Checkpoint**: At this point, US1, US2, and US3 are all independently confirmed working together on the same generated pages.

## Phase 6: User Story 4 - Ask the chat a question and follow links to the cited code

**Goal:** Let a user ask a question in the chat panel and follow clickable citation links to the documented code they reference.

**Independent test criteria:** Submitting a question renders the generated answer; every citation with a resolvable search-index match renders as a working link; an unresolvable citation renders as a plain label; an API error renders a clear message.

- [X] T017 [US4] Implement `frontend/src/lib/chatApiClient.ts`: same-origin relative `fetch` wrappers for `POST /sessions`, `POST /sessions/{sessionId}/messages`, `GET /sessions/{sessionId}/messages`, per `research.md` Decision 4 and `specs/014-local-chat-api/contracts/chat-api.md`. Depends on T001.
- [X] T018 [US4] Implement `frontend/src/components/ChatPanel.tsx`: question input, message list, and citation-link resolution against `lib/searchIndex.ts`'s loaded data (matching `citedSymbolIds` first, then `citedFilePaths`, per `research.md` Decision 5), rendering a plain unlinked label when no match exists, and a clear error message for both 014's structured error responses and network-level failures, per `contracts/ui-mount-points.md`. Depends on T012, T017.
- [X] T019 [US4] Add Vitest component tests in `frontend/tests/ChatPanel.test.tsx` verifying: submitting a question renders the returned answer, a citation with a resolvable search-index match renders as a link, a citation with no match renders as a plain label, and a simulated API error renders a clear error message. Depends on T018.

**Checkpoint**: All four user stories are independently functional — home page, search, diagram navigation, and chat with citation links all work together.

## Phase 7: Polish & Cross-Cutting Concerns

**Goal:** Confirm the feature is fully self-contained and idempotent, build and commit the real bundle, and match the quickstart end to end.

**Independent test criteria:** No generated page references a CDN or a `type="module"` script; the vendored bundle and search index are present and stable across regenerations; the full quickstart flow works with the real, committed bundle.

- [X] T020 [P] Add an integration test in `tests/integration/test_wiki_ui_assets.py` asserting no `http://`/`https://` reference appears anywhere in generated page HTML (including the new bundle/stylesheet references) and that the bundle's `<script>` tag carries no `type="module"` attribute, per `research.md` Decision 2.
- [X] T021 [P] Add a test confirming a second, unchanged generation run does not rewrite `outputRoot/assets/wiki-ui.js`, `wiki-ui.css`, or `search-index.json` when their content is unchanged (writer idempotency), per `data-model.md` Validation.
- [X] T022 Run `npm run build` in `frontend/` and commit the resulting `wiki-ui.js`/`wiki-ui.css` into `src/doc_generator/assets/`, per `research.md` Decision 8. Depends on T013, T018 (both components must exist to build the real bundle).
- [X] T023 Validate the end-to-end flow against `specs/016-wiki-web-interface/quickstart.md` (home page overview, search, diagram navigation, chat panel with citation links, no-CDN/classic-script, bundle idempotency) using the real committed bundle from T022, and fix any mismatches across `frontend/` and `src/doc_generator/`. Depends on T011, T014, T015, T016, T019, T020, T021, T022, T024.
- [X] T024 [P] Extend `tests/integration/test_wiki_ui_assets.py` to assert that a **module** page's rendered HTML — generated and inspected independently of the home page or the diagram page — also contains the `#wiki-search-root`/`#wiki-chat-root` containers and the vendored bundle's classic `<script>`/`<link>` references, closing the E1 gap from `/speckit-analyze` (previously only verified on diagram pages via T016), per `spec.md`'s "open any specific module, diagram, or symbol page directly" requirement. Depends on T007.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories.
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion; can then proceed in parallel or in priority order (US1 → US2 → US3 → US4).
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### Task-Level Dependencies

- `T001` and `T002` have no dependencies and can run in parallel.
- `T003` depends on `T002`. `T004` depends on `T003`. `T005` has no dependency on `T003`/`T004` (different concern — asset copying and generic file writing).
- `T006` depends on `T004` and `T005`.
- `T007` depends on `T005` (needs the asset-href computation pattern) and can run in parallel with `T003`/`T004`/`T006`.
- `T008` depends on `T001` and `T007`.
- `T009` → `T010` → `T011` (US1, strictly sequential, same files/topic).
- `T012` depends on `T008`. `T013` depends on `T012`. `T014` depends on `T013`.
- `T015` depends on `T004` (and transitively `T003`).
- `T016` depends on `T007`. `T024` also depends on `T007` only, not on `T016` — both extend the same test file but assert on independent page kinds (diagram vs. module), so they can be written in parallel.
- `T017` depends on `T001`. `T018` depends on `T012` and `T017`. `T019` depends on `T018`.
- `T020`/`T021` depend on `T006` (need real generation output to inspect).
- `T022` depends on `T013` and `T018` (the components the bundle actually ships).
- `T023` is a final validation after every story's tasks, `T022`, and `T024`.

### Parallel Opportunities

- `T001`/`T002` (Setup).
- `T007` alongside `T003`/`T004`/`T006` (Foundational — different files).
- Once Foundational (`T008`) completes, `T009` (US1), `T012` (US2), `T016`/`T024` (US3, once `T007` lands), and `T017` (US4) can all start in parallel.
- `T020`/`T021` (Polish, independent checks).

## Parallel Execution Examples

### Setup

```text
Task: T001 -> initialize frontend/ npm project
Task: T002 -> add attr_list extension in src/doc_generator/html_render.py
```

### After Foundational completes

```text
Task: T009 -> extend generateOverviewPage in src/doc_generator/generator.py
Task: T012 -> search query/match logic in frontend/src/lib/searchIndex.ts
Task: T017 -> chat API client in frontend/src/lib/chatApiClient.ts
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories).
3. Complete Phase 3: User Story 1 - the home page presents a real architecture overview.
4. **STOP and VALIDATE**: Generated home page content includes the architecture summary.

### Incremental Delivery

1. Setup + Foundational → the search index, vendored bundle plumbing, and shared mount points all exist.
2. Add US1 (home page overview) → test independently → MVP.
3. Add US2 (search) → test independently — the feature's second explicit success criterion.
4. Add US3 (diagram navigation confirmation) → test independently — a regression guard proving 013's behavior survives the new mount points unchanged.
5. Add US4 (chat panel with citation links) → test independently — the feature's most complex piece, deliberately last since it depends on both the search index (US2) and the chat API (014) being solid.
6. Polish: build and commit the real bundle, lock in self-containment/idempotency, and run a full quickstart pass.
