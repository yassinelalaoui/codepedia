# Implementation Plan: Repository Change Watcher

**Branch**: `017-repo-change-watcher` | **Date**: 2026-08-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/017-repo-change-watcher/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add a background `RepositoryWatcher` that uses `watchdog` to continuously monitor the
already-scanned local repository, reuses the scanner's (001) exclusion rules so watched and
scanned paths never diverge, debounces per-path bursts into a single stabilized `ChangeBatch`
per burst (research §4), reconciles against the existing `repository_metadata` (005) indexed
state on startup for a catch-up batch, and hands every batch to a caller-supplied callback —
leaving the incremental reindexing pipeline itself (e.g., wiring the batch into
`CodeSummaryPipeline.summarizeRepository(..., changed_paths=...)`) to the code that composes
the watcher, per the spec's Non-Goals.

## Technical Context

**Language/Version**: Python 3.11 (matches `pyproject.toml`, consistent with the rest of the
codebase)

**Primary Dependencies**: `watchdog` (new dependency, per user selection over the Node.js
`chokidar` alternative — see [research.md](./research.md) §1); reuses in-repo
`repo_scanner.ignore` and `repo_scanner.binary` (001) for exclusion parity, and
`repository_metadata.store.RepositoryMetadataStore` (005) for startup reconciliation

**Storage**: N/A for new storage — reuses the existing `repository_metadata` SQLite store
(005) as the read-only source of "last indexed" state; the watcher itself is stateless
between process runs

**Testing**: `pytest`, matching the existing `tests/unit`, `tests/integration`,
`tests/contract` layout

**Target Platform**: Local developer machine (Windows/macOS/Linux), running as part of the
same local tool process that already performs scanning/indexing — no standalone service

**Project Type**: Single Python library/package added to the existing `src/` layout (no
frontend or separate backend split needed)

**Performance Goals**: Detect a single file change and produce its reindexing handoff within
roughly the stabilization delay (on the order of 1–2 seconds) of the change settling (SC-001);
remain idle-cost-negligible between changes (event-driven via native OS notification APIs, not
polling)

**Constraints**: Must never block or slow down normal repository file access (SC-004); must
never write into the watched repository itself ([[constitution 2.7]]); must not depend on any
network or cloud service ([[constitution 2.1]])

**Scale/Scope**: One watcher instance per configured local repository; repositories on the
order of tens of thousands of files, consistent with the scanner's (001) existing scale target

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
| --- | --- | --- |
| 2.1 Confidentialité absolue | Watcher only observes local filesystem events and reads local files to hash/classify them; nothing leaves the machine; no new network calls introduced | PASS |
| 2.2 Zero exposition réseau | Watcher introduces no server or network listener of any kind | PASS |
| 2.3 Jamais de repli silencieux vers le cloud | N/A — watcher has no LLM dependency; it only produces a file-change handoff | PASS |
| 2.4 Traçabilité des réponses IA | N/A — watcher produces no AI-generated content | PASS |
| 2.5 Ré-indexation incrémentale | This feature exists specifically to enable incremental (not full-repo) reindexing by identifying only the impacted files per change | PASS (directly implements this principle) |
| 2.6 Infrastructure minimale et stockage local | Adds one lightweight local library (`watchdog`); reuses the existing local SQLite metadata store rather than introducing new storage or a broker | PASS |
| 2.7 Dépôt analysé en lecture seule | Watcher only reads the repository to detect/classify changes; "last indexed" state is read from the existing metadata store, never written into the watched repository | PASS |

No violations identified; Complexity Tracking is not needed for this feature.

## Project Structure

### Documentation (this feature)

```text
specs/017-repo-change-watcher/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
└── repo_watcher/             # New package for this feature
    ├── __init__.py
    ├── models.py              # ChangeType, FileChange, ChangeBatch
    ├── debouncer.py            # Per-path stabilization/burst-grouping (research §4)
    ├── reconciliation.py       # Startup catch-up diff against repository_metadata (005)
    └── watcher.py              # RepositoryWatcher: wraps watchdog Observer, wires
                                 # exclusion (repo_scanner, 001), debouncer, and
                                 # reconciliation together; exposes start()/stop()/
                                 # isRunning() and the on_batch handoff (contracts/)

tests/
├── unit/
│   └── test_repo_watcher.py        # Debounce/state-machine logic in isolation
├── integration/
│   └── test_repo_watcher.py        # Real filesystem events on a temp repo fixture,
│                                    # exclusion parity, catch-up reconciliation
└── contract/
    └── test_repo_watcher_interface.py  # Verifies RepositoryWatcher matches
                                         # contracts/repository-watcher-interface.md
```

**Structure Decision**: Single project layout (this codebase has no
frontend/backend split for its Python packages — `frontend/` in the repo root is
unrelated tooling for the existing wiki UI, feature 016). `repo_watcher` is added
as its own top-level package under `src/`, following the same one-package-per-
feature convention already used by `repo_scanner` (001), `repository_metadata`
(005), and the other existing features, and depends on `repo_scanner` (for
exclusion parity) and `repository_metadata` (for startup reconciliation) rather
than duplicating their logic.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — this section is not applicable.
