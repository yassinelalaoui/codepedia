# Tasks: Repository Change Watcher

## Phase 1: Setup

**Goal:** Add the `watchdog` dependency and create the `repo_watcher` package skeleton every downstream task depends on.

**Independent test criteria:** `watchdog` is importable after dependency install; `import repo_watcher` succeeds against the empty package.

- [X] T001 Add `watchdog>=4.0` to the `dependencies` list in `pyproject.toml`, per `research.md` §1.
- [X] T002 [P] Create `src/repo_watcher/__init__.py` (empty package marker) per the `Project Structure` in `plan.md`.

## Phase 2: Foundational

**Goal:** Build the shared data model, debounce engine, and startup-reconciliation logic every user story depends on, and stand up the `RepositoryWatcher` skeleton with input validation.

**Independent test criteria:** `RepositoryWatcher(repository_root=<nonexistent path>, on_batch=...)` raises before any monitoring begins; constructing `ChangeType`/`FileChange`/`ChangeBatch` values succeeds and an empty `ChangeBatch` is rejected.

- [X] T003 [P] Create `src/repo_watcher/models.py` with the `ChangeType` enum (`CREATED`/`MODIFIED`/`DELETED`), the `FileChange` dataclass, the `ChangeBatch` dataclass (rejecting an empty `changes` tuple, `origin: "live" | "catchup"`), and the `WatcherConfiguration` dataclass, per `data-model.md`.
- [X] T004 [P] Create `src/repo_watcher/debouncer.py` implementing the per-path stabilization state machine from `data-model.md` "State Transitions" (a pending change per path, timer reset on a further event for that same path, flush of all settled paths into one `ChangeBatch`). Depends on T003.
- [X] T005 [P] Create `src/repo_watcher/reconciliation.py` with a function that walks the repository (reusing `repo_scanner`'s traversal + `IgnoreMatcher`, 001) and diffs the current file set/content hashes against `RepositoryMetadataStore` (`repository_metadata`, 005) to produce a `ChangeBatch` with `origin="catchup"` (or `None` if nothing changed), per `research.md` §3. This diff naturally covers both an empty prior record (first run — everything reported `CREATED`, per `data-model.md`'s "First-run behavior" note) and a file that has become excluded since the last index (correctly reported `DELETED`, since it must leave the index, per `research.md` §3). Depends on T003.
- [X] T006 [P] Create `src/repo_watcher/watcher.py` with the `RepositoryWatcher` class constructor (`repository_root`, `on_batch`, `stabilization_delay`), validating that `repository_root` exists and is a readable directory before returning, per `contracts/repository-watcher-interface.md` "Failure expectations". Depends on T003.
- [X] T007 Implement `RepositoryWatcher`'s watchdog wiring in `src/repo_watcher/watcher.py`: a `FileSystemEventHandler` that converts raw watchdog created/modified/deleted/moved events into `(relative_path, ChangeType)` pairs (a moved event becomes a `DELETED` for the old path plus a `CREATED` for the new path), filters every event through `repo_scanner.ignore.IgnoreMatcher` (001) before it ever reaches the debouncer, and forwards surviving events to the debouncer (T004), per `research.md` §2 and §4. Depends on T004, T006.
- [X] T008 Implement `RepositoryWatcher.start()` / `stop()` / `isRunning()` in `src/repo_watcher/watcher.py`: `start()` runs the reconciliation pass (T005) and invokes `on_batch` with its catch-up batch (if any) before starting the watchdog `Observer` on a background thread and returning without blocking; `stop()` stops the `Observer` cleanly, per `contracts/repository-watcher-interface.md`. Depends on T005, T007.

**Checkpoint**: Foundation ready - user story implementation can now begin.

## Phase 3: User Story 1 - Index stays current without a manual re-scan

**Goal:** Creating, modifying, deleting, or renaming a file is detected and results in a reindexing handoff carrying that file, including for changes that happened while the watcher was not running (or before the repository was ever indexed).

**Independent test criteria:** `quickstart.md` "Validate a single file change (SC-001)" — modifying one file yields exactly one `on_batch` call carrying exactly one `FileChange` for it; "Validate startup catch-up (SC-005)" — offline changes and first-run reconciliation are each captured correctly.

