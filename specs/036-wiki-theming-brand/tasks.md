---

description: "Task list for 036-wiki-theming-brand"
---

# Tasks: Wiki Theming and Brand Identity

**Input**: Design documents from `/specs/036-wiki-theming-brand/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/wiki-theme-shell.md](./contracts/wiki-theme-shell.md)

**Tests**: Included. The spec's Success Criteria are stated as verifiable
outcomes, the repository ships green suites (130 pytest / 97 vitest) that this
feature's shell changes will touch, and the feature's definition of done requires
both suites green. Test tasks are therefore first-class here, not optional.

**Organization**: Grouped by user story so each can be implemented and verified
independently.

**Revision**: Renumbered after `/speckit-analyze` (2026-09-04). T020/T021 and the
regeneration step were added to close coverage and ordering gaps, and the
duplicated transform-preservation task was folded into its implementation task.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story the task serves (US1–US4)
- Exact file paths are given in every task

## Path Conventions

Single project, using directories that already exist: `src/doc_generator/` for
the generator and page shell, `frontend/src/` for the wiki bundle, `tests/` at
the repository root. No new top-level structure — see plan.md, Structure Decision.

`SCRATCH` below means any working directory outside the repository; this session
uses its own scratchpad directory. It is never a path inside the repo, because
pytest writes temporary trees there and they must not land in version control.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish a known-good baseline and get the brand asset into the
tree before anything references it.

- [X] T001 Record the pre-change baseline by running `.venv/Scripts/python.exe -m pytest tests/ --basetemp=$SCRATCH/pytest -p no:cacheprovider` and `cd frontend && npx vitest run`; note the counts (expected 130 and 97) in the implementation notes so any later delta is attributable
- [X] T002 [P] Copy `docs/brand/favicon.ico` to `src/doc_generator/assets/favicon.ico` as a committed source asset, byte-identical to the brand kit original
- [X] T003 [P] Record the vendored provenance of the new asset in `src/doc_generator/assets/VENDORED.md`, matching the existing entry style used for `mermaid.min.js`

**Checkpoint**: Baseline known, brand asset in the tree, nothing wired up yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The template context, the storage contract and the pre-paint script.
Every user story depends on `data-theme` actually being applied.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Add `wiki_id` derivation to `src/doc_generator/html_render.py` as `sha256(repository_id)[:16]`, citing `data-model.md` (WikiIdentity) and mirroring the `state_id` construction in `src/cli/paths.py`; the raw `repositoryId` must never reach the template because it embeds an absolute filesystem path
- [X] T005 Thread the repository id from `src/doc_generator/generator.py` into the `render_page_html` call so `wiki_id` reaches the template context (depends on T004)
- [X] T006 [P] Add `FAVICON_SOURCE_PATH` / `FAVICON_OUTPUT_PATH` constants and extend the asset copy in `src/doc_generator/writer.py` to ship `assets/favicon.ico` through the existing `_copy_if_changed` path used by `mermaid.min.js` and `wiki-ui.css` (spec FR-020)
- [X] T007 Compute `favicon_href` with `relative_output_link` in `src/doc_generator/html_render.py`, alongside the existing `ui_style_href` and `mermaid_script_href`, so it resolves correctly from diagram pages one directory deeper (depends on T006)
- [X] T008 [P] Create `frontend/src/lib/theme.ts` implementing the storage contract from `contracts/wiki-theme-shell.md` §3: key `codepedia:theme:<wikiId>`, values `system`/`light`/`dark`, every read and write wrapped in try/catch, any unknown or unreadable value resolving to `system`, and an absent preference treated as System for a first-time reader (spec FR-003, FR-009, FR-010)
- [X] T009 Implement effective-theme resolution and application in `frontend/src/lib/theme.ts`: write `data-theme` on `<html>` for light/dark and **remove the attribute entirely for System** — never `data-theme="system"`, which satisfies the stylesheet's `:not([data-theme="light"])` guard while matching no dark rule, leaving a state the CSS cannot express. A pinned Light or Dark must win over the OS preference in both directions (spec FR-006, `contracts/wiki-theme-shell.md` §2.1)
- [X] T010 Add the pre-paint inline `<script>` to `<head>` of `src/doc_generator/templates/layout.html.jinja`, before any body content, with no `src`, `defer` or `async`; it reads the stored preference for `{{ wiki_id }}` and stamps `data-theme` synchronously. It must be dependency-free and must never throw — `wiki-ui.js` loads at the end of `<body>`, so a toggle implemented only in the bundle repaints after first paint and flashes on every navigation (spec FR-008, `research.md` §1)
- [X] T011 Add the `<div id="wiki-theme-root">` mount point to the sidebar in `src/doc_generator/templates/layout.html.jinja`, following the existing `#wiki-search-root` / `#wiki-toc-root` convention (depends on T010, same file)
- [X] T012 [P] Add unit tests for `frontend/src/lib/theme.ts` in `frontend/src/lib/theme.test.ts` covering the three values, an unknown stored value, a missing key, and a `localStorage` accessor that throws

