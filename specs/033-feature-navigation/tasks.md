---

description: "Task list for 033-feature-navigation"
---

# Tasks: Feature Navigation in the Generated Wiki

**Input**: Design documents from `/specs/033-feature-navigation/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/feature-navigation.md](./contracts/feature-navigation.md), [quickstart.md](./quickstart.md)

**Tests**: Included — the spec requires them (FR-030 makes the no-model path a
tested property, not an assumed one).

## Read this before trusting the phase structure

> **The user stories in this feature are NOT independently deliverable, and
> pretending otherwise would be dangerous.** Spec-kit's usual promise is that
> each story is an MVP slice you could ship alone. Here:
>
> - Shipping **US1** alone (feature-named navigation) removes the sidebar's
>   module tree while the feature page is still the section page — every module
>   loses its last door. US1 without US2 makes the wiki strictly worse.
> - Shipping **US1** without **US3** publishes feature URLs before the alias
>   table exists. Measured: six of eleven anchors are one import edge from
>   moving (research Decision 6), so those URLs break on the first refactor and
>   cannot be repaired afterwards.
>
> **US1 + US2 + US3 are one release boundary.** US4 (no-model parity) is a
> property of that boundary rather than an increment on top of it. Only US5
> (ordering) is genuinely droppable.
>
> The phases below are therefore ordered **A1 → A2 → A3 → A4** from plan.md, not
> by story priority, and each task carries the story it serves.

**Organization**: By implementation phase. Parallelism is limited by file, not by
story — see [Dependencies](#dependencies--execution-order).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different file, no dependency on incomplete work
- **[Story]**: US1..US5, mapping to the user stories in spec.md

## Path Conventions

Single Python project. `src/doc_generator/`, `tests/unit/`, `tests/integration/`.
**No frontend file is touched** — see contract § 6. A task asking for
`npm run build` means the approach has drifted.

## Test command

```bash
.venv/Scripts/python.exe -m pytest --basetemp="$SCRATCHPAD" -p no:cacheprovider
```

Both flags are mandatory on this machine; a bare `pytest` reports ~17 spurious
`PermissionError`s. Expect 672 passing plus one known flake
(`test_config_before_any_provider_reachable_still_reports_without_failing`, which
makes a live Groq availability call). **Any other failure is real.**

---

## Phase 1: Setup

**Purpose**: The package boundary that makes the "no engine below the planner"
rule checkable by reading one directory.

- [x] T001 Create `src/doc_generator/features/__init__.py` exporting nothing yet, so the package exists before any module imports from it
- [x] T002 [P] Add `PROVIDER_TOKEN_BUDGET = 8000` and `CHARS_PER_TOKEN = 4` to `src/doc_generator/features/__init__.py` as the two constants the budget assertion reads. They belong here, not in `planner.py`, because the test asserting the ceiling must not import the module that could raise the ceiling
- [x] T003 [P] Confirm the Phase 0 probe harness still runs: `cd "$SCRATCHPAD" && .venv/Scripts/python.exe probe_evidence.py`. It is the A1 gate in quickstart § 2.1 and every number in research.md comes from it

---

## Phase 2: A1 — Evidence and candidates (Blocking Prerequisite)

**Goal**: Navigation is derived, complete and correct with **no model involved
at all**. At the end of this phase the grouping exists and is verifiable; only
its names are missing.

**Independent Test**: Run the A1 gate (quickstart § 2.1) and confirm the
candidate size distribution is not degenerate — no candidate holds more than
about a third of the modules, fewer than half are singletons.

**⚠️ Everything after this phase depends on it.**

### Tests for A1

- [x] T004 [P] [US2] Add `tests/unit/test_feature_evidence.py::test_one_evidence_row_per_module` — assert `len(evidence.modules) == len(bundle.files)` including modules with no entry points, no exports and no summary. A missing row would fail silently as a module absent from the navigation
- [x] T005 [P] [US2] Add `tests/unit/test_feature_evidence.py::test_reaching_entry_points_uses_a_visited_set` — build a fixture with a call cycle and assert the walk terminates and reports each entry point once. This is the property `build_entry_point_call_sequence` deliberately does not have
- [x] T006 [P] [US4] Add `tests/unit/test_feature_evidence.py::test_missing_readme_yields_no_bullets` and `::test_unreadable_readme_never_raises` — an unreadable README degrades the prompt, never the run (contract § 1)
- [x] T007 [P] [US4] Add `tests/unit/test_feature_evidence.py::test_readme_md_is_read` — pins the difference from `chat.retrieval.read_readme_content`, whose candidate list omits `.md` on purpose ([retrieval.py:25](../../src/chat/retrieval.py#L25))
- [x] T008 [P] [US2] Add `tests/unit/test_feature_candidates.py::test_candidates_partition_the_repository` — the union of all `memberKeys` equals every module key and no two candidates intersect. **This is the invariant every downstream guarantee rests on** (FR-001)
- [x] T009 [P] [US2] Add `tests/unit/test_feature_candidates.py::test_attach_distance_is_bounded_at_two` — assert `MAX_ATTACH_DISTANCE == 2` *and* that a module 3 hops from every seed is not attached by reachability. Pinning the constant alone would pass against an implementation that ignores it
- [x] T010 [P] [US2] Add `tests/unit/test_feature_candidates.py::test_a_module_reachable_from_two_seeds_goes_to_the_nearer` and `::test_equal_distance_breaks_on_seed_key` (FR-006)
- [x] T011 [P] [US2] Add `tests/unit/test_feature_candidates.py::test_small_candidates_are_folded` and `::test_survivors_are_capped_at_max_prompted` (FR-007)
- [x] T012 [P] [US4] Add `tests/unit/test_feature_candidates.py::test_derivation_is_identical_across_runs` — build twice, assert equal (FR-002)
- [x] T013 [P] [US4] Add `tests/unit/test_feature_fallback.py` with the clustering assertions that still describe live behaviour, adapted to the new API, plus **a fixture containing prose files**. `test_sections.py` is *kept* until A4 deletes `sections.py` with it - moving it now would leave the live module untested for three phases. Research Decision 9: `identify_entry_points` skips prose, so documents reach only this path — and this repository's `src/` tree contains none, so the existing fixtures do not exercise it

### Implementation for A1

- [x] T014 [US2] Implement `src/doc_generator/features/evidence.py` — `FeatureEvidence`, `RepositoryEvidence`, `build_repository_evidence(bundle, graph, *, repository_root)`. **Takes no engine argument, not even an optional one** (contract § 1). Reuse `identify_entry_points` as-is; walk `graph.functions_called_by` with an own visited set bounded at `MAX_EVIDENCE_CALL_DEPTH = 6`. Makes T004–T007 pass
- [x] T015 [US2] Create `src/doc_generator/features/fallback.py` by **moving** `_build_import_adjacency`, `_absorb_small_directories`, `_coupling_target`, `_ancestor_target`, `_resolve_absorption_target`, `_split_group`, `_label_propagation`, `_lead_member`, `_ordered`, `_relative_directory`, `_normalize_path` and their constants out of `sections.py` unchanged, plus `build_fallback_groups(...)`. The diff must read as a move, not a rewrite. Makes T013 pass
- [x] T016 [US2] Implement `src/doc_generator/features/candidates.py` — `Candidate` and `build_candidates(...)` with `MAX_ATTACH_DISTANCE = 2`, `MIN_CANDIDATE_MODULES = 2`, `MAX_PROMPTED_CANDIDATES = 32`. Every ordering an explicit `sorted(...)`; no `set` iteration order reaches the output. Makes T008–T012 pass
- [x] T017 [US2] **Run the A1 gate** — run, and it initially FAILED at 78% of the repository in one candidate. Root cause was not the attach rule: research.md Decision 11, the import adjacency was substantially fictional
- [x] T017a [US2] **DECISION TAKEN: Option B** — fix import resolution in `dependency_graph` properly. Implemented in `src/dependency_graph/graph.py`: relative imports resolve against the importing file's own package; dotted absolute imports must match the whole dotted tail; a bare name resolves only when exactly one repository file carries it; and an unresolved import node no longer inherits the importing file's `sourceFile`
- [x] T017d [US2] Add five regression tests to `tests/unit/test_dependency_graph.py` covering all four changes, and mutation-check each — reverting the unresolved-path fix reddens 1 test, the ambiguous-bare fix 1, the relative-import fix 2. **This fix is in shared code and had nothing pinning it**, which is the failure shape this project keeps repeating
- [x] T017e [US2] Confirm zero regressions from the shared-code change: full suite passes with no failures (baseline was 1, the known Groq flake)
- [x] T017c [US2] Re-run the A1 gate — **PASS**: 21 candidates, largest 21 modules (15%, was 78%), 0 singletons, 139/139 modules claimed with no duplicates, identical across two builds
- [x] T017f [US2] Qualify `Candidate.seedTitle` by the seed's package (`repository_metadata - models`, not `models`). Four candidates were titled `models`; `validate.py` rejects duplicate titles, so with no model reachable three of the four features would have been discarded and reassigned
- [x] T018 [US2] Mutation-check the candidate assertions - and this **found a vacuous test**. Three mutations run: consolidation truncating instead of folding (red), bare seed titles (red), and ordering by label instead of summed weight (**green - the coupling test was not discriminating**, because in that fixture every module had a single labelled neighbour so any tie-break agreed). Added `test_a_module_joins_the_area_it_is_most_coupled_to_not_the_first_named`, where one area wins on weight while the other sorts first; the mutation now reddens it. At 4 the stage produced one 64-module candidate and 41 singletons; a suite that stays green against that is not testing the distribution

**Checkpoint**: Grouping is complete, deterministic and model-free. Nothing
renders yet. **Do not proceed to A3 before A2** — see the note at the top.

---

## Phase 3: A2 — Anchor and alias, before anything renders

**Goal**: A feature's address exists, is stable, and survives its anchor moving.

**Independent Test**: quickstart § 2.4 — generate, move an anchor, regenerate
incrementally, confirm the old URL still opens and the old file was not deleted.

**Why this phase is here and not after A4**: rendering a feature page publishes a
URL. Publishing a URL before the alias table exists ships links the first
refactor breaks, and those cannot be repaired after the fact. Measured: six of
eleven anchors need one import edge to move (research Decision 6).

### Tests for A2

- [x] T019 [P] [US3] Add `tests/unit/test_page_aliases.py::test_alias_is_recorded_when_the_anchor_moves` (FR-020)
- [x] T020 [P] [US3] Add `tests/unit/test_page_aliases.py::test_removal_skips_an_aliased_path` — write a page at the aliased path, run the removal pass, assert the file **still exists**. Asserting only that `list_aliases` was called would pass against an implementation that ignores the answer (FR-021)
- [x] T021 [P] [US3] Add `tests/unit/test_page_aliases.py::test_redirect_stub_carries_a_visible_link` — the stub must contain a real `<a href>`, not only the meta refresh, so a reader whose browser blocks the refresh still gets there and can tell where they were sent (spec acceptance 3.4)
- [x] T022 [P] [US3] Add `tests/unit/test_page_aliases.py::test_redirect_url_is_relative` — an absolute or `http://` URL would break `file://` reading and make a network request (constitution 2.2)
- [x] T023 [P] [US3] Add `tests/integration/test_feature_page_identity.py::test_a_moved_anchor_keeps_the_old_url_working` — two full runs with a real anchor move between them, opening the recorded path from run 1 after run 2
- [x] T024 [P] [US3] Add `tests/integration/test_feature_page_identity.py::test_a_retitled_feature_keeps_its_address` (FR-019)