- [X] T009 [P] [US1] Add a contract test in `tests/contract/test_repo_watcher_interface.py` (new file) asserting `RepositoryWatcher` exposes `start()`/`stop()`/`isRunning()` and accepts `repository_root`/`on_batch`/`stabilization_delay`, per `contracts/repository-watcher-interface.md`. Depends on T008.
- [X] T010 [P] [US1] Add an integration test in `tests/integration/test_repo_watcher.py` (new file, temp-repo fixture) covering: creating a file yields one `on_batch` call with `FileChange(CREATED)`; modifying an existing file yields one `on_batch` call with `FileChange(MODIFIED)`; deleting a file yields one `on_batch` call with `FileChange(DELETED)`. Depends on T008.
- [X] T011 [US1] Add an integration test in `tests/integration/test_repo_watcher.py` asserting that renaming a file (a watchdog "moved" event) produces exactly one `on_batch` call whose `ChangeBatch` contains a `DELETED` `FileChange` for the old relative path and a `CREATED` `FileChange` for the new relative path, per the rename edge case and FR "Change detection" in `spec.md`. Depends on T010 (same file, extends its fixture).
- [X] T012 [US1] Add an integration test in `tests/integration/test_repo_watcher.py` covering `RepositoryWatcher.start()`'s reconciliation pass (SC-005): (a) pre-populate `RepositoryMetadataStore` for a sample repository, modify one file and delete another while the watcher is not running, start it, and assert the first `on_batch` call carries `origin="catchup"` with exactly a `MODIFIED` entry for the changed file and a `DELETED` entry for the removed one; (b) start the watcher against a repository with no prior `RepositoryMetadataStore` record at all and assert the catch-up batch reports every non-excluded, non-binary file as `CREATED`, per the first-run edge case in `spec.md`. Depends on T011 (same file).
- [X] T013 [P] [US1] Apply `repo_scanner.binary.is_binary_path` (001) to `CREATED`/`MODIFIED` files at debounce flush time in `src/repo_watcher/debouncer.py`, so a binary file never appears in an outgoing `ChangeBatch`, per `data-model.md` "FileChange" validation rules. Depends on T004.
- [X] T014 [US1] Add a unit test in `tests/unit/test_repo_watcher.py` (new file) asserting `ChangeBatch`/`FileChange` validation rules: a path appears at most once per batch with its net/latest `ChangeType`, and a binary file is excluded at flush time (T013). Depends on T013 — a functional dependency on the flush behavior T013 implements in `src/repo_watcher/debouncer.py`, not a same-file dependency (this test lives in `tests/unit/test_repo_watcher.py`).

**Checkpoint**: US1 is functional and independently testable — single-file changes (including renames), and both offline and first-run startup reconciliation, all reliably produce a correct handoff.

## Phase 4: User Story 2 - Uninterrupted normal repository usage

**Goal:** The watcher runs entirely in the background and never blocks, delays, or locks normal repository file access — including while it is still processing its startup catch-up backlog.

**Independent test criteria:** `quickstart.md` "Validate non-blocking operation (SC-004)" — normal file operations complete immediately while the watcher runs.

- [X] T015 [P] [US2] Add an integration test in `tests/integration/test_repo_watcher.py` that performs writes/reads/deletes on repository files while the watcher is running and asserts they complete without delay or lock errors. Depends on T010.
- [X] T016 [US2] Confirm `RepositoryWatcher.start()` (T008) only blocks for its bounded, read-only reconciliation scan (T005/T012) — matching the contract's ordering guarantee that the catch-up batch is delivered before any live batch — and that this scan never acquires a lock that would block a concurrent edit/build; verified by `test_normal_file_operations_are_not_blocked_while_watching`'s `startup_duration` assertion (T015) and by T017's file-handle audit. Depends on T008, T012, T015.
- [X] T017 [P] [US2] Audit `src/repo_watcher/reconciliation.py` and `src/repo_watcher/debouncer.py` (content hashing, binary sampling) to ensure every file handle is opened, read, and closed per file rather than held open across events. Depends on T005, T013.

**Checkpoint**: US1 and US2 work together — changes are detected and normal repository usage stays unaffected, even during startup catch-up.

## Phase 5: User Story 3 - Burst changes produce one handoff, not many

**Goal:** Rapid saves of one file, and bulk changes touching many files at once, each collapse into a single stabilized handoff.

**Independent test criteria:** `quickstart.md` "Validate burst grouping (SC-002, SC-006)" and "Validate create+delete cancellation".

