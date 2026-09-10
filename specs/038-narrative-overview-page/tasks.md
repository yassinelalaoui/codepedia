---

description: "Task list for the Narrative Overview Page feature"
---

# Tasks: Narrative Overview Page

**Input**: Design documents from `/specs/038-narrative-overview-page/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/overview-narrative.md](./contracts/overview-narrative.md), [quickstart.md](./quickstart.md)

**Tests**: Requested. Every task that touches the narrator names its tests. Four tests are required by name:

- `test_worst_case_call_fits_the_provider_budget` (with its independent-arithmetic and raised-cap companions), computed from `PROVIDER_TOKEN_BUDGET` and `CHARS_PER_TOKEN`, never a literal;
- `test_a_fabricated_symbol_rejects_its_paragraph`;
- `test_no_engine_page_has_the_same_outline`;
- `test_unchanged_repository_regenerates_identical_markdown`.

**Organization**: by user story. The first release is **User Stories 1, 2 and 4**; User Story 3 is deferred (spec, Clarifications Q4). **User Story 1 alone produces a working, better Overview** before any User Story 2 task starts. **User Story 4 imports nothing from `doc_generator.overview`**, so it ships even if the narration design changes.

**Conventions**:

- Run tests with `.venv\Scripts\python.exe -m pytest --basetemp=<scratchpad>\pytest -p no:cacheprovider`. A bare run shows about 17 spurious `PermissionError`s.
- `tests/unit/test_cli_config*` makes a live Groq call and is flaky; re-run it before investigating.
- Fake engines reuse `RecordingEngine` from `tests/unit/test_feature_planner.py` and, in integration tests, `RecordingLLMEngine` + `wrap_llm` (a real `FailoverExecutor`) from `tests/integration/_doc_generator_support.py`.
- Indexed repositories in tests come from `build_indexed_repo(tmp_path)`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1, US2 or US4 (spec user stories)

---

## Phase 1: Setup

**Purpose**: Baseline and package skeleton. No behaviour changes.

- [X] T001 Record the baseline: run the full suite with the command in Conventions on `038-narrative-overview-page`, confirm `.venv` is Python 3.11â€“3.13, and note any pre-existing failures in `<scratchpad>\baseline.txt`. That file, not this branch, is what later "suite green" claims are compared against.
- [X] T002 [P] Create `src/doc_generator/overview/__init__.py` with the package docstring stating the invariant verbatim from contract Â§1 (`evidence` and `grounding` take no LLM engine argument, not even an optional one; `narrator` is the only module that accepts one). Re-export `PROVIDER_TOKEN_BUDGET` and `CHARS_PER_TOKEN` from `doc_generator.features`; do not redefine them.
- [X] T003 [P] Delete the stale, sourceless `src/doc_generator/__pycache__/section_narrator.*.pyc` files (research Decision 0). Confirm with a grep that nothing imports `section_narrator`.

---

## Phase 2: Foundational (shared, narrator-free leaves)

**Purpose**: Deterministic helpers that User Story 1 (README lead) and User Story 4 (module descriptions) both need. **Neither task imports `doc_generator.overview`**, which is what keeps User Story 4 independent of the narrator.

- [X] T004 [P] Write `tests/unit/test_plain_text.py`:
  - `test_leading_atx_heading_is_stripped`
  - `test_emphasis_code_and_html_markers_are_removed`
  - `test_links_reduce_to_their_text`
  - `test_whitespace_collapses`
  - `test_cut_at_last_sentence_boundary_within_cap`
  - `test_cut_at_word_boundary_with_ellipsis_when_no_sentence_fits`
  - `test_never_cuts_mid_word`
  - `test_empty_and_heading_only_input_yield_empty`
  - `test_the_nextgen_readme_row_becomes_plain_text`, using the exact README string from research Decision 12
- [X] T005 Implement `src/doc_generator/plain_text.py::excerpt(text, max_chars=MAX_MODULE_DESCRIPTION_CHARS)` with `MAX_MODULE_DESCRIPTION_CHARS = 160`, per research Decision 12. Stdlib `re` only. Makes T004 pass.

**Checkpoint**: Foundation ready. User Story 4 can start now, in parallel with User Story 1.

---

## Phase 3: User Story 1 â€” Read what the repository is before what it contains (Priority: P1) ðŸŽ¯ MVP

**Goal**: One to four grounded, marked paragraphs directly under the Overview's title say what the repository is, name its major subsystems as links, and describe where work enters and ends up. The page's structure is unchanged without a provider; an unchanged repository regenerates identical Markdown.

**Independent Test**: Index a repository with a provider. One to four `.ai-generated` paragraphs (two to four requested) precede the repository facts, each cites at least one real file, module or symbol, every backticked name is a link, and every subsystem link opens. Then regenerate with a failing engine: the same headings and link destinations, and no prose (quickstart Â§2â€“Â§4).

### Tests for User Story 1 (write first; confirm they fail)

- [X] T006 [P] [US1] Write `tests/unit/test_overview_package.py::test_only_the_narrator_accepts_an_engine`. It walks every public function and class constructor in `doc_generator.overview.evidence` and `doc_generator.overview.grounding` with `inspect.signature`, and asserts that no parameter is named `llmEngine`, `engine` or `llm_engine`. It also asserts that neither module's source imports `local_llm` (contract Â§1).
- [X] T007 [P] [US1] Write `tests/unit/test_manifest_overview_narratives.py`:
  - `test_save_then_load_by_key_round_trips_reply_and_handle_map`
  - `test_load_with_a_different_key_is_a_miss`
  - `test_load_latest_ignores_the_key`
  - `test_save_overwrites_the_single_row_per_repository`
  - `test_unreadable_handle_map_json_is_a_miss_not_a_crash`
  - `test_schema_appears_on_an_existing_database_without_migration`, which opens a manifest created before the table existed
- [X] T008 [P] [US1] Write `tests/unit/test_overview_evidence.py`, building features with `features.validate.repair` over hand-written candidates (the pattern `tests/unit/test_feature_validate.py` uses):
  - `test_features_follow_navigation_order_and_cap_at_max_prompted_features`
  - `test_omitted_feature_count_counts_the_rest`
  - `test_handles_are_f0_to_fn_in_navigation_order`
  - `test_major_feature_keys_skip_tooling_and_cap_at_eight`
  - `test_anchor_summary_prefers_docstring_then_generated_summary_first_sentence_capped_at_120`
  - `test_member_names_exclude_the_anchor_and_cap_at_three`
  - `test_entry_flows_rank_by_modules_reached_then_stable_key_and_cap_at_six`
  - `test_reached_handles_are_ordered_by_first_contact_depth_and_cap_at_five`
  - `test_readme_lead_is_the_first_prose_paragraph_after_the_title`
  - `test_readme_lead_is_empty_without_a_readme`
  - `test_building_twice_gives_equal_evidence`
- [X] T009 [P] [US1] Write `tests/unit/test_overview_narrator.py`. **The budget tests are computed from the constants, never from a literal.**
  - `test_worst_case_call_fits_the_provider_budget` asserts `worst_case_call_tokens() <= PROVIDER_TOKEN_BUDGET`.
  - `test_the_budget_arithmetic_is_the_documented_one` recomputes `(SYSTEM_PROMPT_CHARS + HEADER_CHARS + MAX_README_LEAD_CHARS + MAX_README_PROMPT_CHARS + MAX_PROMPTED_FEATURES * FEATURE_BLOCK_CHARS + MAX_PROMPTED_ENTRY_FLOWS * ENTRY_FLOW_CHARS) // CHARS_PER_TOKEN` independently and adds `MAX_NARRATIVE_RESPONSE_TOKENS`.
  - `test_raising_a_cap_would_break_the_budget` monkeypatches `MAX_PROMPTED_FEATURES` Ã—4 and expects the budget to be exceeded.
  - `test_system_prompt_fits_its_declared_size`
  - `test_a_real_prompt_stays_under_the_worst_case`, using maximum-size evidence
  - `test_prompt_sets_low_reasoning_effort_and_the_response_cap`
  - `test_prompt_asks_for_two_to_four_lead_paragraphs_each_citing_a_listed_name` (FR-005, FR-007; the minimum is a request, SC-007)
  - `test_no_feature_key_or_url_reaches_the_prompt`
  - `test_no_features_yields_skipped_with_reason_no_features_and_makes_no_call` (spec edge case "no subsystems at all")
  - `test_cache_key_is_stable_for_equal_evidence`
  - `test_cache_key_changes_when_any_prompt_line_changes`
  - `test_cache_hit_returns_cached_before_checking_availability`
  - `test_unavailable_engine_yields_unavailable`
  - `test_runtime_error_yields_failed`
  - `test_empty_reply_yields_unparseable`
  - `test_unparseable_reply_is_not_saved`
  - `test_a_parseable_reply_is_saved_with_its_handle_map_even_if_nothing_grounds`
  - `test_an_attribute_error_is_not_disguised_as_an_unavailable_provider`
  - `test_the_narrator_calls_the_provider_chain_not_the_engine_directly`
  - `test_failure_with_an_earlier_row_returns_stale_with_the_stored_handle_map`, parametrized over unavailable, failed and unparseable
  - `test_a_failure_never_overwrites_the_earlier_row`
  - `test_parse_accepts_an_object_with_a_lead`
  - `test_parse_accepts_json_wrapped_in_prose`
  - `test_parse_rejects_a_list_prose_and_empty_objects`