**Checkpoint**: `data-theme` is applied before first paint and the storage
contract is settled. User stories can now proceed.

---

## Phase 3: User Story 1 - Read the wiki in the theme I choose (Priority: P1) 🎯 MVP

**Goal**: A reader can pick System, Light or Dark from any page and the wiki
obeys immediately.

**Independent Test**: Open a generated wiki with the OS set to dark, choose
Light, and confirm the page turns light and stays light. Repeat with the OS light,
choosing Dark.

### Tests for User Story 1

- [X] T013 [P] [US1] Component tests for the segmented control in `frontend/src/components/ThemeToggle.test.tsx`: three options render, the active one is marked selected, activating one applies the theme, and every option is reachable and operable by keyboard alone (spec FR-001, FR-002, FR-012, SC-009)
- [X] T014 [P] [US1] Test in `frontend/src/lib/theme.test.ts` that an OS preference change while System is selected re-resolves the effective theme, and that no change is emitted while Light or Dark is pinned (spec FR-005, FR-006)

### Implementation for User Story 1

- [X] T015 [US1] Create the segmented control in `frontend/src/components/ThemeToggle.tsx` with exactly three options in the order System, Light, Dark, each reachable in one interaction from any other state; keep `.theme-toggle` first in the class list as the test/JS hook, with utilities alongside (spec FR-001, SC-001, `contracts/wiki-theme-shell.md` §2.2)
- [X] T016 [US1] Give the control its accessible name and per-option selected state (`aria-checked`/`aria-pressed`) in `frontend/src/components/ThemeToggle.tsx`, so the current state is conveyed without interaction (spec FR-002, FR-012)
- [X] T017 [US1] Mount `ThemeToggle` into `#wiki-theme-root` in `frontend/src/main.tsx`, alongside the existing search, TOC and chat mounts (depends on T015)
- [X] T018 [US1] Add the `matchMedia` change listener in `frontend/src/lib/theme.ts` so a System reader follows a live OS switch without a reload, and dispatch `wiki:theme-changed` on `document` only when the *effective* theme actually changed — each firing re-renders every diagram on the page (spec FR-005, `contracts/wiki-theme-shell.md` §4)
- [X] T019 [US1] Rebuild the bundle with `cd frontend && npx vite build` so `src/doc_generator/assets/wiki-ui.{js,css}` reflect the control; these are committed artifacts and must not drift from source
- [X] T020 [US1] Regenerate a wiki fixture with `.venv/Scripts/python.exe -m cli.main index <any-repo>` so every browser check from here on runs against current output. **Every browser verification in Phases 3–6 depends on this**, and it must come after T019 or the regenerated wiki carries a stale bundle (depends on T019)
- [X] T021 [US1] Verify against the regenerated wiki that switching theme applies immediately without a page reload and leaves the reader's scroll position undisturbed — scroll to the middle of a long page, switch theme, and confirm the scroll offset is unchanged (spec FR-004; depends on T020)