- [X] T018 [P] [US3] Add an integration test in `tests/integration/test_repo_watcher.py`: saving the same file five times within the stabilization window yields exactly one `on_batch` call for it; changing ten files at once yields exactly one `on_batch` call listing all ten. Depends on T010.
- [X] T019 [P] [US3] Add a unit test in `tests/unit/test_repo_watcher.py` asserting a create immediately followed by a delete of the same path within the stabilization window produces no queued change for that path. Depends on T014.
- [X] T020 [US3] Implement create+delete cancellation for a still-pending path in `src/repo_watcher/debouncer.py`, per `data-model.md` "Special case". Depends on T004.
- [X] T021 [US3] Implement per-path timer-reset semantics in `src/repo_watcher/debouncer.py` (a new event on an already-pending path resets that path's timer instead of emitting early, while unrelated pending paths are unaffected), per `research.md` §4. Depends on T020 (same file).

**Checkpoint**: US1, US2, and US3 work together — bursts of related changes settle into one handoff each.

## Phase 6: User Story 4 - No noise from excluded paths

**Goal:** Changes confined to excluded paths never produce a handoff, and a mixed batch never lists excluded files — including when a path becomes excluded between indexing runs.

**Independent test criteria:** `quickstart.md` "Validate exclusion parity (SC-003)".

- [X] T022 [P] [US4] Add an integration test in `tests/integration/test_repo_watcher.py`: modifying a file inside `node_modules/` produces no `on_batch` call; modifying one excluded file and one relevant file in the same burst produces a batch listing only the relevant file. Depends on T010.
- [X] T023 [P] [US4] Add a unit test in `tests/unit/test_repo_watcher.py` asserting a relevant-looking filename inside an excluded directory is still excluded (`IgnoreMatcher.ignores` evaluated on the full relative path). Depends on T014.
- [X] T024 [US4] Validate against T022 that the T007 per-event filtering correctly handles a burst mixing an excluded and a relevant file: only the relevant file's `FileChange` reaches the outgoing batch, never the excluded one. Adjust `src/repo_watcher/watcher.py` if the mixed-burst case reveals a gap in T007's per-event filtering. Depends on T007, T022.
- [X] T025 [US4] Validate against a dedicated test that reconciliation's diff (`src/repo_watcher/reconciliation.py`) correctly reports a file that has become excluded since the last index (e.g., a `.gitignore` change) as `DELETED` — the file is absent from the current-state side of the diff, so the same general diff that handles genuine deletions reports it as `DELETED`, correctly telling the reindexing pipeline to drop it from the index, per `research.md` §3. Depends on T005, T012.

**Checkpoint**: All four user stories are independently functional together — SC-001 through SC-006 all hold at once.

## Phase 7: Polish & Cross-Cutting Concerns

**Goal:** Handle the remaining failure-mode guarantees from the contract, finalize the package's public exports, and validate the full quickstart end to end.

**Independent test criteria:** Every `quickstart.md` scenario passes against the finished implementation; `repo_watcher`'s public exports match the contract's surface.

- [X] T026 [P] Update `src/repo_watcher/__init__.py` to export `RepositoryWatcher`, `ChangeType`, `FileChange`, `ChangeBatch`, and `WatcherConfiguration` via `__all__`, matching `src/repo_scanner/__init__.py`'s convention. Depends on T008, T003.
- [X] T027 [P] Implement the remaining failure-surfacing guarantees from `contracts/repository-watcher-interface.md` in `src/repo_watcher/watcher.py`: surface a clear error (rather than stopping silently or hanging) if the watched repository becomes inaccessible after `start()`, and catch/report `on_batch` exceptions without crashing the monitoring loop or dropping subsequent batches. Depends on T008.
- [X] T028 Add a unit test in `tests/unit/test_repo_watcher.py` for both failure guarantees in T027 (simulated repository access loss; an `on_batch` callback that raises). Depends on T027.
- [X] T029 Validate the end-to-end flow against `specs/017-repo-change-watcher/quickstart.md` (single change, rename, burst grouping, exclusion parity, create+delete cancellation, startup catch-up including first run, non-blocking operation) and fix any mismatches. Depends on every prior task.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories.
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion; can then proceed in parallel or in priority order (US1 → US2 → US3 → US4).
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### Task-Level Dependencies

- `T001` and `T002` have no dependencies and can run in parallel.
- `T003` depends on `T002` only insofar as the package must exist; it is otherwise independent.
- `T004`, `T005`, and `T006` each depend only on `T003` and touch different files (`debouncer.py`, `reconciliation.py`, `watcher.py`), so all three can run in parallel once `T003` lands.
- `T007` depends on `T004` and `T006` (same file as `T006`, extends its class). `T008` depends on `T005` and `T007` (same file again).
- `T009`, `T010`, and `T013` each depend only on already-completed Foundational tasks (`T008`, `T008`, `T004` respectively) and touch three different files, so all three can run in parallel.
- `T011` depends on `T010` (same file, `tests/integration/test_repo_watcher.py`, extends its fixture) — sequential, not parallel with it. `T012` depends on `T011` for the same reason (same file, sequential chain: `T010` → `T011` → `T012`).
- `T014` depends on `T013` — a **functional** dependency (needs the flush-time binary-exclusion behavior `T013` adds to `src/repo_watcher/debouncer.py` before it can be asserted), not a same-file dependency: `T014` itself lives in `tests/unit/test_repo_watcher.py`.
- `T015`, `T016`, and `T017` each depend on already-completed tasks (`T010`; `T008`/`T012`; `T005`/`T013` respectively) and touch different files, so all three can run in parallel.
- `T018` depends on `T010` (extends the same integration test file, but no other Phase 5 task touches it concurrently). `T019` depends on `T014` (same reasoning for the unit test file). `T020` depends on `T004`. `T021` depends on `T020` (same file, `debouncer.py`, sequential).
- `T022` and `T023` each depend on already-completed tasks (`T010`, `T014` respectively) and touch different files, so both can run in parallel. `T024` depends on `T007` and `T022` (needs the mixed-burst scenario `T022` writes before it can be validated against). `T025` depends on `T005` and `T012` only, so it can run in parallel with `T022`/`T023`/`T024`.
- `T026` depends on `T003`/`T008` (needs every exported symbol to exist). `T027` depends on `T008` and touches `watcher.py` (not concurrently touched elsewhere in this phase), so it can run in parallel with `T026`. `T028` depends on `T027`. `T029` depends on every prior task.

### Parallel Opportunities

- `T001`/`T002` (Setup).
- `T004`/`T005`/`T006` (Foundational, once `T003` lands).
- `T009`/`T010`/`T013` (US1, once Foundational completes — `T011`/`T012` extend `T010`'s file sequentially afterward).
- `T015`/`T016`/`T017` (US2).
- `T018`/`T019` (US3 tests, once their prerequisite files exist).
- `T022`/`T023`/`T025` (US4 — `T024` follows once `T022` lands).
- `T026`/`T027` (Polish).

## Parallel Execution Examples

### Foundational

```text
Task: T004 -> per-path debounce state machine in src/repo_watcher/debouncer.py
Task: T005 -> startup reconciliation in src/repo_watcher/reconciliation.py
Task: T006 -> RepositoryWatcher constructor/validation in src/repo_watcher/watcher.py
```

### After Foundational completes (User Story 1)

```text
Task: T009 -> contract test in tests/contract/test_repo_watcher_interface.py
Task: T010 -> integration test in tests/integration/test_repo_watcher.py
Task: T013 -> binary-file exclusion at flush time in src/repo_watcher/debouncer.py
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories).
3. Complete Phase 3: User Story 1 - a single file change (including a rename, or an offline/first-run catch-up) reliably produces a correct reindexing handoff.
4. **STOP and VALIDATE**: Run the `quickstart.md` "Validate a single file change (SC-001)" and "Validate startup catch-up (SC-005)" scenarios.

### Incremental Delivery

1. Setup + Foundational → the data model, debounce engine, reconciliation logic, and watchdog wiring all exist.
2. Add US1 (change detection, including renames and startup/first-run catch-up) → test independently → MVP: the watcher's core detect-and-handoff loop works.
3. Add US2 (non-blocking operation) → test independently — confirms the background design doesn't regress normal repository usage, even during catch-up.
4. Add US3 (burst grouping) → test independently — the feature's second explicit success criterion (exactly one event per settled burst).
5. Add US4 (exclusion parity) → test independently — closes the "no false positives on excluded files" half of the primary success criterion, including exclusion-rule changes surfacing during catch-up.
6. Polish: failure-surfacing guarantees, finalize public exports, and run the full quickstart end to end.
