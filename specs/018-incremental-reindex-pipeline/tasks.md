# Tasks: Incremental Reindexing Pipeline

## Phase 1: Setup

**Goal:** Create the `reindex_pipeline` package skeleton every downstream task depends on.

**Independent test criteria:** `import reindex_pipeline` succeeds against the empty package.

- [X] T001 [P] Create `src/reindex_pipeline/__init__.py` (empty package marker) per the `Project Structure` in `plan.md`.

## Phase 2: Foundational

**Goal:** Build the shared data model, the two small extensions to existing components, and the per-file classification/graph-sync/embedding helpers every user story depends on, plus the `IncrementalReindexPipeline` skeleton.

**Independent test criteria:** `DependencyGraph.remove_source_file(source_file)` removes a file's nodes/edges and nothing else; `PathClassification`/`ChangeConfirmation` can be constructed and correctly classify a sample excluded/binary/unsupported-language file.

- [X] T002 [P] Create `src/reindex_pipeline/models.py` with the `ReindexBatch`, `ChangeConfirmation`, `PathClassification`, and `ReindexOutcome` dataclasses, per `data-model.md`.
- [X] T003 [P] Add `DependencyGraph.remove_source_file(source_file: str)` to `src/dependency_graph/graph.py`: removes every node whose `sourceFile` equals the given value and every edge attached to a removed node, per `data-model.md` "New extension: DependencyGraph.remove_source_file" and `research.md` §4.
- [X] T004 [P] Create `src/reindex_pipeline/classification.py` implementing per-path classification (`PathClassification`, via `repo_scanner.ignore.IgnoreMatcher`, `repo_scanner.binary.is_binary_path`, `repo_scanner.language.LanguageDetector`, 001) and hash-confirmation (`ChangeConfirmation`, via `repository_metadata.fingerprints.compute_content_hash` + `RepositoryMetadataStore.has_file_changed`, 005), per `research.md` §1 and §3. Depends on T002.
- [X] T005 [P] Create `src/reindex_pipeline/graph_sync.py` with a function that loads the persisted dependency graph by the repository's stable id (`repository_metadata.sqlite_store.stable_repository_id`), records its current `EdgeId` set, applies `remove_source_file` (T003) plus `ingest_inventory` for each file needing reprocessing, applies `remove_source_file` alone for each deleted file, saves the graph back under the same id, and **returns the set of `EdgeId`s added or removed by this update** (diffed against the set recorded before mutation) for downstream documentation impact, per `research.md` §4 and §7. Depends on T003.
- [X] T006 [P] Create `src/reindex_pipeline/embeddings.py` with a function that builds one `CodeChunk` per in-scope symbol (module plus public, non-nested functions/classes, matching `CodeSummaryPipeline`'s own selection) from the symbol's source text, embeds it via the configured `EmbeddingEngine`, and calls `VectorIndex.reindexFile`/`removeChunksForFile` (006/007/009), per `research.md` §6. Depends on T002.
- [X] T007 [P] Create `src/reindex_pipeline/pipeline.py` with the `IncrementalReindexPipeline` class constructor (`repositoryRoot`, `metadataStore`, `dependencyGraphPath`, `summaryPipeline`, `vectorIndex`, `docGenerator`), per `contracts/incremental-reindex-pipeline.md`. Depends on T002.

**Checkpoint**: Foundation ready - user story implementation can now begin.

## Phase 3: User Story 1 - Documentation reflects a single edited file quickly

**Goal:** Modifying one file re-parses it, updates the dependency graph/metadata, regenerates only its (and its direct dependents') summary, updates only its embeddings, and regenerates only the affected documentation pages — with a result identical to a full re-index, achieved without ever scanning the whole repository.

**Independent test criteria:** `quickstart.md` "Validate a single-file update" — an incremental run's duration is far below a full re-index's (SC-001), and its result is identical to a full re-index's for the changed file and its dependents (SC-002).

- [X] T008 [P] [US1] Add a contract test in `tests/contract/test_reindex_pipeline_interface.py` (new file) asserting `IncrementalReindexPipeline` exposes `run(batch)` and accepts the constructor inputs listed in `contracts/incremental-reindex-pipeline.md`. Depends on T007.
- [X] T009 [US1] Implement `IncrementalReindexPipeline.run(batch)` in `src/reindex_pipeline/pipeline.py` for the created/confirmed-modified path: classify and hash-confirm every path in `batch` (T004); for each file needing reprocessing, re-parse it (`parser_engine.extract_symbols`) and call `RepositoryMetadataStore.store_inventory` (005); update the dependency graph for the whole batch via `graph_sync` (T005), capturing its returned changed-`EdgeId` set; call `CodeSummaryPipeline.summarizeRepository(changed_paths=...)` (010) once for the batch; update embeddings per reprocessed file via `embeddings.py` (T006); call `DocGenerator.generateRepositoryDocumentation(changedPaths=..., changedSymbolIds=..., changedDependencyEdgeIds=<graph_sync's returned EdgeId set>)` (012) once for the batch; and assemble the resulting `ReindexOutcome`, per `research.md` §8 and `data-model.md`'s state-flow diagram. Depends on T004, T005, T006, T007.
- [X] T010 [US1] Add an integration test in `tests/integration/test_reindex_pipeline.py` (new file, small real indexed sample repository) asserting that modifying one file's content results in: that file's symbols re-extracted and re-stored, its dependency-graph entries replaced with no duplicate/stale entries, only its (and its direct dependents') summary regenerated, only its embeddings updated, and only the documentation pages it affects regenerated — with every unrelated file's stored symbols, summary, embedding, and page untouched. Depends on T009.
- [X] T011 [US1] Add a timing assertion in `tests/integration/test_reindex_pipeline.py` comparing a single-file incremental `run()` call's duration against a full re-index of the same sample repository, confirming the incremental run is substantially faster, per `quickstart.md` "Validate a single-file update" step 5 (SC-001). Depends on T010 (same file).
- [X] T012 [US1] Add an integration test in `tests/integration/test_reindex_pipeline.py` that runs a full re-index and, separately from the same starting repository state, an incremental `run()` for the same single-file change, then asserts the two runs' resulting stored metadata, dependency graph, summaries, embeddings, and documentation are identical for the changed file and its direct dependents, per spec.md's "Consistency with a full re-index" requirement, `quickstart.md` "Validate a single-file update" step 6, and SC-002. Depends on T011 (same file).
- [X] T013 [US1] Add a test in `tests/integration/test_reindex_pipeline.py` asserting `IncrementalReindexPipeline.run()` never calls `repo_scanner.scanner.scan_repository` (e.g., via a spy/mock), per spec.md's "MUST NOT re-scan... regardless of repository size" requirement and `research.md` §1. Depends on T009; same file as T012, sequential.

**Checkpoint**: US1 is functional and independently testable — the pipeline's core single-file, batch-aware flow works end to end, is verified to match a full re-index, and is verified never to fall back to a full scan. This is the MVP.

## Phase 4: User Story 2 - Unreal changes are skipped

**Goal:** A `MODIFIED` file whose content hash hasn't actually changed triggers zero reprocessing.

**Independent test criteria:** `quickstart.md` "Validate the hash-confirmation skip" (SC-003).

- [X] T014 [P] [US2] Add an integration test in `tests/integration/test_reindex_pipeline.py` asserting that a batch containing a `MODIFIED` file whose current content hash matches its stored hash produces a `ReindexOutcome` listing it in `skippedPaths` (not `reprocessedPaths`), with no re-parsing, summary regeneration, embedding update, or documentation regeneration for it. Depends on T009.
- [X] T015 [P] [US2] Add a unit test in `tests/unit/test_reindex_pipeline.py` (new file) asserting `classification.py`'s hash-confirmation (T004) correctly reports `changed=False` for an unchanged file and `changed=True` for both a genuinely modified file and a file with no prior stored hash. Depends on T004.

**Checkpoint**: US1 and US2 work together — real changes are reprocessed, unreal ones are skipped, with zero wasted work.

## Phase 5: User Story 3 - New and removed files stay in sync

**Goal:** A created file becomes fully indexed and documented; a deleted file's symbols, embeddings, and pages fully disappear, including from pages that referenced it.

**Independent test criteria:** `quickstart.md` "Validate create/delete symmetry" (SC-005).

- [X] T016 [P] [US3] Add `RepositoryMetadataStore.delete_source_file(repository_root, path)` to `src/repository_metadata/store.py`, reusing the existing private `_delete_source_file_records` deletion logic in `src/repository_metadata/sqlite_store.py`, per `data-model.md` "New extension: RepositoryMetadataStore.delete_source_file" and `research.md` §2.
- [X] T017 [US3] Implement deleted-file handling in `IncrementalReindexPipeline.run(batch)` (`src/reindex_pipeline/pipeline.py`): for each `DELETED` file, apply `graph_sync`'s removal path (T005), call `RepositoryMetadataStore.delete_source_file` (T016), call `VectorIndex.removeChunksForFile` (T006), and let `DocGenerator.generateRepositoryDocumentation`'s existing removed-page handling (012) drop and propagate its documentation page. Depends on T009, T016.
- [X] T018 [P] [US3] Add an integration test in `tests/integration/test_reindex_pipeline.py`: a batch with one `CREATED` file results in its symbols, summary, embeddings, and a new documentation page all existing afterward. Depends on T010.
- [X] T019 [US3] Add an integration test in `tests/integration/test_reindex_pipeline.py`: a batch with one `DELETED` file results in its dependency-graph entries, stored metadata, and embeddings being removed, its documentation page removed, and any page that referenced it (e.g. a home page listing modules) regenerated to no longer reference it. Depends on T017 (same file as T018, sequential).

**Checkpoint**: US1, US2, and US3 work together — created and deleted files stay in sync with the index and documentation, alongside modified-file updates and unreal-change skipping.

## Phase 6: User Story 4 - Batches of changed files are processed together

**Goal:** Cross-file impact within one batch (e.g., a function calling into another changed file in the same batch) is captured in a single pass; a multi-file batch's result matches processing the same files as sequential single-file batches.

**Independent test criteria:** `quickstart.md` "Validate multi-file batch handling".

- [X] T020 [P] [US4] Add an integration test in `tests/integration/test_reindex_pipeline.py`: a batch with two files, where a function in file A calls a function in file B and both changed, results in both changed symbols and their direct dependents having their summaries and documentation regenerated exactly once each (via `ReindexOutcome.regeneratedSymbolIds`), not once per changed dependency. Depends on T010.
- [X] T021 [US4] Add an integration test in `tests/integration/test_reindex_pipeline.py` asserting that running the same two-file change as one multi-file batch versus two sequential single-file batches produces identical final stored metadata, dependency graph, summaries, embeddings, and documentation. Depends on T020 (same file).
- [X] T022 [US4] Confirm — and adjust `src/reindex_pipeline/pipeline.py`'s `run()` (T009) if needed — that the graph/metadata update step completes for every file in the batch before the single batch-wide summary-regeneration and documentation-regeneration calls run, per `research.md` §8's ordering guarantee, verified against T020. Depends on T009, T020.

**Checkpoint**: All four user stories are independently functional together — a single edited file, unreal-change skipping, create/delete symmetry, and multi-file batches all produce a result identical to a full re-index, far faster, and without ever scanning the whole repository.

## Phase 7: Polish & Cross-Cutting Concerns

**Goal:** Handle the remaining failure-mode guarantees from the contract, finalize the package's public exports, and validate the full quickstart end to end.

**Independent test criteria:** Every `quickstart.md` scenario passes against the finished implementation; `reindex_pipeline`'s public exports match the contract's surface.

- [X] T023 [P] Update `src/reindex_pipeline/__init__.py` to export `IncrementalReindexPipeline`, `ReindexBatch`, `ChangeConfirmation`, `PathClassification`, and `ReindexOutcome` via `__all__`, matching sibling packages' convention (e.g. `src/repo_watcher/__init__.py`). Depends on T007, T002.
- [X] T024 [P] Implement the remaining failure-surfacing guarantees from `contracts/incremental-reindex-pipeline.md` in `src/reindex_pipeline/pipeline.py`: when a file fails to re-parse, `ReindexOutcome` reports it clearly while other files in the batch and unaffected downstream steps still complete; when the local summarization model is unavailable, `ReindexOutcome.summaryFailure` is set and metadata/graph/embedding updates for the batch still complete. Depends on T009.
- [X] T025 Add unit tests in `tests/unit/test_reindex_pipeline.py` for both failure guarantees in T024 (a file with invalid syntax; a summary pipeline that raises `LocalLLMUnavailableError`). Depends on T024.
- [X] T026 Validate the end-to-end flow against `specs/018-incremental-reindex-pipeline/quickstart.md` (single-file update timing and consistency, hash-confirmation skip, create/delete symmetry, multi-file batch handling, local-LLM-unavailability resilience) and fix any mismatches. Depends on every prior task.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories.
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion; can then proceed in parallel or in priority order (US1 → US2 → US3 → US4).
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### Task-Level Dependencies

- `T001` has no dependencies.
- `T002` and `T003` each depend only on `T001`/nothing and touch different files (`models.py`, `dependency_graph/graph.py`), so both can run in parallel.
- `T004`, `T006`, and `T007` each depend only on `T002` and touch different files, so all three can run in parallel once `T002` lands. `T005` depends on `T003` and touches a different file (`graph_sync.py`) than `T004`/`T006`/`T007`, so it can run in parallel with them too, once `T003` lands.
- `T008` depends on `T007` (different file than `T009`, so it can run in parallel with it). `T009` depends on `T004`, `T005`, `T006`, and `T007` (the central integration point; touches `pipeline.py`, not concurrently written by any other Foundational/US1 task).
- `T010` depends on `T009`. `T011`, `T012`, and `T013` each depend on the previous one and share the same file (`tests/integration/test_reindex_pipeline.py`), so this whole chain (`T010` → `T011` → `T012` → `T013`) is sequential.
- `T014` and `T015` each depend on already-completed tasks (`T009`, `T004` respectively) and touch different files, so both can run in parallel.
- `T016` depends on nothing new (existing `store.py`) and touches a different file than `T014`/`T015`, so it can run in parallel with them. `T017` depends on `T009` and `T016` (same file as `T009`, `pipeline.py`, sequential after both land). `T018` depends on `T010` and touches the shared integration test file — the only task in this phase to do so alongside `T019` — so it is parallel-eligible relative to `T016`/`T017` (different files) but not relative to `T019`. `T019` depends on `T017` (and, same-file, on `T018` having landed first).
- `T020` depends on `T010` and touches the shared integration test file. `T021` depends on `T020` (same file, sequential). `T022` depends on `T009` and `T020` (different file, `pipeline.py`; only adjusted if `T020` reveals a gap).
- `T023` depends on `T002`/`T007` (needs every exported symbol to exist). `T024` depends on `T009` and touches `pipeline.py` (not concurrently touched elsewhere in this phase), so it can run in parallel with `T023`. `T025` depends on `T024`. `T026` depends on every prior task.

### Parallel Opportunities

- `T002`/`T003` (Foundational, first wave).
- `T004`/`T005`/`T006`/`T007` (Foundational, second wave, once `T002`/`T003` land).
- `T008`/`T009` (US1, once Foundational completes).
- `T014`/`T015` (US2).
- `T016`/`T018` (US3, different files from each other and from `T017`/`T019`).
- `T023`/`T024` (Polish).

## Parallel Execution Examples

### Foundational, second wave

```text
Task: T004 -> per-path classification + hash-confirmation in src/reindex_pipeline/classification.py
Task: T005 -> dependency-graph load/mutate/save (+ changed-EdgeId capture) in src/reindex_pipeline/graph_sync.py
Task: T006 -> per-symbol chunk building + VectorIndex calls in src/reindex_pipeline/embeddings.py
Task: T007 -> IncrementalReindexPipeline constructor in src/reindex_pipeline/pipeline.py
```

### After Foundational completes (User Story 1)

```text
Task: T008 -> contract test in tests/contract/test_reindex_pipeline_interface.py
Task: T009 -> IncrementalReindexPipeline.run() core flow in src/reindex_pipeline/pipeline.py
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories).
3. Complete Phase 3: User Story 1 - a single modified file is reprocessed end to end (metadata, graph, summary, embeddings, documentation) with a result identical to a full re-index, far faster, and without ever scanning the whole repository.
4. **STOP and VALIDATE**: Run the `quickstart.md` "Validate a single-file update" scenario (both the timing and content-equivalence checks).

### Incremental Delivery

1. Setup + Foundational → the data model, the two component extensions, and the classification/graph-sync/embedding helpers all exist.
2. Add US1 (single-file update) → test independently → MVP: the pipeline's core batch-aware flow works end to end, matches a full re-index, and never falls back to scanning the whole repository.
3. Add US2 (hash-confirmation skip) → test independently — closes the "avant de déclencher un retraitement coûteux" half of the spec's primary instruction.
4. Add US3 (create/delete symmetry) → test independently — the pipeline's second explicit extension point (deleted-file metadata removal).
5. Add US4 (multi-file batches) → test independently — confirms the batch-wide ordering guarantee (research.md §8) holds under cross-file impact, deliberately last since it's a verification/hardening pass over behavior US1 already built batch-aware.
6. Polish: failure-surfacing guarantees, finalize public exports, and run the full quickstart end to end.
