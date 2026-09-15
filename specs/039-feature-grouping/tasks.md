---

description: "Task list for the Feature Grouping That Follows the Code feature"
---

# Tasks: Feature Grouping That Follows the Code

**Input**: Design documents from `/specs/039-feature-grouping/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/feature-grouping.md](./contracts/feature-grouping.md), [quickstart.md](./quickstart.md)

**Tests**: Requested (owner convention: tests first). Every implementation task names the tests it makes pass. Write each story's tests first and confirm they fail before implementing it.

**Organization**: by user story.

- User Stories 1 and 2 (both P1) are the MVP. Together they remove the catch-all group and the test-seeded groups.
- User Story 3 (anchors) and User Story 4 (planner input) build on them.

All four stories edit `src/doc_generator/features/`, so they are delivered in order, and each can still be verified on its own.

**Conventions**:

- **Work** on `main`, with no branch and no commits unless the owner asks (and no `Co-Authored-By` trailer).
- **Run tests** with `.venv\Scripts\python.exe -m pytest --basetemp=<scratchpad>\pytest-039 -p no:cacheprovider -q <paths>`. A bare run shows about 17 spurious `PermissionError`s.
- **Known flaky test**: `tests/integration/test_cli.py::test_config_before_any_provider_reachable_still_reports_without_failing` makes a live Groq call and fails whenever Groq answers. Re-run it before investigating.
- **Test fixtures**:
  - hand-built `RepositoryEvidence`, `Candidate` and adjacency, following `_evidence`, `_candidate` and `_adjacency` in `tests/unit/test_feature_validate.py`;
  - small indexed repositories, following `_build` in `tests/unit/test_feature_candidates.py` and `index_repo` in `tests/integration/_doc_generator_support.py`.
- **Fake planner engines** reuse `RecordingEngine` and `CapturingEngine` from `tests/unit/test_feature_planner.py`.
- **Probes** are read-only, need no provider, and live in the 039 planning session's scratchpad (`planner_probe.py`, `grouping_proto.py`, `majors_probe.py`). T002 makes them durable. Run each as `$env:PYTHONPATH='src'; .venv\Scripts\python.exe <probe> <repo-root>`.
- **Reference repositories**: `C:\Users\ASUS\IdeaProjects\codepedia-sample-repo` and `C:\Users\ASUS\IdeaProjects\nextgen-wealth-ledger`.
- **Model calls**: none before T036, and T036 only with the owner's approval.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 to US4 (spec user stories)

---

## Phase 1: Setup

**Purpose**: a baseline to compare against, and durable copies of the measurements. No behaviour changes.

- [X] T001 Record the baseline:
  - Run the full suite with the command in Conventions on the current `main`, in the background (about 10 minutes).
  - Save the result as `<scratchpad>\baseline-039.txt` and note any pre-existing failures. Later "suite green" claims are compared against this file.
  - Confirm `.venv` is Python 3.11–3.13.
- [X] T002 [P] Preserve the 033 baseline measurements, which research.md and quickstart.md cite:
  - run `planner_probe.py` on both reference repositories and save the outputs as `probe-sample.033.txt` and `probe-nextgen.033.txt`;
  - copy `grouping_proto.py`, `planner_probe.py`, `majors_probe.py` and `proto-run1.txt` next to them.

  **Ask the owner** where they should live. The default is the implementing session's scratchpad; the alternative is `specs/039-feature-grouping/measurements/`.

---

## Phase 2: Foundational (shared evidence every story needs)

**Purpose**: move three helpers out of `overview/` into `features/` (research Decision 3), and extend `RepositoryEvidence` (data-model.md). Nothing groups differently yet.

**⚠️ No user-story work starts until this phase is done.**

- [X] T003 [P] Extend `tests/unit/test_feature_evidence.py`. Build one fixture with `tests/test_x.py` (test functions only), `cli.py` (a Typer `@app.command()`), `launcher.py` (`def main()`), `helpers.py` (an uncalled public function) and a README with a title, a badge and a prose paragraph. Add:
  - `test_test_files_are_recognised_by_directory_or_name`, and `test_ordinary_files_are_not_test_files`: move 038's parametrised cases from `tests/unit/test_overview_evidence.py` here, and keep thin copies there importing through `overview.evidence`.
  - `test_readme_lead_is_the_first_prose_paragraph` and `test_readme_lead_is_empty_without_a_readme`.
  - `test_test_modules_are_listed_apart`: `testModuleKeys` holds `tests/test_x.py` only.
  - `test_entry_modules_hold_a_command_a_route_or_main`: `entryModuleKeys` equals {`cli.py`, `launcher.py`}.
  - `test_seeds_are_non_test_modules_with_entry_points`: `seedModuleKeys` equals {`cli.py`, `launcher.py`, `helpers.py`}.
  - `test_module_labels_tell_same_named_modules_apart`: two `__init__.py` files get distinct labels.
- [X] T004 Move the helpers into `src/doc_generator/features/evidence.py`:
  - `is_test_path` (with `_TEST_DIRECTORIES` and `_TEST_FILE_NAME`), `ENTRY_KINDS`, and `read_readme_lead` (with `_first_prose_paragraph` and `MAX_README_LEAD_CHARS`);
  - a new `entry_kind(entry_point) -> str`, holding 038's "an uncalled `function` named `main` is kind `main`" rule.

  `src/doc_generator/overview/evidence.py` imports and re-exports them, and its `_entry_flows` uses `entry_kind`. The 038 suites must pass unchanged: `tests/unit/test_overview_*.py` and `tests/integration/test_overview_*.py`.
- [X] T005 Extend `RepositoryEvidence` and `build_repository_evidence` in `src/doc_generator/features/evidence.py` with:
  - `readmeLead`, `testModuleKeys`, `entryModuleKeys` and `seedModuleKeys`, exactly as data-model.md defines them;
  - `moduleLabels: Mapping[str, str]`, the `prose.disambiguated_labels` label per module key. It is computed here because only this stage holds the repository root.

  Every new field defaults to empty, so existing hand-built evidence in tests still constructs. `prose.disambiguated_labels` takes `ModuleSymbol`s: pass `bundle.files[*].module`.

  Makes T003 pass. Then run `tests/unit/test_feature_*.py` and `tests/integration/test_feature_*.py`, and confirm nothing else changed.
- [X] T006 [P] Teach `tests/integration/_doc_generator_support._language` the analysed languages: `.java` → `java`, `.ts`/`.tsx` → `typescript`, `.js`/`.jsx`/`.mjs`/`.cjs` → `javascript`, `.md` → `markdown`, else `python`. Update `index_repo`'s docstring. Existing callers pass only `.py` and `.md`, so nothing else changes.
- [X] T006a [P] Write the plan cache key tests in `tests/unit/test_feature_planner.py` (contract §7). They must fail first:
  - `test_a_changed_grouping_changes_the_cache_key`
  - `test_an_unchanged_grouping_keeps_the_cache_key`
  - `test_a_grouping_version_bump_changes_the_cache_key`

  Keep `test_the_cache_key_ignores_summaries` unchanged in intent.
- [X] T006b Make the plan cache key cover the grouping, **before any grouping rule changes** (FR-018; research Decision 9, order of work; analyze finding I1). In `src/doc_generator/features/planner.py`:
  - add `GROUPING_VERSION = "2"`;
  - make `plan_cache_key(evidence, candidates)` hash, in order, the version, the module keys, the entry-point keys, then each candidate's sorted member keys in handle order (data-model.md § Plan cache key);
  - have `FeaturePlanner.plan` pass the candidates it received.

  Update the durable copy of `planner_probe.py` (T002) to call `plan_cache_key(evidence, candidates)`. From here on, the cached 033 plans no longer match, so the probe's repaired features are the no-model features.

  Makes T006a pass. Then run `tests/unit/test_feature_*.py` and `tests/integration/test_feature_navigation.py`: one call per grouping, zero on an unchanged rerun.

**Checkpoint**: evidence knows tests, entry modules, seeds, labels and the README lead. The plan cache key covers the grouping. Grouping is untouched.

---

## Phase 3: User Story 1: parts grouped by how their code connects, in Java and JS/TS too (Priority: P1) 🎯 MVP

**Goal**:
- Java and JS/TS imports couple modules.
- Uncoupled groups fold by directory, never into the largest group.
- Entry modules are never absorbed by a group without one.
- Entry-point counts survive every fold.

**Independent Test**: spec US1. Regenerate `nextgen-wealth-ledger` with no model (`planner_probe.py`). Modules importing one another share a group, no feature holds more than 30% of the modules, and each feature's entry-point count is the sum over its members.

### Tests for User Story 1 (write first; they must fail)

- [X] T007 [P] [US1] Write `tests/unit/test_feature_imports.py`, following contract §2. The fixture is a small repository indexed through `index_repo` (needs T006) with:
  - `backend/com/acme/web/WalletController.java`, importing `com.acme.service.WalletService`, `com.acme.dto.*`, `static com.acme.util.Money.round` and `java.util.List`;
  - `backend/com/acme/service/WalletService.java`;
  - `backend/com/acme/dto/{A,B,C}Dto.java`;
  - `backend/com/acme/util/Money.java`, with a nested class imported as `com.acme.util.Money.Currency` from another file;
  - `frontend/app/wallets.component.ts`, importing `./wallet.service`, `../shared/index` and `@angular/core`;
  - `frontend/app/wallet.service.ts`, `frontend/shared/index.ts`, and a relative import of a missing file.

  Tests:
  - `test_a_fully_qualified_java_import_couples_its_modules`
  - `test_a_static_import_couples_to_its_class`
  - `test_a_nested_class_import_couples_to_its_outer_class`
  - `test_a_wildcard_import_splits_one_import_across_the_package` (each DTO edge is `Fraction(1, 3)` and they sum to 1, FR-003)
  - `test_an_external_java_import_adds_nothing`
  - `test_a_same_named_class_in_another_package_is_not_matched` (FR-002: `org.other.dto.ADto` does not couple to `com/acme/dto/ADto`)
  - `test_a_call_without_an_import_adds_no_coupling` (FR-004: two classes of one package, one calling the other, no import)
  - `test_a_relative_ts_import_resolves_with_or_without_extension`
  - `test_a_directory_import_resolves_to_its_index_file`
  - `test_a_package_import_adds_nothing`
  - `test_a_missing_relative_target_adds_nothing`
  - `test_edges_are_symmetric_without_self_loops`
  - `test_resolution_is_identical_across_runs`
- [X] T008 [P] [US1] Extend `tests/unit/test_feature_fallback.py`:
  - `test_python_adjacency_is_unchanged` (FR-005): on a Python-only fixture, `build_import_adjacency` equals 033's value for value. Snapshot the expected dict from the pre-change code, or compare against `_python_import_adjacency` if T012 keeps 033's body under that name.
  - `test_java_and_ts_edges_are_merged_into_the_adjacency`.
- [X] T009 [P] [US1] Extend `tests/unit/test_feature_candidates.py` with hand-built evidence and adjacency (contract §5, research Decision 6):
  - `test_an_uncoupled_small_group_joins_the_survivor_holding_most_modules_directly_in_its_directory`
  - `test_the_directory_walk_climbs_to_the_parent_directory`
  - `test_the_directory_walk_never_climbs_from_a_subdirectory_into_the_root` (FR-006: an orphan under `frontend/` does not join a group holding a root-level module)
  - `test_a_directory_counts_only_its_direct_modules_never_its_subtree`
  - `test_leftovers_sharing_a_directory_combine`
  - `test_a_truly_isolated_module_lands_in_the_terminal_candidate` (title `TERMINAL_FEATURE_TITLE`)
  - `test_no_group_is_folded_into_the_largest_for_being_largest`
  - `test_a_one_module_entry_module_survives` (FR-006a)
  - `test_an_entry_module_is_never_absorbed_by_a_group_without_one`
  - `test_a_small_entry_group_joins_the_entry_group_it_is_most_coupled_to` (FR-006a)
  - `test_two_small_entry_groups_in_one_directory_combine` (FR-006a, directory rule)
  - `test_entry_groups_of_two_or_more_modules_in_one_directory_stay_apart` (FR-006a; the sample's route groups in `api/`)
  - `test_the_cap_folds_non_entry_groups_first`
  - `test_entry_groups_beyond_the_cap_combine_by_coupling_then_directory_then_shared_path` (FR-006a; lower `MAX_PROMPTED_CANDIDATES` with `monkeypatch`)
  - `test_entry_point_counts_add_up_to_the_non_test_total` (FR-007)
  - `test_candidates_still_partition_every_module`

  And in `tests/unit/test_feature_validate.py`: `test_there_is_at_most_one_terminal_feature`. Cover three cases: with no plan, when two seed titles collide, and when the model titles a planned feature `TERMINAL_FEATURE_TITLE` and leaves the terminal candidate unplaced (research Decision 6 step 5).
- [X] T010 [P] [US1] Write `tests/integration/test_feature_grouping_languages.py` (contract §8). The fixture is a Java backend (controller, service, a DTO package imported by wildcard, an exceptions package) plus a TypeScript frontend (components, services, an `index.ts`), indexed with `index_repo`. Assert, without a planner:
  - every module is in exactly one feature;
  - no feature exceeds 30% of the modules;
  - the controller, its service and its DTOs share a feature;
  - the components join their services;
  - no feature holds both Java and TypeScript modules (edge case "Unconnected halves");
  - a second run yields identical features.

  Leave the anchor and incremental assertions for T024.

### Implementation for User Story 1

- [X] T011 [US1] Create `src/doc_generator/features/imports.py` with `resolve_repository_imports(bundle, graph, *, repository_root)`, following research Decision 2 and contract §2:
  - Take no engine.
  - Select Java and JS/TS modules **by file suffix**, not by the stored language label, whose case differs between indexing and tests.
  - Build one path index per call.
  - Read import names from `graph.dependencies(module.filePath, relation_type="import")`.
  - **Java**: a name matches only a path ending with the whole name at a segment boundary, never a partial suffix, and several matches go to the smaller path. Static and nested imports drop trailing segments one at a time, down to two, and the first name that matches wins. A wildcard adds `Fraction(1, n)`.
  - **JS/TS**: resolve relative names against the importer's directory, trying the name as given, with each of `JS_RESOLVE_EXTENSIONS`, then `/index` with each extension.
  - Unresolved names add nothing.

  Makes T007 pass.
- [X] T012 [US1] In `src/doc_generator/features/fallback.py`, make `build_import_adjacency` return 033's Python adjacency merged with `resolve_repository_imports`. Keep the Python body byte-for-byte, as `_python_import_adjacency` if extracted. Widen the weight type to `int | Fraction`, and check that `_label_propagation`, `_coupling_target` and `lead_module_key` only add and compare. Makes T008 pass.
- [X] T013 [US1] Replace `_consolidate` and `_best_absorption_target` in `src/doc_generator/features/candidates.py` with research Decision 6, steps 1 to 6:
  1. Coupling first.
  2. Entry groups (holding a module in `evidence.entryModuleKeys`) are exempt from `MIN_CANDIDATE_MODULES`. A small entry group folds only into the entry group it is most coupled to, or failing that the one found by step 3's walk over entry groups. Entry groups of `MIN_CANDIDATE_MODULES` or more never combine outside step 6.
  3. The direct-directory walk, which never climbs from a subdirectory into the repository root.
  4. Leftovers combine per directory, titled by `default_group_title`.
  5. The one explicitly built terminal candidate (`TERMINAL_FEATURE_TITLE`, imported from `validate`, with a fixed sentinel seed key that is not a member key).
  6. The cap folds non-entry groups first. Entry groups beyond it combine by coupling, then the directory walk, then the longest shared leading directory path, with ties to the smaller seed key.

  Remove the "largest survivor" fallback entirely. `build_candidates` needs the evidence's entry modules: pass `evidence` down, keeping the public signature. Keep 033's post-condition that the candidates partition every module.

  In `src/doc_generator/features/validate.py`, make `_place_remainder`'s terminal bucket join the feature already titled `TERMINAL_FEATURE_TITLE`, whether it came from the terminal candidate or from the plan, instead of appending a second one (research Decision 6 step 5).

  Makes T009's folding tests and `test_there_is_at_most_one_terminal_feature` pass.

  **Added at T015** (owner decisions, 2026-09-15; research Decision 6):
  - When no group can stand alone, nothing folds (033's rule), tested by `test_when_no_group_can_stand_alone_nothing_is_folded`.
  - `fallback._ancestor_target` no longer climbs into the root, tested by `test_a_lone_subdirectory_never_joins_a_root_group_by_ancestry`.
  - `TERMINAL_FEATURE_TITLE` is defined in `candidates.py` and re-exported by `validate.py`, because `validate` imports `candidates`.

  **Corrected at T020**: steps 1 to 3 run per group, smallest first, with the order taken again after each fold. The first version ran all coupling folds before any directory placement. Research Decision 6 records why.
- [X] T014 [US1] Recompute entry-point counts from members, excluding `evidence.testModuleKeys` (research Decision 8, FR-007):
  - `Candidate.exposedEntryPointCount` at the end of `build_candidates` in `src/doc_generator/features/candidates.py`;
  - `Feature.exposedEntryPointCount` in `validate._build_features` in `src/doc_generator/features/validate.py`.

  Makes `test_entry_point_counts_add_up_to_the_non_test_total` and T010 pass.
- [X] T015 [US1] Reconcile the existing tests that encode 033 rules this spec replaces, in `tests/unit/test_feature_candidates.py`, `tests/unit/test_feature_fallback.py`, `tests/unit/test_feature_validate.py` and `tests/integration/test_feature_*.py`. Likely candidates:
  - `test_small_candidates_are_folded_rather_than_dropped`
  - `test_candidate_count_respects_the_prompt_cap`
  - `test_entry_point_modules_seed_their_own_candidates`

  Change an expectation only where FR-006, FR-006a or FR-007 now requires something else, and give each changed test a one-line comment naming the requirement. List every changed test in the task report. Then run the 038 suites: the Overview's evidence reads features, so its integration tests may see new groups. Reconcile them the same way.
- [X] T016 [US1] Measure, with no model: run `planner_probe.py` (updated in T006b) on both reference repositories, and confirm it finds no cached plan. Record against quickstart §2 and research Decision 1:
  - the largest feature's share (SC-001);
  - SC-002 per import and per language: resolved in-repository imports over all in-repository imports, as SC-002 defines them. Also record Java and TS modules coupled, for context;
  - the entry-point count totals (SC-004).

  Differences from `proto-run1.txt` are explained in the report, never silently accepted. research.md's Decision 12 addendum lists the prototype's known shortcuts.

**Checkpoint**: no catch-all group on `nextgen-wealth-ledger`, Java and TS coupling present, Python grouping unchanged. Tests still seed at this point; US2 stops that.

---

## Phase 4: User Story 2: tests follow the code they test (Priority: P1)

**Goal**: test files never seed and never pull production code into a group. They are placed afterwards, with the code they exercise (FR-008, FR-009; research Decision 5).

**Independent Test**: spec US2. Regenerate `codepedia-sample-repo` with no model:
- no group is seeded by a test;
- `fine_calculator.py` is grouped by production coupling;
- `test_fines.py` sits in the feature holding most of the code it imports;
- `tests/conftest.py`, which imports production code, is placed by coupling (prototype: with `routes_members`). Any test importing no production code is placed by directory.

### Tests for User Story 2 (write first; they must fail)

- [X] T017 [P] [US2] Extend `tests/unit/test_feature_candidates.py`:
  - `test_a_test_file_never_seeds_a_group`
  - `test_a_production_module_coupled_only_to_its_test_is_grouped_by_production_code`
  - `test_a_test_joins_the_group_holding_most_of_the_code_it_imports`
  - `test_a_tie_between_groups_goes_to_the_smaller_seed_key`
  - `test_a_fixtures_only_test_is_placed_by_its_directory`
  - `test_the_test_directory_walk_counts_production_modules_only` (tests already placed do not count)
  - `test_unplaced_tests_sharing_a_directory_combine_and_a_lone_one_goes_to_the_terminal_candidate` (FR-009)
  - `test_placing_tests_never_moves_a_production_module` (compare production memberships with and without the test files)
  - `test_every_test_file_belongs_to_exactly_one_group`
  - `test_a_repository_whose_only_entry_points_are_in_tests_is_grouped_by_directory` (edge case "Tests only": no seeds, no catch-all group, tests placed afterwards)

### Implementation for User Story 2

- [X] T018 [US2] In `src/doc_generator/features/candidates.py`:
  - seed from `evidence.seedModuleKeys`, not `entryPointModuleKeys`;
  - give `_assign_by_coupling`, `build_fallback_groups` and the Decision 6 folding an adjacency restricted to production modules, removing every module in `evidence.testModuleKeys` from both keys and neighbour lists.
- [X] T019 [US2] In `src/doc_generator/features/candidates.py`, add test placement after folding (research Decision 5):
  - each test file joins the candidate holding the greatest summed weight of production modules it is coupled to, with ties to the smaller seed key;
  - a test coupled to none follows the Decision 6 step 3 directory walk, counting production modules only;
  - tests still unplaced and sharing a directory combine into one candidate for it, unless the cap is reached;
  - a test left alone joins the terminal candidate (research Decision 5 step 4).

  Append tests to `memberKeys` and keep 033's name ordering. Makes T017 pass. Then re-run T015's suites.
- [X] T020 [US2] Measure, with no model: on `codepedia-sample-repo`, record:
  - SC-003 (test-seeded groups: 5 → 0);
  - where `test_fines.py`, `tests/conftest.py` and `fine_calculator.py` land. `conftest.py` imports production code, so it is expected with the code it imports (prototype: `routes_members`);
  - any test placed by directory or sent to the terminal candidate.

  On `nextgen-wealth-ledger`, confirm nothing moved, since it has no test files.

**Checkpoint**: both P1 stories hold. The MVP can be reviewed here.

---

## Phase 5: User Story 3: a subsystem starts where its work starts (Priority: P2)

**Goal**: a feature's anchor, and so its page address and the Overview's start file, is:
1. its entry module;
2. else its seed with the most entry points;
3. else the most connected member.

Old addresses keep resolving (FR-010, FR-011; research Decision 7).

**Independent Test**: spec US3. On both repositories, every feature holding an entry module is anchored at one, and every other feature holding a seed is anchored at a seed. Every address the previous run published still resolves.

### Tests for User Story 3 (write first; they must fail)

- [X] T021 [P] [US3] Extend `tests/unit/test_feature_validate.py` (contract §6):
  - `test_the_anchor_is_the_entry_module_over_a_seed_with_more_uncalled_functions`
  - `test_the_anchor_is_the_seed_over_a_better_connected_helper`
  - `test_a_feature_without_a_seed_keeps_the_most_connected_member`
  - `test_a_model_merge_keeps_the_entry_module_anchor`
  - `test_anchor_ties_go_to_the_module_name_then_the_key`

  Update `test_a_feature_is_keyed_by_its_anchor_module` only if its fixture's expected anchor now differs by FR-010, with a comment.
- [X] T022 [P] [US3] Extend `tests/integration/test_feature_navigation.py` with `test_an_address_published_before_regrouping_still_resolves`:
  1. generate the fixture repository, and record one feature's `outputPathHtml`;
  2. add an entry point to another member of that feature, so its anchor moves under FR-010;
  3. regenerate;
  4. assert the old path holds a redirect stub pointing at the feature now holding most of its modules, and that `list_aliases` records it (033 FR-020, FR-021).

### Implementation for User Story 3

- [X] T023 [US3] Add `anchor_for(member_keys, evidence, adjacency, name_by_key)` to `src/doc_generator/features/candidates.py`, following research Decision 7:
  - the entry module with the most entry points;
  - else the non-test seed with the most entry points;
  - else `lead_module_key`;
  - ties go to the module name, then the key.

  `anchor_module_key` stays for directory titles. Use `anchor_for` in `validate._build_features` in `src/doc_generator/features/validate.py`. Makes T021 pass. `_resolve_anchor_collisions` stays as the assertion it is.
- [X] T024 [US3] Add to `tests/integration/test_feature_grouping_languages.py`:
  - the anchor assertions: the controller's feature is anchored at its seed, and a directory-only feature at its most connected member;
  - `test_a_body_only_java_edit_keeps_the_grouping` (FR-019, constitution 2.5; analyze finding C2). Change one method body of one Java file, touching no import or entry point. Re-index that file and regenerate with `incremental=True, changedPaths=[…]`, as `test_feature_navigation.py` does. Assert that the candidates and the plan cache key are unchanged, that no model is called, and that the impact does not set `requiresNavigationRegeneration`.

  Run T022, then T015's suites.
- [X] T025 [US3] Measure, with no model: the anchors on both reference repositories (SC-005).
  - Expected on the sample: `cli`, the route modules, `lending_service`, `catalog_service`, `memory_store` and `sqlite_store`. Not `ids`, `errors`, `member` or `fine_calculator`.
  - Expected on nextgen: never `animations.ts`.

  Record them against research Decision 7.

**Checkpoint**: anchors name the modules readers should open. Redirects cover every moved address.

---

## Phase 6: User Story 4: the planner is shown what a group actually is (Priority: P3)

**Goal**:
- Each group is described by its seed, then its most relevant members, under distinguishable labels.
- The README's opening paragraph replaces its headings.
- A plan cached from the old prompt is not reused (the cache key itself moved to T006b).

(FR-012 to FR-015 and FR-018; research Decisions 9 and 10.)

**Independent Test**: spec US4. Build the planning prompt for both repositories with no model:
- each group lists its seed first, then members by entry points and coupling;
- labels are distinct;
- the repository description is the README's first paragraph;
- the `GROUPING_VERSION` bump changes the cache key.

### Tests for User Story 4 (write first; they must fail)

- [X] T026 [P] [US4] Extend `tests/unit/test_feature_planner.py` (contract §7):
  - `test_the_seed_is_the_first_member_described`
  - `test_members_are_ordered_by_entry_points_then_coupling_then_label`
  - `test_same_named_members_get_distinct_labels`
  - `test_a_long_label_is_cut_to_its_trailing_segments`
  - `test_the_readme_lead_is_the_repository_description`
  - `test_readme_bullets_are_no_longer_sent`
  - `test_the_terminal_candidates_placeholder_seed_is_not_described` (U4)

  The cache key tests moved to T006a. Update `test_the_budget_arithmetic_is_the_documented_one` so its independent arithmetic includes `MAX_MEMBER_LABEL_CHARS`. Keep `test_worst_case_call_fits_the_provider_budget` unchanged in intent.

### Implementation for User Story 4

- [X] T027 [US4] Order each candidate's `memberKeys` by relevance at the end of `build_candidates` in `src/doc_generator/features/candidates.py`, where the adjacency is available:
  1. the seed, when it is a member (the terminal candidate's placeholder seed is not);
  2. non-test members by entry points, descending;
  3. by summed coupling inside the candidate, descending;
  4. by label.

  The planner then describes the first `MAX_MEMBERS_PER_CANDIDATE`. `validate._build_features` keeps sorting `Feature.members` by name, so pages are unaffected.

  Note in data-model.md § Candidate that `memberKeys` order now carries relevance.
- [X] T028 [US4] In `src/doc_generator/features/planner.py`:
  - describe members by `evidence.moduleLabels`, cut to their trailing path segments within the new `MAX_MEMBER_LABEL_CHARS = 40`;
  - send `evidence.readmeLead` in place of `readmeBullets`, still bounded by `MAX_README_PROMPT_CHARS`;
  - make `worst_case_prompt_tokens()` count the label cap.

  The budget test must still pass (FR-015).
- [X] T029 [US4] In `src/doc_generator/features/planner.py`, bump `GROUPING_VERSION` from `"2"` to `"3"`, because T028 changes what the model is shown. A plan cached from the MVP's prompt is then not reused for an unchanged grouping (research Decision 9). The key itself was built in T006b.

  Then run T015's suites plus `tests/integration/test_feature_navigation.py`: one call per grouping, zero on an unchanged rerun.
- [X] T030 [US4] Measure, with no model: print the planning prompt with `planner_probe.py` (updated in T006b) for both repositories and check the Independent Test by eye. Record the prompt size against the `worst_case_call_tokens()` ceiling.

**Checkpoint**: all four stories are done without a model call.

---

## Phase 7: Polish, verification and docs

- [X] T031 Run the full suite in the background and compare it with `<scratchpad>\baseline-039.txt`. No new failure is accepted; the known flaky Groq test does not count as new.
- [X] T032 Confirm determinism and the no-model path on real data (quickstart §3):
  - run `planner_probe.py` twice per repository and confirm the outputs are byte-identical;
  - with a planner stub that refuses, confirm the modules and candidates equal the no-planner run (033 SC-006).
- [X] T033 [P] `docs/architecture.md`, per its "> Maintenance:" rule. In the `doc_generator` Presentation row, describe feature grouping (033 never documented it):
  - seeds from entry points, tests excluded;
  - coupling from imports in Python, Java and JS/TS;
  - directory-based folding with no catch-all group;
  - anchors at entry modules;
  - one cached planner call keyed on the grouping.

  In Storage, add `doc_feature_plans` next to `doc_overview_narratives`.
- [X] T034 [P] `docs/diagrams/class-diagram.md`, per its "> Maintenance:" rule:
  - add `RepositoryEvidence`, `Candidate` and `Feature` to `DocGeneratorPackage`;
  - add the `resolve_repository_imports` step, shown as a `<<function>>`-annotated class the way `ChatApiApp` is annotated;
  - add relationships: `DocGenerator ..> RepositoryEvidence`, `FeaturePlanner ..> Candidate`, `Feature *-- Candidate` (repair).

  Parse it with the scratchpad's `mermaid_parse.cjs`, or rebuild that helper from 038's T051 note.
- [X] T035 [P] `README.md`, per the living-docs rule: in "Renders a browsable wiki", say the sidebar groups modules into features that follow how the code connects (Python, Java, JavaScript/TypeScript), with tests shown beside the code they test.
  - Check whether `docs/diagrams/sequence-diagrams/01-full-indexing.md` needs a grouping note.
  - Confirm `docs/stack.md` needs no change (no new dependency).
- [X] T036 **Owner-gated verification round** (quickstart §4). **Ask the owner first**, with a recommendation.
  1. Hash-compare `%USERPROFILE%\.codepedia\config.json` with the backup (`%USERPROFILE%\.codepedia\config.backup-038.json`).
  2. List every `features/*.html` in both wikis' `<state>\docs\` directories.
  3. Set the Groq-first `summaryChain`.
  4. Re-index both reference repositories.
  5. Restore the config byte for byte, and hash-compare again.

  Expected and recorded:
  - one planner call per repository on the first run (the cache key changed), and none on a second;
  - no `Traceback`;
  - every address listed in step 2 still opens, as a live page or a redirect stub to one. The check is scripted over every listed path (SC-008; analyze finding C1);
  - the largest feature's share with the model, recorded, not enforced (clarification Q5);
  - the Overview is re-narrated once per repository (038).
- [X] T036a **Added after T036** (owner decision, 2026-09-15). Fix the defect the second model round exposed: a full `codepedia index` builds into a fresh directory and carries only the manifest forward, so earlier redirect stubs were lost (9 of 11 sample aliases, 7 nextgen), and an alias whose target moved again pointed at a page that no longer existed. It predates 039, but breaks SC-008 and FR-011 from the second full re-index on.
  - Test first: `tests/integration/test_feature_navigation.py::test_every_published_address_survives_repeated_full_rebuilds` (three full runs into fresh output directories, the anchor moving twice).
  - Fix: `DocGenerator._restore_redirects`, called after `_redirect_superseded_pages`. Each alias is followed to the live page, re-pointed if its target moved, and its stub rewritten when missing or stale. This stays within 033's alias mechanism, as FR-011 requires.
  - Then restore both reference wikis with one more re-index (plan and narrative cached, so no model call is expected; same swap and restore procedure), and check all three address lists resolve: `t036-old-features-*`, `round2-old-features-*` and the current pages.
- [X] T037 Map the features against 038's answer keys `sc001-key-{sample,nextgen}.md` (SC-006):
  - sample: at least 6 of 8, including the CLI;
  - nextgen: at least 6 of 9, including wallets, auth and security, chatbot and frontend.

  Then run the stranger test (SC-007): one fresh subagent per repository, told to use Read exactly once on `<state>\docs\index.md` and nothing else, confirming `tool_uses: 1` and scoring against the keys. The implementer never reviews.

  Take screenshots of each Overview at 700 px dark and full width light.
- [X] T037a **Added after T037** (owner decision, 2026-09-15). The Overview table's "Start with" shows the feature's anchor. 038's `_start_with_member` picked the member with the most entry points, so the table contradicted the paragraph's start file on 5 subsystems, and both reviewers flagged it.
  - Test first: `tests/integration/test_overview_subsystems.py::test_start_with_is_the_subsystems_anchor`.
  - Fix: `DocGenerator._start_with_member` returns the anchor member. The now-unused `_repository_evidence` and `_relative_to_root` are removed. `docs/architecture.md` says the table and the paragraph share the anchor.
  - Then regenerate both wikis (no model call expected) and repeat the stranger test with two fresh reviewers.
- [X] T038 Record the results in `specs/039-feature-grouping/research.md` as Decision 13: the implementation's measurements against the prototype, SC-001 to SC-008, the stranger test, and every test changed in T015. Tick this file's tasks. Report to the owner. Do not commit.

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2 → stories.** T004 blocks T005. T003, T006 and T006a can start with T004. T006b needs T006a and T002 (the durable probe it updates).
- **T006b before any grouping change.** The plan cache key must cover the grouping before T013 changes it, or intermediate states apply the cached 033 plan to new groups (research Decision 9, order of work).
- **US1 → US2 → US3 → US4, in that order.** Each story edits `src/doc_generator/features/candidates.py`, so its implementation tasks are sequential. Its test tasks ([P]) can be written in parallel with the previous story's implementation.
  - **US2** depends on Phase 2 (`seedModuleKeys`, `testModuleKeys`) and on T013 (the folding it restricts to production modules).
  - **US3** depends on Phase 2 (`entryModuleKeys`) and on T014, which also edits `validate.py`.
  - **US4** depends on Phase 2 (`readmeLead`, `moduleLabels`, the cache key) and on T019, the last change to `build_candidates` before T027. T029 follows T028.
- **Polish**: T031 and T032 after all stories. T033 to T035 in parallel with anything after T029. T036 only after T031, and only with the owner's approval. T037 after T036. T038 last.

```text
T001 ─┐
T002 ─┤ (parallel)
T003 ─┼─> T004 ─> T005 ─> T006b ─┬─> US1: T007..T010 [P] ─> T011 ─> T012 ─> T013 ─> T014 ─> T015 ─> T016
T006 ─┤                          │   US2: T017 [P] ──────────────────────────────> T018 ─> T019 ─> T020
T006a ┘
                                 │   US3: T021, T022 [P] ──────────────────────────────────> T023 ─> T024 ─> T025
                                 │   US4: T026 [P] ────────────────────────────────────────────────> T027 ─> T028 ─> T029 ─> T030
                                 └─> Polish: T031, T032 ─> T036 (owner) ─> T037 ─> T038;  T033, T034, T035 [P]
```

## Parallel Execution Examples

- **Phase 2**: T003 (tests), T006 (test support) and T006a (cache key tests) together, while T004 is written.
- **US1**: T007, T008, T009 and T010 are four test files, written together before T011.
- **US3**: T021 (`test_feature_validate.py`) and T022 (`test_feature_navigation.py`) together.
- **Polish**: T033, T034 and T035 are three documents, written together.

## Implementation Strategy

1. **MVP = Phases 1–4 (US1 + US2).** This is the smallest release that fixes what readers reported: the catch-all group on `nextgen-wealth-ledger`, and "Tests (Test Fines)" and "Scripts" swallowing the CLI on the sample. Stop and report after T020 if the owner wants a review point.
2. **Then US3** (anchors). This is the change readers see in the Overview's "start" files and in page addresses.
3. **Then US4** (planner input). This improves names only, and costs no extra call.
4. **Then polish.** T036 is the only step that calls a model, and it needs the owner's approval each time.
