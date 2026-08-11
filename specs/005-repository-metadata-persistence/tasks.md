# Tasks: Repository Metadata Persistence

## Implementation Strategy

Build the persistence feature as a thin repository-metadata layer over SQLite.
Start by scaffolding the package and defining the shared data model, then add
content fingerprint helpers and the SQLite storage primitives, then wire the
public store API and finish with validation against reopen, incremental update,
and lookup scenarios.

## Dependencies

1. Setup must complete before any implementation work.
2. Foundational data models and persistence helpers must exist before the store
   API is wired.
3. User Story 1 establishes the repository metadata persistence flow, including
   incremental updates, retrieval, and reopen behavior.
4. Validation tasks for reopen, file/module lookup, and change detection depend
   on the SQLite write/read path being implemented.

## Parallel Opportunities

- Setup: package scaffold, fixture directories, and contract test skeletons can
  be created in parallel once the feature directory exists.
- US1: fingerprint helpers, SQLite schema helpers, and contract/unit tests can
  be developed in parallel before wiring the store API.
- US1: integration fixtures and read-path validation tests can be prepared in
  parallel with the SQLite write path.

## Phase 1: Setup

- [X] T001 Create the repository metadata package scaffold in `src/repository_metadata/__init__.py`, `src/repository_metadata/models.py`, `src/repository_metadata/store.py`, `src/repository_metadata/sqlite_store.py`, and `src/repository_metadata/fingerprints.py`.
- [X] T002 Add the repository metadata test skeletons in `tests/unit/test_repository_metadata.py`, `tests/contract/test_repository_metadata_interface.py`, and `tests/integration/test_repository_metadata.py`.
- [X] T003 Create integration fixture directories for repository reopen, incremental update, lookup, and fingerprint scenarios in `tests/integration/fixtures/repository-metadata/`.

## Phase 2: Foundational

- [X] T004 Define the repository metadata entities in `src/repository_metadata/models.py` for `Repository`, `SourceFile`, `Symbol`, `ModuleSymbol`, `ClassSymbol`, `FunctionSymbol`, `DependencyGraph`, and `DependencyEdge`.
- [X] T005 Define file fingerprint utilities in `src/repository_metadata/fingerprints.py` for stable content-hash calculation and change detection.
- [X] T006 Define the SQLite schema and low-level persistence helpers in `src/repository_metadata/sqlite_store.py` for repositories, source files, symbols, and dependency edges.
- [X] T007 Define the public repository metadata storage interface in `src/repository_metadata/store.py` for incremental writes, file/module reads, and repository reopen operations.

## Phase 3: User Story 1 - Persist and reopen repository metadata locally

Story goal: store repository metadata in a single local file, update changed
files incrementally, and reopen the indexed repository with the same files,
symbols, fingerprints, and dependency relations.

Independent test criteria: a test repository can be indexed, reopened, and
queried for file/module metadata; changing one file updates only that file's
stored records; the stored fingerprint detects whether a file changed.

- [X] T008 [P] [US1] Add contract coverage for the repository metadata storage interface in `tests/contract/test_repository_metadata_interface.py`.
- [X] T009 [P] [US1] Add unit tests for content-hash generation and file change detection in `tests/unit/test_repository_metadata.py`.
- [X] T010 [P] [US1] Add unit tests for repository, source file, symbol, and dependency-edge model behavior in `tests/unit/test_repository_metadata.py`.
- [X] T011 [P] [US1] Add integration fixtures for a repository with multiple files, one changed file, and one unchanged file in `tests/integration/fixtures/repository-metadata/`.
- [X] T012 [US1] Implement repository-level persistence orchestration in `src/repository_metadata/store.py` for create, update, reopen, and lookup flows.
- [X] T013 [US1] Implement the SQLite write/read path in `src/repository_metadata/sqlite_store.py` with incremental upserts for a single file and its related symbols and dependency edges.
- [X] T014 [US1] Implement file fingerprinting and change detection wiring in `src/repository_metadata/fingerprints.py` so unchanged files can be skipped on reopen.
- [X] T015 [US1] Expose the public API from `src/repository_metadata/__init__.py` for repository, file, symbol, edge, and store helpers.
- [X] T016 [US1] Add integration tests for reopen-without-reanalysis, incremental file updates, and exact file/module lookup results in `tests/integration/test_repository_metadata.py`.
- [X] T017 [US1] Add integration tests that confirm dependency relations and fingerprints are preserved across close and reopen in `tests/integration/test_repository_metadata.py`.

## Phase 4: Polish & Cross-Cutting Concerns

- [X] T018 Align `specs/005-repository-metadata-persistence/contracts/repository-metadata-interface.md`, `specs/005-repository-metadata-persistence/contracts/sqlite-schema.md`, `specs/005-repository-metadata-persistence/data-model.md`, and `specs/005-repository-metadata-persistence/quickstart.md` with the final repository, file, symbol, and dependency field names.
- [X] T019 Perform a final consistency pass over `src/repository_metadata/models.py`, `src/repository_metadata/store.py`, `src/repository_metadata/sqlite_store.py`, and `src/repository_metadata/fingerprints.py` to ensure incremental persistence and reload behavior match the spec.
- [X] T020 Verify the full feature against `python -m compileall src tests` and the repository metadata integration scenarios documented in `specs/005-repository-metadata-persistence/quickstart.md`.