**Checkpoint**: The control works and the theme applies. Diagrams still carry
their original colours until US4 — expected, not a regression.

---

## Phase 4: User Story 2 - The choice sticks, and never flashes (Priority: P1)

**Goal**: The choice survives navigation and restarts, and no page ever paints
in the wrong theme.

**Independent Test**: Choose Dark, navigate five or more pages watching for any
light frame, then close the browser entirely, reopen, and confirm it is still dark.

**Depends on T020** for a current wiki fixture.

### Tests for User Story 2

- [X] T022 [P] [US2] Test in `frontend/src/lib/theme.test.ts` that choosing System writes the literal `"system"` rather than deleting the key, and that both forms read back identically (`data-model.md`, ThemePreference lifecycle)
- [X] T023 [P] [US2] Generator test in `tests/unit/test_wiki_theme_shell.py` asserting the inline theme script is present in `<head>`, carries no `defer`/`async`/`src`, and appears before any body content on every page kind (spec FR-008)
- [X] T024 [P] [US2] Generator test in `tests/unit/test_wiki_theme_shell.py` asserting two different repositories produce different `wiki_id` values, and that the same repository produces a stable one across two renders (spec FR-007)

### Implementation for User Story 2

- [X] T025 [US2] Verify persistence across pages and across a full browser restart per `quickstart.md` §4 check 4.2, confirming `data-theme` is already correct at `Page.domContentEventFired` rather than being set later (spec FR-007, SC-003)
- [X] T026 [US2] Verify no-flash across ten page navigations with Dark pinned, capturing first-paint screenshots over CDP per `quickstart.md` §4 check 4.1 (spec FR-008, SC-002) — jsdom has no paint, so `vitest` cannot see this by construction
- [X] T027 [US2] Verify per-wiki isolation with two generated wikis per `quickstart.md` §4 check 4.3: setting Dark in one must leave the other untouched. Chrome reports `location.origin` as `file://` for every local document regardless of directory, so all wikis share one `localStorage` and an unscoped key silently clobbers (`research.md` §2, spec FR-007) — a single-wiki test cannot catch this
- [X] T028 [US2] Verify the theme still applies for the current page when `localStorage` throws, with no error surfaced to the reader, per `quickstart.md` §4 check 4.8 (spec FR-010)

**Checkpoint**: Both P1 stories complete. The theme feature is usable and durable.

---

## Phase 5: User Story 3 - The wiki looks like Codepedia produced it (Priority: P2)

**Goal**: The real brand mark in the shell and a Codepedia icon on the browser
tab, both correct for the active theme.

**Independent Test**: Open a generated wiki, confirm the real mark is top-left and
a Codepedia icon is on the tab, then switch theme and confirm the mark switches.

### Tests for User Story 3

- [X] T029 [P] [US3] Generator test in `tests/unit/test_wiki_brand.py` asserting every page kind declares `link[rel="icon"]` and that `assets/favicon.ico` is written into the output byte-identical to the source (spec FR-016, FR-020, SC-004)
- [X] T030 [P] [US3] Generator test in `tests/unit/test_wiki_brand.py` asserting no generated file references `docs/brand/` or any path outside the wiki's own output root (spec FR-021)
- [X] T031 [P] [US3] Generator test in `tests/unit/test_wiki_brand.py` asserting that **across the same page kinds T029 covers** both `data-brand-variant` marks are inlined, that each is `aria-hidden="true"`, and that neither retains `role`, `aria-label` or a `<title>` element — the slot already carries a visible "codepedia" wordmark and the brand must be announced exactly once (spec FR-019, SC-004)

### Implementation for User Story 3

