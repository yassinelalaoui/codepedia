# Tasks: Local Code Summary Pipeline

## Phase 1: Setup

**Goal:** Create the feature scaffolding and shared summary helpers inside the existing repository metadata package.

**Independent test criteria:** The repository exposes the new summary pipeline modules from `src/repository_metadata`, and the new files can be imported without side effects.

- [X] T001 [P] Create `src/repository_metadata/summary_context.py` with the shared summary job, context, result, and impacted-symbol dataclasses defined in the design docs.
- [X] T002 [P] Create `src/repository_metadata/summary_prompts.py` with local prompt-building helpers for module and function summaries.

## Phase 2: Foundational

**Goal:** Add the repository metadata read/write capabilities required by the summary pipeline before any generation logic is wired.

**Independent test criteria:** The metadata store can load the symbols needed for summary generation and persist a generated summary back onto an existing symbol record.

- [X] T003 Extend `src/repository_metadata/sqlite_store.py` with targeted symbol-summary update helpers and any symbol-loading queries needed for incremental summary regeneration.
- [X] T004 Extend `src/repository_metadata/store.py` with high-level methods for loading source-file symbol bundles for summarization and updating `Symbol.generatedSummary` by symbol id.
- [X] T005 Update `src/repository_metadata/__init__.py` to export the new summary pipeline types once the implementation modules exist.

## Phase 3: User Story 1 - Generate summaries for indexed symbols

**Goal:** Generate and persist a natural-language summary for each in-scope module and each public significant function.

**Independent test criteria:** Running the pipeline against a sample indexed repository stores non-empty summaries on the matching module and function symbols.

- [X] T006 [US1] Implement `CodeSummaryPipeline` in `src/repository_metadata/summary_pipeline.py` to iterate modules and public significant functions, invoke the local LLM, and write the generated text to `Symbol.generatedSummary`.
- [X] T007 [US1] Wire the pipeline entry points into `src/repository_metadata/store.py` so callers can summarize a repository, a source file, or a precomputed impacted-symbol set.

## Phase 4: User Story 2 - Use local context and local LLM only

**Goal:** Assemble the right local context for each symbol and fail fast when the local model is unavailable.

**Independent test criteria:** The pipeline refuses to start when the local model is unavailable, and successful prompts include symbol source text, imports, and direct callers when present.

- [X] T008 [US2] Implement context assembly in `src/repository_metadata/summary_context.py` so each summary job includes source text, imports, direct callers from `DependencyGraph`, and the symbol metadata needed by the prompt.
- [X] T009 [US2] Implement prompt construction in `src/repository_metadata/summary_prompts.py` so module and function prompts are built from the local context only and stay deterministic across runs.
- [X] T010 [US2] Enforce local-model readiness checks in `src/repository_metadata/summary_pipeline.py` before any symbol is processed, and raise an explicit local-only error when `LocalLLMEngine.isAvailableLocally()` is false.

## Phase 5: User Story 3 - Regenerate only impacted summaries

**Goal:** Recompute summaries only for symbols touched by a change, not for the whole repository.

**Independent test criteria:** After a file edit, only the impacted symbols get regenerated and unchanged symbols keep their existing summaries.

- [X] T011 [US3] Implement impacted-symbol discovery in `src/repository_metadata/summary_pipeline.py` using file hashes, changed symbol ids, and `DependencyGraph` caller relationships.
- [X] T012 [US3] Add incremental summary persistence flows in `src/repository_metadata/sqlite_store.py` and `src/repository_metadata/store.py` so only impacted symbols are rewritten and unchanged summaries are preserved.
- [X] T013 [US3] Add repository-level orchestration in `src/repository_metadata/summary_pipeline.py` to rerun summaries incrementally after indexing and to skip unaffected modules and functions.

## Phase 6: Polish & Cross-Cutting Concerns

**Goal:** Make the feature easy to consume and verify from the rest of the codebase.

**Independent test criteria:** The package exports are coherent, the quickstart scenarios still match the code, and the feature can be exercised end to end from the existing indexing flow.

- [X] T014 Update `src/repository_metadata/__init__.py`, `src/repository_metadata/summary_pipeline.py`, and `src/repository_metadata/summary_context.py` for clean public exports and stable imports.
- [X] T015 Validate the end-to-end summary flow against the repository indexing path documented in `specs/010-code-summary-pipeline/quickstart.md` and fix any mismatches in `src/repository_metadata/summary_pipeline.py` or `src/repository_metadata/store.py`.

## Dependencies

- `T001` and `T002` can run in parallel.
- `T003`, `T004`, and `T005` depend on the package scaffolding from Phase 1.
- `T006` depends on the foundational store helpers from `T003` and `T004`.
- `T007` depends on `T006`.
- `T008`, `T009`, and `T010` depend on the summary pipeline module existing.
- `T011` depends on the context and readiness behavior from `T008` through `T010`.
- `T012` depends on `T011` and can then be completed without changing the summary prompt layer.
- `T013` depends on `T011` and `T012`.
- `T014` and `T015` are final polish tasks after the main implementation lands.

## Parallel Execution Examples

### User Story 1

```text
Task: T006 -> implement the summary pipeline core in src/repository_metadata/summary_pipeline.py
Task: T007 -> wire store-level entry points in src/repository_metadata/store.py
```

### User Story 2

```text
Task: T008 -> build local summary context assembly in src/repository_metadata/summary_context.py
Task: T009 -> build deterministic prompt composition in src/repository_metadata/summary_prompts.py
Task: T010 -> enforce LocalLLMEngine readiness checks in src/repository_metadata/summary_pipeline.py
```

### User Story 3

```text
Task: T011 -> compute impacted symbols in src/repository_metadata/summary_pipeline.py
Task: T012 -> persist incremental summary updates in src/repository_metadata/sqlite_store.py and src/repository_metadata/store.py
```

## Implementation Strategy

1. Ship the minimal happy path first: generate summaries for modules and public significant functions and persist them on the symbol records.
2. Add the local-only safety gate next so the pipeline never starts when the local model is unavailable.
3. Finish with incremental regeneration so only impacted summaries are recomputed after a change.
4. Keep the public package surface small and stable so the new pipeline can be reused by the existing indexing flow without extra glue code.
