# Tasks: Local Vector Index

## Implementation Strategy

Build the local vector index in vertical slices. Start with the package
scaffold and the core data model, then add local storage and search helpers,
then implement the `VectorIndex` API for incremental add/remove/reopen/search
flows, and finish with integration validation against interactive top-k
semantic search scenarios.

## Dependencies

1. Setup must complete before any implementation work.
2. Foundational models, storage helpers, and search helpers must exist before
   the index API is wired.
3. User Story 1 establishes the searchable `CodeChunk` lifecycle, local
   persistence, and semantic search behavior.
4. Validation tasks for reopen, incremental updates, and deletion depend on the
   storage and search paths being implemented.

## Parallel Opportunities

- Setup: package scaffold, dependency update, and fixture directories can be
  prepared in parallel.
- Foundational: chunk models, storage schema, and search helpers can be built in
  parallel after the package scaffold exists.
- US1: contract tests, unit tests, and integration fixtures can be prepared in
  parallel before wiring the public index API.

## Phase 1: Setup

- [X] T001 Create the vector index package scaffold in `src/vector_index/__init__.py`, `src/vector_index/models.py`, `src/vector_index/index.py`, `src/vector_index/storage.py`, `src/vector_index/search.py`, and `src/vector_index/chunking.py`.
- [X] T002 Update project dependencies in `pyproject.toml` to add the local vector search dependency and keep the test configuration aligned with the new vector index package.
- [X] T003 Create integration fixture directories for vector indexing, file replacement, file deletion, and empty-index scenarios in `tests/integration/fixtures/vector-index/`.

## Phase 2: Foundational

- [X] T004 Define the core vector index data models in `src/vector_index/models.py` for `CodeChunk`, `VectorIndex`, `VectorEntry`, `SearchQuery`, `SearchResult`, and `ChunkLifecycle`.
- [X] T005 [P] Define chunk-building helpers in `src/vector_index/chunking.py` for turning code fragments and generated summaries into `CodeChunk` records.
- [X] T006 [P] Define the local storage layout and persistence helpers in `src/vector_index/storage.py` for indexes, chunks, and file-scoped lifecycle records.
- [X] T007 [P] Define similarity search helpers in `src/vector_index/search.py` for ranking, filtering, and top-k result shaping.

## Phase 3: User Story 1 - Persist and search code fragments locally

Story goal: store code-fragment and summary embeddings in a local on-disk
index, update changed files incrementally, and return the most relevant
fragments with scores and source-symbol attribution.

Independent test criteria: a test repository can be indexed, reopened, and
queried for top-k semantic matches; adding a new fragment extends the index;
replacing or deleting a file removes the old vectors; empty-index searches
return no matches.

- [X] T008 [P] [US1] Add contract coverage for the vector index public API in `tests/contract/test_vector_index_interface.py`.
- [X] T009 [P] [US1] Add unit tests for `CodeChunk`, search result ranking, and lifecycle behavior in `tests/unit/test_vector_index.py`.
- [X] T010 [P] [US1] Add integration fixtures for indexed batches, modified files, deleted files, and empty-index scenarios in `tests/integration/fixtures/vector-index/`.
- [X] T011 [US1] Implement the public `VectorIndex` API in `src/vector_index/index.py` with add, bulk add, remove-by-file, replace-by-file, search, save, and load operations.
- [X] T012 [US1] Implement local persistence in `src/vector_index/storage.py` so chunks, source symbols, and index metadata are stored on disk and reopened later.
- [X] T013 [US1] Implement semantic search ranking in `src/vector_index/search.py` so queries return the top `k` fragments with scores and source attribution.
- [X] T014 [US1] Implement chunk assembly in `src/vector_index/chunking.py` so code fragments and generated summaries become stable `CodeChunk` records.
- [X] T015 [US1] Expose the final public API from `src/vector_index/__init__.py` for `CodeChunk`, `VectorIndex`, `VectorEntry`, `SearchQuery`, `SearchResult`, and chunk/search helpers.
- [X] T016 [US1] Add integration tests for incremental addition, file replacement, file deletion, reopen behavior, and exact top-k search results in `tests/integration/test_vector_index.py`.
- [X] T017 [US1] Add integration tests for empty-index searches and chat-style search latency expectations in `tests/integration/test_vector_index.py`.

## Phase 4: Polish & Cross-Cutting Concerns

- [X] T018 Align `specs/007-local-vector-index/contracts/vector-index-interface.md`, `specs/007-local-vector-index/contracts/vector-index-storage.md`, `specs/007-local-vector-index/data-model.md`, and `specs/007-local-vector-index/quickstart.md` with the final chunk, index, and search field names.
- [X] T019 Perform a final consistency pass over `src/vector_index/models.py`, `src/vector_index/index.py`, `src/vector_index/storage.py`, `src/vector_index/search.py`, and `src/vector_index/chunking.py` to ensure incremental persistence and deterministic search behavior match the spec.
- [X] T020 Verify the full feature against `python -m compileall src tests` and the vector index quickstart scenarios documented in `specs/007-local-vector-index/quickstart.md`.