- [X] T010 [P] [US1] Write `tests/unit/test_overview_grounding.py`, one test per rule on hand-written replies with no model (contract Â§3):
  - `test_empty_paragraph_is_dropped` (G1)
  - `test_unbalanced_backtick_rejects_the_paragraph` (G2)
  - `test_unknown_handle_rejects_the_paragraph` (G3)
  - `test_a_stale_handle_to_a_vanished_feature_rejects_the_paragraph` (G3)
  - **`test_a_fabricated_symbol_rejects_its_paragraph`** (G4)
  - `test_an_ambiguous_bare_name_rejects_its_paragraph` (G4)
  - `test_a_repo_relative_module_path_is_accepted` (G4)
  - `test_an_unbackticked_snake_case_fabrication_rejects` (G5)
  - `test_an_unbackticked_fabricated_camelcase_rejects` (G5)
  - `test_a_detected_language_name_is_allowed` (G5)
  - `test_second_person_rejects` (G6)
  - `test_a_banned_promotional_term_rejects` (G6)
  - `test_a_lead_paragraph_without_a_resolved_name_rejects` (G7)
  - `test_a_lead_paragraph_citing_only_a_subsystem_handle_rejects` (G7, constitution Â§2.4)
  - `test_the_lead_is_trimmed_to_four_paragraphs` (G9)
  - `test_the_word_budget_trims_from_the_end` (G9)
  - `test_a_rejected_opening_paragraph_withholds_the_lead` (G10)
  - `test_a_rejected_later_paragraph_leaves_the_others_in_order` (FR-010)
  - `test_ground_none_equals_all_rejected`
  - `test_render_paragraph_neutralises_markdown_and_html_injection`, where a reply made of `#`, `|`, `<script>`, `[x](y)` and `{: .c }` renders none of them as structure (FR-004)
  - `test_render_paragraph_links_handles_to_their_feature_pages`