- [X] T032 [US3] Create the inlined brand markup in `src/doc_generator/templates/_brand.html.jinja` holding both `codepedia-mark-light.svg` and `codepedia-mark-dark.svg` with published fills preserved (`#14274A`/`#FFFFFF` and inverse), each stripped of `role`, `aria-label` and `<title>` and wrapped `aria-hidden="true"`. **It must be a `*.jinja` file directly in `src/doc_generator/templates/`** — `template_fingerprint()` globs that directory non-recursively for `*.jinja` only, so an `.svg` sidecar or a subdirectory would escape the staleness check and leave regenerated wikis inconsistent (`research.md` §6, contract invariant 7)
- [X] T033 [US3] Replace the `<span class="brand-mark …">CP</span>` placeholder in `src/doc_generator/templates/layout.html.jinja` with the brand include, growing the slot from `size-5` (20 px) to 24 px — the brand policy forbids the full mark below 24 px because the magnifier handle disappears (spec FR-014, FR-017)
- [X] T034 [US3] Check the brand link's `items-baseline` alignment in `src/doc_generator/templates/layout.html.jinja` now that the slot holds a 24 px SVG rather than a text span, and correct the alignment if the mark and wordmark no longer sit right (depends on T033)
- [X] T035 [US3] Add the `<link rel="icon" href="{{ favicon_href }}">` to `<head>` in `src/doc_generator/templates/layout.html.jinja` (spec FR-016; depends on T007)
- [X] T036 [P] [US3] Add the brand variant visibility rules to `frontend/src/styles.css` in `@layer components`, using the same three-state selector shape as the palette so exactly one mark is visible per theme, decided by CSS alone with no script — the correct mark must show before the bundle loads and forever if it never loads (spec FR-015, `research.md` §3)
- [X] T037 [US3] Update the existing shell assertions in `tests/unit/test_page_toc.py`, `tests/integration/test_feature_pages.py` and `tests/integration/test_doc_generator_cross_references.py` to match on hooks rather than exact class strings wherever the grown brand slot broke them — fix by matching the hook, never by pinning the new class string
- [X] T038 [US3] Rebuild the bundle with `cd frontend && npx vite build` so the brand CSS reaches `src/doc_generator/assets/wiki-ui.css`, then regenerate the wiki fixture so later checks see it (depends on T036)

**Checkpoint**: The wiki is branded in both themes and on the tab.

---

## Phase 6: User Story 4 - It still works with no network and no server (Priority: P2)

**Goal**: Everything above holds when the wiki is opened from the filesystem with
no network, with scripting disabled, and on pages carrying diagrams.

**Independent Test**: Disconnect, copy a generated wiki outside the repository
that produced it, open it from the filesystem, and exercise the theme control,
the brand and a diagram.

### Tests for User Story 4

- [X] T039 [P] [US4] Test in `frontend/src/lib/diagramViewport.test.ts` that a theme change re-renders a diagram from its stashed source and that the viewport wrapper's transform is unchanged afterwards (spec FR-013, FR-013a, SC-011)
- [X] T040 [P] [US4] Test in `frontend/src/lib/diagramViewport.test.ts` that a diagram with no stashed source, or one that fails to re-render, is left exactly as it is and does not abort the batch (`contracts/wiki-theme-shell.md` §5)

### Implementation for User Story 4

- [X] T041 [US4] Stash each diagram's source text into `data-diagram-source` on `pre.mermaid` **before** the first `mermaid.run()` in the inline bootstrap in `src/doc_generator/templates/layout.html.jinja`. `mermaid.run()` replaces the element's text content with the rendered SVG, so after the first render the source is gone from the DOM and there is nothing left to re-render from — this is a precondition, not an optimisation (`research.md` §5)
- [X] T042 [US4] Implement the theme-change re-render in `frontend/src/lib/diagramViewport.ts`: on `wiki:theme-changed`, re-initialize Mermaid with the matching built-in theme, re-render each diagram from its stashed source into a detached element, and swap **only** the resulting `<svg>` into the existing viewport wrapper, leaving the wrapper's CSS transform untouched so `{ scale, offsetX, offsetY }` survive because nothing captures or restores them — replacing the wrapper instead would reset to `INITIAL_STATE` and lose the reader's position (spec FR-013, FR-013a; depends on T041)
- [X] T043 [US4] Verify the wiki renders fully offline from a relocated directory with zero network requests, using `Network.enable` over CDP per `quickstart.md` §4 check 4.4 (spec FR-021, FR-022, SC-005, SC-006, constitution 2.2)
- [X] T044 [US4] Verify the page renders completely and follows the OS preference with script execution disabled, under both emulated colour schemes, per `quickstart.md` §4 check 4.5 (spec FR-011, SC-007)
- [X] T045 [US4] Verify a zoomed and panned diagram redraws in the new theme at the same zoom and position, and that code blocks stay legible in both themes, per `quickstart.md` §4 check 4.7 (spec FR-013a, FR-013b, SC-011)
- [X] T046 [US4] Rebuild the bundle with `cd frontend && npx vite build` so the diagram re-render reaches `src/doc_generator/assets/wiki-ui.js` (depends on T042)

