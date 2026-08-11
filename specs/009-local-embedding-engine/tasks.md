# Tasks: Local Embedding Engine

## Implementation Strategy

Build the local embedding engine in vertical slices. Start with the package
scaffold and shared error/model types, then add the local transport and engine
surface, then wire the engine into code-fragment and query vectorization paths
inside `vector_index`, and finish by aligning the local-only failure handling
and validation docs with the final behavior.

## Task Order

1. Setup must complete before any implementation work.
2. Foundational models, transport helpers, and error types must exist before the
   engine API is wired.
3. User Story 1 establishes embedding for code fragments during indexing.
4. User Story 2 establishes embedding for search queries during retrieval.
5. User Story 3 ensures local availability checks and explicit failure handling
   are enforced across both indexing and search call sites.

## Parallel Opportunities

- Setup: package scaffold and public export preparation can be started in
  parallel with documentation alignment.
- Foundational: models, errors, and transport helpers can be built in sequence
  with the engine surface once the core shapes are defined.
- User Story 1: chunk construction and index wiring can be updated in parallel
  after the engine surface exists.
- User Story 2: query vectorization and index search routing can be updated in
  parallel once the engine is callable.
- User Story 3: availability enforcement and final validation can be prepared
  in parallel after the shared engine and integration paths are in place.

## Phase 1: Setup

- [X] T001 Create the local embedding package scaffold in `src/embedding_engine/__init__.py`, `src/embedding_engine/engine.py`, `src/embedding_engine/errors.py`, `src/embedding_engine/models.py`, and `src/embedding_engine/transport.py`.

## Phase 2: Foundational

- [X] T002 Define the core embedding data models in `src/embedding_engine/models.py` for `EmbeddingVector`, `EmbeddingRequest`, `EmbeddingResult`, and `EmbeddingAvailabilityStatus`.
- [X] T003 Define explicit local-only error types in `src/embedding_engine/errors.py` for service unavailability, missing model, invalid input, invalid response, and embedding failure.
- [X] T004 [P] Implement the local transport helpers in `src/embedding_engine/transport.py` for local availability checks and embedding requests against the configured runtime endpoint.
- [X] T005 Implement the public `EmbeddingEngine` surface in `src/embedding_engine/engine.py` and export it from `src/embedding_engine/__init__.py` with `embed(text)` and `isAvailableLocally()`.

## Phase 3: User Story 1 - Embed code fragments locally

Story goal: convert code fragments into local vectors so indexing can store
semantic representations of code and generated summaries without any external
service.

Independent test criteria: a code fragment can be turned into a stable vector,
the vector is suitable for similarity comparison, and chunk assembly no longer
depends on the old hash-based fallback.

- [X] T006 [US1] Update `src/vector_index/chunking.py` so `build_code_chunk()` and `build_code_chunks()` can use `EmbeddingEngine` when assembling `CodeChunk` records for code fragments and generated summaries.
- [X] T007 [P] [US1] Update `src/vector_index/index.py` so file reindexing and chunk insertion preserve embedding vectors produced by the shared engine instead of recomputing a local hash embedding.

## Phase 4: User Story 2 - Embed search queries locally

Story goal: convert user search questions into the same local vector space used
for indexed fragments so semantic retrieval can rank relevant code locally.

Independent test criteria: a search query can be vectorized by the shared
engine, the query vector can be compared against indexed chunks, and search
routing no longer depends on the legacy hash-based text encoding path.

- [X] T008 [US2] Keep `src/vector_index/search.py` as the pure ranking helper for cosine similarity, filtering, and top-k result shaping once query vectors are produced elsewhere.
- [X] T009 [P] [US2] Update `src/vector_index/index.py` so `VectorIndex.search()` uses the shared embedding engine for `SearchQuery.queryText` while preserving existing filters and return types.

## Phase 5: User Story 3 - Detect missing local embedding availability

Story goal: fail fast and clearly when the local embedding model is missing,
stopped, or unreachable so both indexing and search guide the user to start or
install the local runtime.

Independent test criteria: availability checks report the local runtime state
before any embedding call, and both indexing and search surface explicit local
errors instead of silently falling back.

- [X] T010 [US3] Implement local availability checks and explicit error mapping in `src/embedding_engine/engine.py` so missing runtime and missing model conditions fail before embedding.
- [X] T011 [P] [US3] Update `src/vector_index/chunking.py` and `src/vector_index/index.py` call paths to surface `EmbeddingEngine` failures directly and remove any remaining fallback to the legacy local hash encoder.

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T012 Align `specs/009-local-embedding-engine/contracts/embedding-engine.md`, `specs/009-local-embedding-engine/data-model.md`, and `specs/009-local-embedding-engine/quickstart.md` with the final engine behavior and error wording.
- [X] T013 Verify the full feature against the local embedding quickstart scenarios in `specs/009-local-embedding-engine/quickstart.md`, including the stopped-runtime failure case, the semantic-similarity sanity check, and an explicit no-outbound-network assertion.

## Dependencies

1. T001 must complete before T002 through T005.
2. T002 and T003 must complete before T004 and T005.
3. T005 must complete before the user story phases.
4. T006 must complete before T007.
5. T008 must complete before T009.
6. T010 must complete before T011.
7. T012 and T013 depend on the implementation tasks finishing.

## Parallel Execution Examples

### User Story 1

- Run T006 and T007 in parallel after T005 is complete.

### User Story 2

- Run T008 and T009 in parallel after T005 is complete.

### User Story 3

- Run T010 and T011 in parallel after the User Story 1 and 2 integration paths
  are in place.

## Implementation Notes

- The MVP is the foundational engine plus one integration path that proves the
  local vectorization surface works end to end.
- The next increment is wiring the same engine into query search so both
  indexing and retrieval share the same local embedding behavior.
- The final increment is hardening availability checks and removing any legacy
  hash-based fallback from the embedding path.