- [X] T011 [P] [US1] Write `tests/integration/test_overview_page.py`, using `build_indexed_repo` + `wrap_llm(RecordingLLMEngine(...))`:
  - **`test_no_engine_page_has_the_same_outline`**, parametrized over **five** cases matching FR-014 and SC-004:
    - not configured (`overviewNarrator=None`);
    - unreachable (`isAvailable()` false);
    - chain exhausted (`RuntimeError`);
    - refused (empty reply);
    - unusable (unparseable reply).

    Heading sequence equal; set of `href`s outside `.ai-generated` equal; no `.ai-generated` element; no placeholder text.

    **Each no-provider page is generated into a fresh output root with a fresh manifest store that holds no `doc_overview_narratives` row.** The with-provider reference page is generated separately. Otherwise, per FR-014, FR-015 and contract Â§2 step 2, the narrator correctly returns `cached` or `stale` and prose appears.
  - `test_an_already_narrated_unchanged_repository_keeps_its_prose_without_a_provider` (FR-014, FR-016): same store, second run with an unavailable engine, identical `index.md`.
  - `test_no_subsystems_means_no_lead_and_a_skip_notice` (spec edge case, contract Â§7)
  - **`test_unchanged_repository_regenerates_identical_markdown`**: two `incremental=False` runs; `index.md` bytes equal; the second run makes 0 engine calls.
  - `test_the_lead_precedes_every_list_table_and_diagram`
  - `test_every_backticked_name_in_the_lead_renders_as_a_link`
  - `test_removed_symbol_drops_its_paragraph_on_the_next_incremental_pass` (FR-017)
  - `test_incremental_pass_on_an_unchanged_repository_does_not_rewrite_home`
  - `test_changed_repository_without_provider_shows_the_earlier_narrative_marked_stale` (FR-017a, US1 #10)
  - `test_the_structure_pass_does_not_narrate` (`narrateOverview=False` gives 0 calls)
  - `test_on_notice_receives_the_contract_line_for_each_outcome` (contract Â§7)
  - `test_home_has_no_inline_mermaid_and_no_last_indexed_line`
  - `test_features_list_shows_titles_only` (FR-012a)
- [X] T012 [P] [US1] Write `tests/integration/test_cli_overview_wiring.py` (moved from `tests/unit/` during implementation: it reuses `test_cli.py`'s `cli_home`/`fake_engines` fixtures the way `test_serve_refreshes_wiki_shell.py` does):
  - `test_index_wires_the_narrator_with_the_planners_engine_and_echo`, which monkeypatches `cli.index_command.DocGenerator` to capture kwargs
  - `test_index_structure_pass_passes_narrate_overview_false`
  - `test_serve_wires_the_narrator_with_the_summary_executor`

  These guard the runtime-only failure 033's T060 recorded.

### Implementation for User Story 1

- [X] T013 [US1] Add the `doc_overview_narratives` table to `SCHEMA_STATEMENTS` in `src/doc_generator/manifest_store.py` (columns per data-model), plus `load_overview_narrative`, `load_latest_overview_narrative` and `save_overview_narrative`. They mirror `load_feature_plan`/`save_feature_plan`: bad JSON and exceptions are a miss, never a crash; one row per repository. Makes T007 pass.
- [X] T014 [US1] Add `find_readme(repository_root) -> Path | None` to `src/doc_generator/features/evidence.py`, and make `read_readme_bullets` use it. This is a pure refactor of the `_README_CANDIDATES` loop: `tests/unit/test_feature_evidence.py` and `tests/unit/test_feature_planner.py` must pass unchanged. Add `test_find_readme_follows_candidate_order` to `tests/unit/test_feature_evidence.py`.
- [X] T015 [US1] Implement `src/doc_generator/overview/evidence.py`: `FeatureBrief`, `EntryFlow`, `OverviewEvidence`, `build_overview_evidence`, `read_readme_lead` (via `find_readme` + `plain_text.excerpt`), and the constants `MAX_README_LEAD_CHARS=600`, `MAX_PROMPTED_FEATURES=12`, `MAX_PROMPTED_ENTRY_FLOWS=6`. The depth-tracking BFS is bounded by `features.evidence.MAX_EVIDENCE_CALL_DEPTH`. **No engine parameter anywhere.** Makes T008 and the evidence half of T006 pass.
- [X] T016 [US1] Implement `src/doc_generator/overview/grounding.py` rules G1â€“G7, G9 and G10, plus `ground(reply, evidence, lookup, *, handle_map, is_stale=False)`, `render_paragraph`, `GroundedNarrative` (with `leadWithheld` and `isStale`), `Segment`, `GroundedParagraph`, `Rejection`, `BANNED_PROMOTIONAL_TERMS`, `MAX_LEAD_PARAGRAPHS=4` and `MAX_NARRATIVE_WORDS=600`. G4/G5 resolve through `cross_references.resolve_reference`; text segments go through `markdown_render._markdown_escape`. **No engine parameter.** Makes T010 (including **`test_a_fabricated_symbol_rejects_its_paragraph`**) and the grounding half of T006 pass. G8, G11 and `accept_description` belong to User Story 2.
- [X] T017 [US1] Implement `src/doc_generator/overview/narrator.py`: `OverviewNarrator` (constructor mirrors `FeaturePlanner`), `build_overview_prompt` asking for `{"lead": [...]}` only, `narrative_cache_key`, `parse_narrative_reply`, `NarrativeReply`, `NarrationOutcome` (including `stale`), `worst_case_prompt_tokens`, `worst_case_call_tokens`, `SYSTEM_PROMPT` and the constants from data-model Â§ Constants. `NARRATIVE_FORMAT_VERSION = "1"`. Follow the step order in contract Â§2 exactly: cache before availability; `run(lambda engine: engine.generate(prompt))`; catch `RuntimeError` only; the stale fallback never overwrites. Makes T009 pass, including **`test_worst_case_call_fits_the_provider_budget`**, `test_the_budget_arithmetic_is_the_documented_one` and `test_raising_a_cap_would_break_the_budget`.
- [X] T018 [US1] Export `OverviewNarrator` from `src/doc_generator/__init__.py`, next to `FeaturePlanner`.
- [X] T019 [US1] In `src/doc_generator/generator.py`:
  - `_ensure_features` keeps the `RepositoryEvidence` as `self._repository_evidence`.
  - `DocGenerator.__init__` gains `overviewNarrator` and `onNotice`.
  - `generateRepositoryDocumentation` / `_generate_repository_documentation` gain `narrateOverview: bool = True`.
  - `generateOverviewPage` loses `classDiagramSource` and gains the narrative: build evidence â†’ `narrate` (or `skipped`) â†’ `ground` against `self._symbol_lookup` â†’ `render_paragraph` â†’ `lead_paragraphs` + `lead_is_stale`.
  - Emit at most one `onNotice` line per contract Â§7.
  - Stop passing `classDiagramSource=self._class_diagram_source()` at the home call site (line 841).

  Tests: T011 `test_no_engine_page_has_the_same_outline`, `test_on_notice_receives_the_contract_line_for_each_outcome`, `test_changed_repository_without_provider_shows_the_earlier_narrative_marked_stale`, `test_the_structure_pass_does_not_narrate`.
- [X] T020 [US1] In `src/doc_generator/generator.py`, on an incremental run where `home` is not otherwise targeted, **always** build the home page, and write it only when `writer._content_hash(page.contentMarkdown)` differs from the stored manifest `contentHash` for `home` (research Decision 7; contract Â§5). **Use that function, not another digest**: the stored value is SHA-1 (`writer.py` 202â€“203), and any other algorithm never matches, so the page would be rewritten every pass. Tests: T011 `test_removed_symbol_drops_its_paragraph_on_the_next_incremental_pass`, `test_incremental_pass_on_an_unchanged_repository_does_not_rewrite_home`, **`test_unchanged_repository_regenerates_identical_markdown`**.
- [X] T021 [US1] Edit `src/doc_generator/templates/home.md.jinja`:
  - emit `lead_paragraphs` immediately under the H1, each followed by `{: .ai-generated }`;
  - when `lead_is_stale` and there is at least one paragraph, add the `.summary-stale` caveat line from contract Â§6;
  - delete line 5 (`Last indexed`);
  - delete the inline `mermaid` block (lines 23â€“28), keeping both diagram links;
  - reduce the Features list (line 41) to `[title](link)`, with no description (FR-012a).

  Tests: T011 `test_the_lead_precedes_every_list_table_and_diagram`, `test_home_has_no_inline_mermaid_and_no_last_indexed_line`, `test_features_list_shows_titles_only`, `test_every_backticked_name_in_the_lead_renders_as_a_link`.
- [X] T022 [US1] Update `tests/unit/test_doc_generator_home_overview.py` for the new outline. Keep the counts sentence, the `| Feature | Modules |` table (it is replaced only in User Story 2) and `## Modules`; the Features list no longer carries descriptions.
- [X] T023 [P] [US1] Add the adjacent-`.ai-generated` rule to `frontend/src/styles.css`, next to the existing `.ai-generated` block (line 256): siblings join into one block, with the badge on the first only; existing tokens only. Rebuild with `npm run build` in `frontend/` to regenerate `src/doc_generator/assets/wiki-ui.css`. Run `npm test` in `frontend/` to confirm nothing else changed.
- [X] T024 [US1] Wire `src/cli/index_command.py` and `src/cli/serve_command.py`:
  - In `index_command.py` (next to line 479), pass `overviewNarrator=OverviewNarrator(llm_engine, cache=manifest_store)` and `onNotice=typer.echo`, and pass `narrateOverview=False` to the `GENERATING_DOCS_STRUCTURE` call only (line 483).
  - In `serve_command.py` (next to line 124), pass `overviewNarrator=OverviewNarrator(summary_executor, cache=manifest_store)` and `onNotice=typer.echo`.

  Makes T012 pass.
- [X] T025 [US1] Run the full suite and compare against `<scratchpad>\baseline.txt`. Every test from T006â€“T012 passes, and there is no new failure.

### Manual verification for User Story 1 (prose cannot be judged by a unit test)

- [X] T026 [US1] Index both reference repositories: `codepedia index C:\Users\ASUS\IdeaProjects\codepedia-sample-repo` and `codepedia index C:\Users\ASUS\IdeaProjects\codepedia`. Record each run's `overview:` notice line, if any.
- [X] T027 [US1] **Read both Overview pages end to end** (`<state>\docs\index.html` and `index.md`) against quickstart Â§2 items 1â€“8. Record every failure with the offending sentence in `<scratchpad>\us1-review.md`.
- [X] T028 [US1] **The stranger test (SC-001)**, in two steps, with the implementer never acting as reviewer:
  1. **Answer key first.** Before anyone reads the new Overview, write `<scratchpad>\sc001-key-<repo>.md` for each repository from the code alone. It lists the major subsystems and the places where operations begin.
  2. **An independent reviewer.** Give a fresh AI session (a new subagent with no repository access and no conversation history), or a person who has not seen the repository, **only** the generated `index.md`. Ask them to name the main subsystems and where an operation begins, within the five-minute reading budget.

  Score their answers against the key. Record the key, the answers, the score, whether a newcomer would now understand how the project works, and which paragraph failed them if not, in `<scratchpad>\us1-review.md`. Also record any lead of fewer than two paragraphs on a repository with at least two subsystems (SC-007's review-only minimum).
- [X] T029 [US1] **The tense review (SC-013)**: copy every generated sentence from both Overviews into `<scratchpad>\tense-review-<repo>.md` and mark each one declarative present or not. The expected count of "not" is zero.
- [X] T030 [US1] No-provider check (quickstart Â§3): with `<scratchpad>\nopro_check.py` on a copy of the sample repository's state, run with no narrator at all (`overviewNarrator=None`), and with engines that raise `RuntimeError`, return `""`, and return `"not json"`, each against a store with the narrative row deleted. Confirm the outlines are equal and no prose remains. Then run `--keep-cache` and confirm the earlier narrative shows with its stale caveat.
- [X] T031 [US1] Rerun check (quickstart Â§4): re-index the sample repository and `git diff --no-index` the two `index.md` files; the diff must be empty. The HTML may differ only in the footer's timestamp. Start `serve` and confirm `index.md`'s write time is unchanged.
- [X] T032 [US1] Appearance (quickstart Â§5): both `<state>\docs\index.html` Overviews in light and dark, at about 400 px and at full width. The lead reads as one marked block with one badge, and there is no horizontal scroll.
- [X] T033 [US1] Cost (quickstart Â§6): with `<scratchpad>\cost.py`, record the real prompt tokens, the response cap, their sum and `worst_case_call_tokens()` for both repositories, for the implementation report.

**Checkpoint**: User Story 1 is complete and demonstrable on its own. **Stop here and report before any User Story 2 task** (runbook stage 6).

---

## Phase 4: User Story 2 â€” See the subsystems as a map, not a tally (Priority: P2)

**Goal**: The count table becomes a subsystems table (subsystem, responsibility, where to start), followed by at most eight grounded paragraphs of up to three sentences, one per major subsystem, each ending in a link to that subsystem's page.

**Independent Test**: Open an Overview. The table lists every subsystem once, in navigation order, with a linked starting module that belongs to it. It appears unchanged with no provider. The paragraphs beneath it end in working subsystem links (spec US2).

### Tests for User Story 2

- [ ] T034 [P] [US2] Extend `tests/unit/test_overview_grounding.py`:
  - `test_a_subsystem_paragraph_citing_no_resolved_name_rejects` (G7 applies to subsystem paragraphs too, FR-025)
  - `test_a_four_sentence_subsystem_paragraph_rejects` (G8)
  - `test_sentence_counting_ignores_dotted_names_and_abbreviations` (G8)
  - `test_subsystem_paragraphs_follow_table_order_not_reply_order` (G11)
  - `test_a_withheld_subsystem_paragraph_leaves_the_others` (FR-025a)
  - `test_only_major_features_receive_paragraphs_and_at_most_eight`
  - `test_accept_description_rejects_second_person_and_fabricated_names`
  - `test_accept_description_passes_a_plain_sentence_through_escaped`
- [ ] T035 [P] [US2] Extend `tests/unit/test_overview_narrator.py`:
  - `test_prompt_asks_for_subsystem_paragraphs_keyed_by_handle`
  - `test_format_version_two_changes_the_cache_key`
  - `test_parse_reads_the_subsystems_object`

  **Re-run `test_worst_case_call_fits_the_provider_budget` unchanged**: the response cap already covers User Story 2.
- [ ] T036 [P] [US2] Write `tests/integration/test_overview_subsystems.py`:
  - `test_subsystems_table_lists_every_feature_once_in_navigation_order`
  - `test_start_with_module_belongs_to_its_subsystem_and_prefers_the_most_entry_points`
  - `test_the_table_is_complete_without_a_provider`
  - `test_each_paragraph_ends_with_its_subsystem_link`
  - `test_a_withheld_paragraph_keeps_its_table_row`
  - `test_a_failing_description_renders_a_dash`
  - `test_generated_column_header_is_labelled_only_when_a_planned_description_is_shown`
  - `test_the_features_list_is_gone_and_every_subsystem_is_still_reachable`

### Implementation for User Story 2

- [ ] T037 [US2] In `src/doc_generator/overview/grounding.py`, add G8 (`MAX_SUBSYSTEM_SENTENCES=3`), G11, the `subsystems` half of `ground` (`MAX_SUBSYSTEM_PARAGRAPHS=8`, keys âŠ† `majorFeatureKeys`) and `accept_description`. **No engine parameter.** Makes T034 pass, and T006 still passes.
- [ ] T038 [US2] In `src/doc_generator/overview/narrator.py`, extend `SYSTEM_PROMPT` and `build_overview_prompt` to request `"subsystems": {"<handle>": "..."}` for the major features, extend `parse_narrative_reply`, and set `NARRATIVE_FORMAT_VERSION = "2"`. Makes T035 pass. **`test_worst_case_call_fits_the_provider_budget`, `test_the_budget_arithmetic_is_the_documented_one` and `test_raising_a_cap_would_break_the_budget` must still pass without their constants being touched.**
- [ ] T039 [US2] In `src/doc_generator/generator.py`, build `subsystem_rows`: title link; responsibility = `accept_description(...)` for planned features, else `""`; start-with module = the member with the most entry points (`self._repository_evidence.entryPointKeysByModuleKey`), ties by label, else the anchor, linked to its module page. Also build `subsystem_paragraphs`: `render_paragraph` plus a trailing link to the feature page, and `responsibility_is_generated`. Tests: T036, plus **`test_no_engine_page_has_the_same_outline`** and **`test_unchanged_repository_regenerates_identical_markdown`** re-run against the User Story 2 outline.
- [ ] T040 [US2] In `src/doc_generator/templates/home.md.jinja`, replace the `| Feature | Modules |` table with `| Subsystem | Responsibility | Start with |`, whose header reads `Responsibility (AI-generated)` when `responsibility_is_generated` and whose empty cells show `â€”`. Render `subsystem_paragraphs` beneath it, each with `{: .ai-generated }`. Delete the `## Features` list (the table supersedes it). When the lead was withheld but stale subsystem paragraphs remain, put the stale caveat under the last paragraph (contract Â§6). Update `tests/unit/test_doc_generator_home_overview.py` to the new outline.
- [ ] T041 [US2] Run the full suite against `<scratchpad>\baseline.txt`: T034â€“T036 and every User Story 1 test pass.

### Manual verification for User Story 2

- [ ] T042 [US2] Re-index both reference repositories and re-read both Overviews end to end. Check that:
  - the table and paragraphs are in step, in the same order;
  - each paragraph is at most three sentences and ends in its link;
  - total generated prose is under 600 words (SC-007);
  - the stranger test still holds (SC-001).

  Extend `<scratchpad>\tense-review-<repo>.md` with the new paragraphs and the table's generated cells (SC-013).
- [ ] T043 [US2] Appearance of both `<state>\docs\index.html` Overviews at about 400 px and full width, light and dark: the table scrolls inside itself when narrow, with no page overflow.

**Checkpoint**: User Stories 1 and 2 both work; the page is the full first-release narrative.

---

## Phase 5: User Story 3 â€” Getting started (Priority: P3) â€” DEFERRED

Not in this release (spec Clarifications Q4). Its design is fixed in research Decision 5 and contract Â§8. **No tasks are generated.** A later `/speckit-tasks` run adds them against FR-026â€“FR-028.

---

## Phase 6: User Story 4 â€” A module list that can be read (Priority: P4)

**Goal**: No stray punctuation, no two identical labels, and plain-text descriptions that end cleanly. Every row keeps its module and dependency links.

**Independent Test**: On the sample repository, the module list shows eight distinguishable `__init__` rows, no orphaned `(` or `)`, and a README row in plain text ending at a boundary (spec US4).

**Independence**: every task here touches only `prose.py`, `plain_text.py` (from Phase 2), the module-list block of `generator.py`, and the module-list lines of `home.md.jinja`. **Nothing imports `doc_generator.overview`.** After Phase 2 this phase can run before, alongside, or instead of User Stories 1 and 2.

### Tests for User Story 4

- [ ] T044 [P] [US4] Write `tests/unit/test_prose_labels.py`:
  - `test_unique_code_labels_are_unchanged`
  - `test_duplicate_init_modules_get_the_shortest_unique_path_tail`
  - `test_prose_files_keep_their_display_label`
  - `test_labels_are_deterministic_across_input_order`
  - `test_a_label_never_includes_the_extension`
- [ ] T045 [P] [US4] Write `tests/integration/test_overview_module_list.py`, with a fixture holding two `__init__.py` files, a README with a heading and emphasis, and a module with no docstring:
  - `test_no_row_contains_orphaned_punctuation`
  - `test_no_two_rows_share_a_visible_label`
  - `test_a_prose_description_contains_no_raw_markup`
  - `test_a_long_description_ends_at_a_boundary_with_an_ellipsis`
  - `test_every_row_keeps_its_module_and_dependency_links`
  - `test_the_module_list_is_identical_with_and_without_a_narrator`

### Implementation for User Story 4

- [ ] T046 [US4] Add `disambiguated_labels(modules, repository_root) -> dict[str, str]` to `src/doc_generator/prose.py`, per research Decision 12. It is display-only: slugs, page ids and stored links keep deriving from `module.name`. Makes T044 pass.
- [ ] T047 [US4] In `src/doc_generator/generator.py`'s `generateOverviewPage` module-entry loop (lines 131â€“155), add `label` from `disambiguated_labels` and `description` from `plain_text.excerpt(module.docstring)`. Sort by label. Link `label` values stay `module.name`-based for page ids.
- [ ] T048 [US4] In `src/doc_generator/templates/home.md.jinja`, change the module row (line 52) to `- [{{ entry.label | mdesc }}](â€¦){% if entry.description %} â€” {{ entry.description | mdesc }}{% endif %} [dependencies](â€¦)`, with no parentheses around the dependency link. **No CSS change** (research Decision 12). Makes T045 pass. Run the full suite against the baseline.
- [ ] T049 [US4] Manual: re-index `codepedia-sample-repo`. In the module list, confirm eight distinguishable `__init__` rows, no loose punctuation at either edge in light and dark at about 400 px, and a README row that reads as a plain sentence.

**Checkpoint**: All first-release stories work independently.

---

## Phase 7: Polish & Cross-Cutting

- [ ] T050 [P] Update `docs/architecture.md` per its "> Maintenance:" rule: the new `doc_generator/overview/` package with its one-engine-taker invariant, the `doc_overview_narratives` table in `doc-manifest.sqlite`, and the Overview's always-recomputed, write-if-changed regeneration.
- [ ] T051 [P] Update `docs/diagrams/class-diagram.md` per its "> Maintenance:" rule with `OverviewNarrator`, `OverviewEvidence`, `GroundedNarrative` and their relationships to `DocGenerator`, `FeaturePlanner` and `DocPageManifestStore`.
- [ ] T052 [P] Update `README.md`'s description of the generated wiki: the Overview now opens with a grounded, AI-generated explanation. Confirm `docs/stack.md` needs no change, since no dependency was added.
- [ ] T053 Run the whole of `quickstart.md` (Â§1â€“Â§6) once more on the final tree, and attach the results to the implementation report: files touched, where narration lives and why, tokens per run from T033, and the generated sample-repository `index.md`.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after Setup. Blocks User Story 1 (the README lead uses `excerpt`) and User Story 4.
- **User Story 1 (Phase 3)**: after Foundational. **Must reach its checkpoint, including the manual tasks T026â€“T033, before any User Story 2 task starts.**
- **User Story 2 (Phase 4)**: after User Story 1. It extends User Story 1's narrator and grounding, and the same template and generator code.
- **User Story 3 (Phase 5)**: deferred, no tasks.
- **User Story 4 (Phase 6)**: after Foundational only. **Independent of User Stories 1 and 2**; it shares files with them (`generator.py`, `home.md.jinja`) but not code paths, so run it sequentially with whichever story holds those files.
- **Polish (Phase 7)**: after the stories being shipped.

### Within User Story 1

- T006â€“T012 (tests) first; they fail.
- T013 â†’ T015 â†’ T016 â†’ T017 are ordered because each needs the previous one's types. T014 can run alongside T013.
- T018 â†’ T019 â†’ T020 â†’ T021 â†’ T022 are sequential, sharing `generator.py` and the template.
- T023 [P] can run any time after T021 settles the markup.
- T024 comes after T018.
- T025, then the manual tasks T026â€“T033.

### Within User Story 2

T034â€“T036 (tests) â†’ T037 â†’ T038 â†’ T039 â†’ T040 â†’ T041 â†’ T042â€“T043.

### Within User Story 4

T044 and T045 (tests) â†’ T046 â†’ T047 â†’ T048 â†’ T049.

---

## Parallel Examples

```text
# User Story 1 tests, all separate files:
T006 tests/unit/test_overview_package.py
T007 tests/unit/test_manifest_overview_narratives.py
T008 tests/unit/test_overview_evidence.py
T009 tests/unit/test_overview_narrator.py
T010 tests/unit/test_overview_grounding.py
T011 tests/integration/test_overview_page.py
T012 tests/unit/test_cli_overview_wiring.py

# After Phase 2, User Story 4 alongside User Story 1's early tasks:
T044 tests/unit/test_prose_labels.py    ||  T013 manifest_store.py
T046 src/doc_generator/prose.py         ||  T015 overview/evidence.py

# Polish documents together:
T050 docs/architecture.md  ||  T051 docs/diagrams/class-diagram.md  ||  T052 README.md
```

---

## Implementation Strategy

### MVP: User Story 1 only (the runbook's stage 6)

1. Phase 1 â†’ Phase 2 â†’ Phase 3 (T001â€“T033).
2. **Stop.** Report the files touched, where narration lives and why (research Decision 1), the tokens per run (T033), and the generated `index.md` for `codepedia-sample-repo`.
3. Correct the narrative's tone on those paragraphs before the page grows.

### Incremental delivery

1. User Story 1 â†’ review â†’ User Story 2 â†’ review.
2. User Story 4 at any point after Phase 2, including first, as it needs no model.
3. User Story 3 in a later release.

---

## Notes

- A task that touches the narrator names its tests; a task is done when its named tests pass, not when its code compiles.
- The four required tests are T009 (budget), T010 (fabricated symbol), and T011 (no-engine outline, byte-identical rerun). Each is re-run at T039 against the User Story 2 outline.
- `checklists/narrative.md` is reviewer-owned; implementation must not tick it.
- Commit after each task or logical group.