**Checkpoint**: All four stories functional, offline and script-free paths intact.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T047 [P] Add the print rule to `frontend/src/styles.css` pinning the light palette tokens in an `@media print` block, placed **in `@layer base`** — unlayered CSS outranks every cascade layer in this codebase and would win against utilities in hard-to-debug ways (spec FR-026, `research.md` §7)
- [X] T048 [P] Confirm `frontend/src/styles.css` still carries `@source "../../src/doc_generator/templates/"` so classes used only in the Jinja shell are not tree-shaken, and that no new template directory was introduced that would need its own entry
- [X] T049 Verify a regenerated wiki rebuilds **every** page, not only those whose source changed, confirming the changed `template_fingerprint()` forced a full rebuild — a wiki with the new shell on some pages and the old on others is the exact failure that mechanism exists to prevent (spec FR-023, `quickstart.md` §3)
- [X] T050 Confirm the existing CLI flows are unchanged by running `scan`, `serve` and `provider mode full-local` per `quickstart.md` §6: no new prompt, no new required argument, no changed output, and generation still writes only under the documentation output root that `_ensure_output_root_is_separate` guards, never into the analysed repository (spec FR-024, FR-025, SC-010)
- [X] T051 Measure the brand slot rendered from `src/doc_generator/templates/_brand.html.jinja` to confirm it is at least 24 px rather than eyeballing it, and review the artwork against the rules in `docs/brand/README.md` for unmodified fills, no shadow, gradient or outline, and intact clear space (spec FR-017, FR-018, SC-008)
- [X] T052 Run the full validation in `quickstart.md` end to end, with both suites green at or above the 130 / 97 baseline and every CDP check passing
- [X] T053 Confirm `src/doc_generator/assets/wiki-ui.js` and `wiki-ui.css` are rebuilt and committed, with no drift from `frontend/src`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — **blocks all user stories**
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on Foundational, and on **T020** for a current wiki
  fixture
- **US3 (Phase 5)**: depends on Foundational; needs T007 for `favicon_href`
- **US4 (Phase 6)**: depends on Foundational, on US1's `wiki:theme-changed` event
  (T018), and on T020
- **Polish (Phase 7)**: depends on all desired stories

### The fixture dependency

T020 regenerates the wiki every browser check reads. It sits at the end of US1
because it must follow the bundle rebuild (T019) — regenerating first would copy
a stale `wiki-ui.js` into the output and every later check would test the wrong
code. T038 re-runs the same pairing after the US3 CSS change.

### User Story Dependencies

- **US1 (P1)**: independent once Foundational is done
- **US2 (P1)**: shares `theme.ts` and the inline script with US1 but is verified
  independently — it is mostly assertion and browser verification over machinery
  Foundational already built
- **US3 (P2)**: fully independent of the theme stories except for the CSS
  visibility swap, which reuses selectors that already exist
- **US4 (P2)**: the only genuine cross-story dependency — the diagram re-render
  listens for the event US1 dispatches (T018)

### Within Each User Story