### Implementation for A2

- [x] T025 [P] [US3] Add `feature_page_id`, `feature_slug` (one argument — the anchor module key), `feature_output_paths` and `FEATURE_PAGE_ID_PREFIX` to `src/doc_generator/links.py`, beside the existing `section_*` functions. Do **not** remove `section_*` yet — A4 does that, and removing them here breaks every existing test mid-phase
- [x] T026 [P] [US3] Add `doc_page_aliases` to `SCHEMA_STATEMENTS` in `src/doc_generator/manifest_store.py` plus `PageAlias`, `record_alias` and `list_aliases`. No migration step: `_connect` replays every `CREATE TABLE IF NOT EXISTS` on every connection ([manifest_store.py:59-71](../../src/doc_generator/manifest_store.py#L59-L71))
- [x] T027 [P] [US3] Implement `write_redirect_stub(*, old_paths, new_paths, title)` in `src/doc_generator/writer.py` — `.html` with meta refresh, `<link rel="canonical">` and a visible link; `.md` with one line. Makes T021, T022 pass
- [x] T028 [US3] Add the alias-consulting guard to `DocumentationWriter.remove_page` — **not** to the generator's removal loop as originally written. Putting it in the writer means every caller inherits it, including any added later, and it is where the deletion actually happens. Reads `aliased_output_paths(repositoryId)` and skips any path an alias points through. Makes T020 pass
- [x] T029 [US3] Add `DocGenerator.recordPageMove(oldPageId, newPageId, title)` — records the alias then writes the stub, in that order so an interrupted run leaves a protected path with no stub rather than a stub the next removal pass deletes. Refuses when either page is absent from the manifest: a stub pointing at a page that was never written turns a dead link into a dead link claiming to be a redirect. **The feature-specific anchor-move detection is wired in A4**, when feature pages first render; A2 must land before that, so it ships the mechanism and not the trigger
- [x] T030 [US3] Mutation-check three ways, all confirmed red: removing the alias guard (2 tests), ignoring repository scope on aliases (1), and dropping the stub's visible link (1). The third initially appeared green — the mutation was a syntax error and a `grep FAILED` missed the collection ERROR, so the test never ran. Verified with `ast.parse` before trusting a green mutation result

**Checkpoint**: Addresses are stable and recoverable. Still nothing renders a
feature page — that is A4.

---

## Phase 4: A3 — Planner and validate

**Goal**: Features get real names from one model call, and the wiki is identical
without one.

**Independent Test**: quickstart § 2.3 — generate with and without a model,
confirm identical page addresses and identical membership, differing only in
titles.

### Tests for A3 — every one runs with no model

- [x] T031 [P] [US1] Add `tests/unit/test_feature_planner.py::test_budget_ceiling_from_the_constants` — compute the worst case **from** `MAX_PROMPTED_CANDIDATES`, `MAX_MEMBERS_PER_CANDIDATE`, `MAX_MEMBER_SUMMARY_CHARS`, `MAX_README_PROMPT_CHARS`, `MAX_PLAN_RESPONSE_TOKENS`, `CHARS_PER_TOKEN` and assert `<= PROVIDER_TOKEN_BUDGET`. **Must not hard-code 6145** — a test that restates the answer cannot catch a constant being raised (contract § 4)
- [x] T032 [P] [US1] Add `tests/unit/test_feature_planner.py::test_no_module_key_reaches_the_prompt` — render a prompt from real candidates and assert no `moduleKey` substring appears. Measured at 116.6 chars each; the cheapest guard against the token budget silently regressing (research Decision 4)
- [x] T033 [P] [US1] Add `tests/unit/test_feature_planner.py::test_handles_round_trip` — `c0`..`cN` map back to the candidates they were assigned from, in order
- [x] T034 [P] [US4] Add `tests/unit/test_feature_planner.py::test_exactly_one_call_per_plan` using a recording engine that counts invocations (FR-009)
- [x] T035 [P] [US4] Add `tests/unit/test_feature_planner.py::test_a_cache_hit_makes_no_call` (FR-016, SC-004)
- [x] T036 [P] [US4] Add `tests/unit/test_feature_planner.py::test_unavailable_engine_yields_deterministic_features`, `::test_runtime_error_yields_deterministic_features`, `::test_unparseable_answer_yields_deterministic_features` — all three must produce **the same** result: one feature per candidate under `seedTitle`, `isPlanned=False` (FR-017)
- [x] T037 [P] [US4] Add `tests/unit/test_feature_planner.py::test_an_attribute_error_is_not_disguised_as_an_unavailable_provider` — catching `Exception` instead of `RuntimeError` would turn a wiring bug into a silent fallback, which is exactly the failure shape this project keeps shipping. Carried over from `test_section_narrator.py:209`
- [x] T038 [P] [US4] Add `tests/unit/test_feature_planner.py::test_the_planner_calls_the_provider_chain_not_the_engine_directly` — carried over from `test_section_narrator.py:198`
- [x] T039 [P] [US1] Add `tests/unit/test_feature_validate.py` with **one test per row** of the contract § 5 repair table: unknown handle ignored; uncovered candidate becomes its own feature; duplicated candidate kept in the first only; empty feature dropped; empty/over-long/duplicate title rejected and reassigned; unrecognised `kind` **defaulted, not rejected**
- [x] T040 [P] [US1] Add `tests/unit/test_feature_validate.py::test_unplaced_candidates_land_in_support_and_utilities` (FR-014)
- [x] T041 [P] [US2] Add `tests/unit/test_feature_validate.py::test_repair_preserves_the_partition` — after repair, the union of every feature's `moduleKeys` equals the union of every candidate's `memberKeys`. **This is the assertion that proves the design held** (contract § 5)
- [x] T042 [P] [US1] Add `tests/unit/test_feature_validate.py::test_fewer_than_two_features_discards_the_whole_plan` (FR-015)

### Implementation for A3

- [x] T043 [P] [US1] Implement `src/doc_generator/features/validate.py` — `Feature`, `FeatureMember`, `FeatureKind`, `KIND_RANK`, `repair(plan, candidates)`. **Takes no engine.** Construct the `Support & Utilities` terminal feature explicitly rather than letting it emerge from the uncovered-candidate rule; two rules that could both produce it is how one of them silently stops running. Makes T039–T042 pass
- [x] T044 [US1] Implement `src/doc_generator/features/planner.py` — `FeaturePlanner`, `PlannedFeature`, `FeaturePlan`, `build_feature_plan_prompt`, `parse_feature_plan`, the constants, and the cache key `sha1(sorted moduleKeys + sorted entry-point stableKeys)`. The call is `self.llmEngine.run(lambda engine: engine.generate(prompt))` catching `RuntimeError` only, verbatim in shape from [section_narrator.py:151](../../src/doc_generator/section_narrator.py#L151). Makes T031–T038 pass
- [x] T045 [P] [US4] Add `doc_feature_plans` to `SCHEMA_STATEMENTS` plus `load_feature_plan` / `save_feature_plan`. **One table, not the two data-model.md proposed**: what is cached is the model's raw answer, not the repaired feature set, so repair re-runs on every load. Repair is deterministic and cheap, and caching its *input* rather than its output means a change to the repair rules takes effect immediately instead of waiting for the cache to turn over. `list_feature_titles` moves to A4, where titles first exist
- [x] T046 [US4] Mutation-check five ways, all confirmed red: raising `MAX_PROMPTED_CANDIDATES` (budget test), repair dropping unplaced candidates (3 tests), catching `Exception` instead of `RuntimeError` (the wiring-bug test), never consulting the cache (the zero-call test), and rejecting rather than defaulting an unrecognised kind. Mutations are now applied through `scratchpad/mutate.py`, which `ast.parse`s the result first - a mutation that does not compile makes pytest fail at collection, which looks red but proves nothing
- [x] T047 [US4] Covered by T046's mutation 2 - dropping unplaced candidates reddens three repair tests

**Checkpoint**: Features have names. Nothing renders them yet.

---

## Phase 5: A4 — Rendering: Section → Feature

**Goal**: The wiki publishes feature pages, the sidebar is flat, and the previous
scheme is gone.

**Independent Test**: quickstart § 2.2 and § 2.5.

> **This phase does not have safe intermediate checkpoints.** It is a ~12-file
> rename; between T048 and T060 the tree does not import cleanly and the suite
> does not pass. Complete it in one sitting. A missed call site fails at
> *runtime*, not at import — the CLI and serve wiring are the easiest to miss
> because nothing type-checks them.

### Implementation for A4

- [x] T048 [US1] In `src/doc_generator/models.py`, change `PageKind` member `"section"` to `"feature"`
- [x] T049 [US1] Rename `build_section_diagram_mermaid_source` → `build_feature_diagram_mermaid_source` and `SectionDiagramSource` → `FeatureDiagramSource` in `src/doc_generator/mermaid_diagram.py`, along with `MAX_SECTION_DIAGRAM_MODULES` and `_select_section_diagram_members`. Keep the `click … href` directive at [mermaid_diagram.py:315](../../src/doc_generator/mermaid_diagram.py#L315) byte-identical in shape (FR-028)
- [x] T050 [US1] Rename `src/doc_generator/templates/section.md.jinja` → `feature.md.jinja`, rebinding `section` → `feature` and `section_diagram_source` → `feature_diagram_source`. **The member loop stays exactly as it is** — it already lists every member, and the "N less-connected modules omitted; every module is listed above" line must survive verbatim (contract § 6)
- [x] T051 [US1] In `src/doc_generator/html_render.py`, collapse `NavSection`/`NavModule` to a flat `NavFeature = tuple[str, str, str]` and drop the `active_module_key` parameter and the per-module `expanded` logic
- [x] T052 [US1] In `src/doc_generator/templates/layout.html.jinja`, replace the `<details class="nav-section">` block with a plain list of `<a class="nav-link feature">`, and change the `Sections` label to `Features` (FR-024)
- [x] T053 [US1] In `src/doc_generator/generator.py`, rename `generateSectionPage` → `generateFeaturePage`, `_section_identity` → `_feature_identity`, `_ensure_sections` → `_ensure_features`, and the `sectionNarrator` constructor argument → `featurePlanner`
- [x] T054 [US5] In `src/doc_generator/generator.py`, replace `_nav_sections` with `_nav_features` returning `list[tuple[str, str, str]]` — **no members** — sorted by `(KIND_RANK[kind], -exposedEntryPointCount, title)` (FR-027)
- [x] T055 [US1] In `src/doc_generator/generator.py`, wire `_ensure_features` to `build_repository_evidence` → `build_candidates` → `FeaturePlanner.plan` → `repair`, and update `generateOverviewPage`'s `section_entries` to `feature_entries` so the home page and sidebar cannot disagree (FR-024)
- [x] T056 [US1] In `src/doc_generator/impact.py`, convert all five section reads — the membership map, the `previous_section_page_ids` set, `current_section_page_ids`, the title comparison, and `requiresNavigationRegeneration` — to features
- [x] T057 [US3] In `src/doc_generator/impact.py`, add the `kind == "section"` detection that forces a full non-incremental rebuild (FR-023)
- [x] T058 [US3] In `src/doc_generator/generator.py`, implement the migration pass: for each manifest row with `kind="section"`, resolve the feature holding a plurality of its stored `sourceSymbolIds` (which for a section page **are** its member module keys), record the alias, write the stub, and drop `doc_section_narrations` (FR-022)
- [x] T059 [US1] Delete `src/doc_generator/sections.py` and `src/doc_generator/section_narrator.py`; remove `section_page_id`, `section_slug`, `section_output_paths`, `SECTION_PAGE_ID_PREFIX` from `links.py` and `load_section_narration`, `save_section_narration`, `list_section_titles` from `manifest_store.py`
- [x] T060 [US1] Update `src/doc_generator/__init__.py`, `src/cli/index_command.py:345` and `src/cli/serve_command.py:68` from `SectionNarrator` to `FeaturePlanner`. **These two CLI sites fail at runtime, not at import** — they are the single most likely thing to be missed in this phase

### Tests for A4

- [x] T061 [P] [US2] Add `tests/unit/test_search_index.py::test_every_module_has_a_search_entry` — asserts `search_index.py` indexes every module. **A pinning test only; `search_index.py` must not change.** If implementing this feature requires editing it, the approach has drifted (contract § 6, FR-026)
- [x] T062 [P] [US2] Move `tests/integration/test_section_pages.py` → `test_feature_pages.py` and add `::test_every_member_is_linked_however_large_the_feature` — build a feature larger than `MAX_FEATURE_DIAGRAM_MODULES` and assert `len(rendered member links) == len(feature.members)`. This is the test standing between US2 and an unreachable module (FR-025, SC-008)
- [x] T063 [P] [US1] Move `tests/integration/test_section_navigation.py` → `test_feature_navigation.py`, keeping the invariant it exists for: a re-titled feature still reaches a page that did not otherwise change
- [x] T064 [P] [US2] Add `tests/integration/test_feature_pages.py::test_no_sidebar_entry_links_a_module` (FR-024)
- [x] T065 [P] [US3] Add `tests/integration/test_section_manifest_migration.py` — seed a manifest with `kind="section"` rows, regenerate, assert the run was non-incremental, every old section path resolves to the plurality feature, and `doc_section_narrations` is empty
- [x] T066 [P] [US5] Add `tests/unit/test_impact.py` cases for feature titles and feature page ids driving `requiresNavigationRegeneration`, replacing the section equivalents
- [x] T067 [P] [US5] Add a nav-ordering test asserting `overview` precedes `capability` precedes `subsystem` precedes `tooling`, and that ties break identically across two runs (FR-027)
- [x] T068 [P] [US1] Update `tests/unit/test_doc_generator_home_overview.py`, `tests/integration/test_doc_generator_export.py` and `tests/integration/test_doc_generator_links.py` for the flat nav and `kind="feature"`
- [x] T069 [US1] Ran `grep -rn "[Ss]ection" src/ tests/` — **and it found a live bug**: `module.md.jinja` still read `section_link` while the generator had started passing `feature_link`, so the "In feature" chip on every module page silently rendered nothing (a Jinja undefined is empty, not an error). Fixed and pinned by `test_a_module_page_names_the_feature_it_belongs_to`. Also removed three dead `manifest_store` methods and three comments naming deleted modules. Remaining matches are all *document* sections — the page TOC rail, `search_index`'s prose kind, `_TEMPLATE_HEADING_ANCHORS` — correctly untouched. Original text: run `grep -rn "[Ss]ection" src/ tests/` and confirm every remaining match genuinely means a *document* section — the page TOC rail (`_build_page_toc`, `page_toc`), `search_index`'s `"section"` kind for a prose heading, and `_TEMPLATE_HEADING_ANCHORS`. **Those must not be renamed**; they are a different concept sharing a word (contract § 7)

**Checkpoint**: The full suite passes. The wiki publishes feature pages.

---

## Phase 6: Verification on a real generated wiki

**Purpose**: The requirements a green suite is structurally blind to. Four
defects have shipped in this project through a fully passing suite; every one was
a check that asserted a call was made rather than that a reader arrived
somewhere.

- [x] T070 [US2] quickstart § 2.2 — generate with `featurePlanner=None` into a scratch directory and verify **by reading the generated files**: `features/*.html` exists, `sections/` does not, and the member-link count across all feature pages equals the module-page count (SC-003)
- [ ] T071 [US4] quickstart § 2.3 — generate with a live Groq key, diff the `features/*.html` filename set against T070's. **Identical filenames or the model influenced structure** (SC-006). Then regenerate unchanged and confirm zero planning calls (SC-004)
- [ ] T072 [US4] While doing T071, confirm the model was actually consulted — check the provider log or assert `isPlanned` is `True` on at least one feature. An unreachable model and a silently rejected call both produce a wiki with plain titles; do not infer success from the wiki having built
- [ ] T073 [US3] quickstart § 2.4 — move an anchor, regenerate **incrementally**, open the recorded URL, and `ls` the old path to confirm the removal pass did not delete it
- [ ] T074 [US3] quickstart § 2.5 — stash, generate with `main`'s code, unstash, regenerate over the same output directory and manifest, confirm the old `sections/*.html` resolves. Do this **last**, and commit nothing in between
- [ ] T075 [US1] quickstart § 3.1 — read the sidebar of the wiki from T071 and judge whether a newcomer could name three things this repository does. "Doc Generator", "Chat", "CLI" is the failure mode: that is the directory tree with a model's blessing, which is the defect this feature exists to remove (SC-001)
- [ ] T076 [US5] quickstart § 3.2 — if the ordering looks arbitrary, check whether *every* feature came back with the default `subsystem` kind. The repair table permits that and no test would flag it
- [ ] T077 [US3] quickstart § 3.4 — open a redirect stub and confirm a reader can tell they were moved and where to

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: no dependencies.
- **Phase 2 (A1)**: depends on Phase 1. **Blocks everything else.**
- **Phase 3 (A2)**: depends on A1 for `Feature`/anchor shape. **Must precede A4** —
  A4 renders the first feature page, and rendering publishes a URL.
- **Phase 4 (A3)**: depends on A1 (candidates to plan) and is independent of A2.
- **Phase 5 (A4)**: depends on A1, A2 **and** A3. It is the only phase that
  deletes the old scheme, so it cannot start until the new one is complete.
- **Phase 6**: depends on A4.

### Honest note on parallelism

The `[P]` markers within a phase are real — those tasks touch different files.
**Across phases there is almost none.** A1→A2→A3→A4 is a genuine chain, not a
convention: A2 needs A1's `Feature`, A3 needs A1's candidates, A4 needs all three
and deletes what they replace. Two people could split A2 and A3 after A1 lands;
nothing else parallelises.

### Within Phase 5 specifically

T048–T060 are one atomic change. They are listed separately for reviewability,
not for independent execution — the tree does not import between them.

---

## Implementation Strategy

### The one shippable increment

**A1 + A2 + A3 + A4 together.** There is no smaller correct release, for the
reasons at the top of this file. The phase boundaries are review and
verification checkpoints, not release boundaries.

### Order of gates

| After | Gate |
| --- | --- |
| A1 | quickstart § 2.1 — candidate distribution not degenerate (T017) |
| A2 | quickstart § 2.4 — anchor move survives an incremental run (T073) |
| A3 | quickstart § 2.3 — identical structure with and without a model (T071) |
| A4 | full suite green, `grep` clean (T069), quickstart § 2.2 and § 2.5 |

### Droppable

Only **US5** (general-to-specific ordering). Dropping it means T054 sorts by
title alone and T067, T076 are cut. Everything else is load-bearing.

---

## Notes

- **Do not commit.** Leave all work as uncommitted changes in the working tree.
  `.specify/feature.json` is a machine-local pointer and belongs in no commit.
- **No frontend build.** This feature touches no TypeScript and no CSS.
- Mutation-check the four assertions listed in quickstart § 1 (T018, T030, T046,
  T047). Two vacuous tests were caught this way in feature 034.
- `[P]` = different file, no dependency on incomplete work.