- Tests before implementation
- `theme.ts` before the component that consumes it
- Template context before the template that reads it
- `npx vite build`, then regenerate, then browser verification — in that order

### Parallel Opportunities

- T002 and T003 in Setup
- T006, T008 and T012 in Foundational — different files, no shared state
- T013 and T014 in US1; T022, T023 and T024 in US2
- T029, T030 and T031 in US3, and T036 alongside them (different file)
- T039 and T040 in US4
- T047 and T048 in Polish
- US3 can be worked in parallel with US1/US2 by a second person: it touches
  `_brand.html.jinja` and `styles.css` where the others touch `theme.ts` and
  `ThemeToggle.tsx`. The one shared file is `layout.html.jinja` (T033/T035 vs
  T010/T011/T041), which must be sequenced.

---

## Parallel Example: User Story 3

```bash
# Launch the US3 generator tests together:
Task: "Favicon presence and byte-identical copy in tests/unit/test_wiki_brand.py"
Task: "No reference to docs/brand/ in tests/unit/test_wiki_brand.py"
Task: "Inlined marks are aria-hidden and stripped in tests/unit/test_wiki_brand.py"

# And in parallel, in a different file:
Task: "Brand variant visibility rules in frontend/src/styles.css"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1: Setup
2. Phase 2: Foundational — blocks everything
3. Phase 3: User Story 1
4. **STOP and VALIDATE**: a reader can choose a theme and the wiki obeys
5. US2 follows immediately in practice — a control whose choice is forgotten on
   the next page is worse than no control, so the two P1 stories are the real
   shippable unit

### Incremental Delivery

1. Setup + Foundational → `data-theme` applied before paint
2. US1 → the control works → demo
3. US2 → it sticks and never flashes → this is the honest release point
4. US3 → the wiki carries the brand → demo
5. US4 → offline, script-free and diagram paths verified

### Risk Notes

- **T027 (per-wiki isolation) and T045 (diagram zoom preservation) are the two
  most likely to fail.** T027 is invisible to any single-wiki test; T045 is the
  only place the diagram work can go wrong without an obvious symptom.
- **US1+US2 alone leave diagrams carrying their original colours** after a theme
  switch, since the re-render lands in US4. That is a visible inconsistency on
  diagram pages, so US4 should not be deferred indefinitely even though it is P2.
- **T032's file placement is load-bearing**, not stylistic. Brand markup outside
  `TEMPLATES_DIR/*.jinja` silently escapes `template_fingerprint()`.
- **FR-013b needs no build work.** No syntax highlighter ships; code blocks are
  styled from theme tokens and follow a theme change for free. T045 carries it as
  a regression check only.

---

## Notes

- `[P]` tasks touch different files and have no incomplete dependencies
- `[Story]` labels map tasks to spec.md user stories for traceability
- Implementation comments should cite their spec artifacts by name and section,
  matching the house style already used throughout this codebase
- Pass `--basetemp=$SCRATCH/pytest -p no:cacheprovider` to pytest; a bare run
  produces around 17 spurious `PermissionError`s on this machine
- Commit after each task or logical group

---

## Implementation record (2026-09-04)

All 53 tasks completed. Where execution differed from the plan, it is recorded
here rather than left for the next reader to infer.

### Baselines

The plan expected 130 pytest / 97 vitest. The real pre-change baseline was
**777 pytest passed with 1 pre-existing failure**, and **97 vitest**. The "130"
figure was stale; the Python suite has grown since. The one failure was
`test_config_before_any_provider_reachable_still_reports_without_failing`, a
known-flaky test that makes a live Groq call and fails when Groq answers - it is
unrelated to this feature and passed on the final run.

**Final: 808 pytest passed, 0 failed. 142 vitest passed.** Net +30 Python tests
and +45 frontend tests.

### Deviations

- **T012, T013, T014 - test file locations.** The tasks named
  `frontend/src/**/*.test.ts`. This repository puts frontend tests in a flat
  `frontend/tests/` directory, so they went to `frontend/tests/theme.test.ts` and
  `frontend/tests/ThemeToggle.test.tsx`. The repo's convention wins over the
  task file's guess.
- **T013 - no `user-event`.** The task implied Tab-traversal assertions.
  `@testing-library/user-event` is not a dependency here and plan.md commits to
  adding none, so the tests use `fireEvent` like the rest of the suite and assert
  what that can honestly prove: the options are native `<button>`s that nothing
  has removed from the tab order. Real keyboard traversal is covered in Chrome.
- **T020 - the fixture could not come from `codepedia index`.** `index` builds
  into a staging directory and only promotes it *after* the embedding stage
  (`index_command.py:234-262`). With the OpenAI key quota-exhausted and Ollama
  not running, every provider in the embeddings chain fails and the whole run -
  including the regenerated wiki - is discarded. Reconfiguring the chains to get
  around that would rewrite the user's config and re-trigger the disclosure gate,
  which a test fixture has no business doing. The fixture is instead built by
  driving the real `render_page_html` and `DocumentationWriter.ensure_wiki_ui_assets`
  paths directly, so the shell under test is genuine and only the page *content*
  is synthetic - which is all the browser checks are about.
- **T039, T040 - separate test file.** These went to
  `frontend/tests/diagramTheme.test.ts` rather than being appended to
  `diagramViewport.test.ts`. Distinct concern, distinct DOM fixture; the 034
  gesture tests stay untouched.
- **T037 - no existing assertion needed changing.** The grown brand slot broke
  nothing. Two integration tests did fail, but for a different reason - see
  below - and were fixed at the source rather than by relaxing them.
- **T050 - `provider mode full-local` was not run.** It mutates the user's saved
  provider chains and re-triggers the disclosure gate. The CLI regression was
  verified with the read-only surface instead (`--help`, `scan`, `config`,
  `provider --help`), plus a direct check that all three chains and the
  disclosure signature in `~/.codepedia/config.json` are byte-for-byte unchanged.

### Findings worth keeping

- **The `xmlns` attribute tripped the zero-network guards.** Inlining the brand
  SVGs brought `xmlns="http://www.w3.org/2000/svg"` with them, and
  `test_no_cdn_reference_and_classic_script_tag` /
  `test_no_cdn_reference_and_classic_ui_script_tag` assert `"http://" not in
  renderedHtml`. An inline `<svg>` in an HTML document is namespaced by the
  parser, so the attribute is redundant here and was removed. The guards are
  blunt on purpose and were left exactly as strict as they were.
- **Mermaid ids must be unique per render.** Reusing an id makes Mermaid serve a
  cached definition, and the redraw silently keeps the previous theme's colours -
  a no-op that looks like success. Covered by a test.
- **The fresh SVG needs `enhanceOne`'s sizing reapplied.** Mermaid stamps
  `width="100%"` and a `max-width` on every render; leaving those on a viewport
  child re-introduces the letterboxing that made `scale` stop meaning
  magnification. Covered by a test.

### Browser verification

35 CDP checks across two scripts, all passing: 22 for theme behaviour
(T021, T025-T028, T043, T044, FR-005) and 13 for brand and diagrams
(T045, T051, FR-013b, FR-015). Highlights:

- `data-theme` is `dark` at DOMContentLoaded with `atStart` showing the document
  element did not yet exist - the attribute is stamped by the `<head>` script,
  not the bundle (FR-008).
- Two fixture wikis confirmed to share one `file://` origin, with each deriving
  its own key and neither able to clobber the other (FR-007).
- A diagram zoomed to `translate(42px, 17px) scale(3)` came back from the theme
  redraw at exactly `translate(42px, 17px) scale(3)`, with the viewport element
  identical and the SVG markup genuinely changed, 9099 -> 8965 bytes (FR-013a).
- Brand mark measured at 24x24 with the wordmark centred to within 0px, and
  exactly one variant visible in either theme (FR-015, FR-017).
- Zero non-`file://` requests from a wiki copied outside the repository (FR-022).
