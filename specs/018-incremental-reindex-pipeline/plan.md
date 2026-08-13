# Implementation Plan: Incremental Reindexing Pipeline

**Branch**: `018-incremental-reindex-pipeline` | **Date**: 2026-08-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/018-incremental-reindex-pipeline/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add an `IncrementalReindexPipeline` orchestrator that turns one repository-watcher (017)
`ChangeBatch` into targeted updates across the analysis stack, reusing each existing
component in its already-"targeted" (single-file / explicit-list) mode rather than its
full-repository mode: the scanner's (001) exclusion/binary/language primitives applied
per path (research.md §1, since `scan_repository` itself has no targeted mode yet), the
parser (002/003) and metadata store (005) per file, the dependency graph (004) loaded
once and mutated in memory, the code summary pipeline (010) via its existing
`changed_paths` parameter, the vector index (006/007/009) via `reindexFile`/
`removeChunksForFile`, and the doc generator (012) via its existing `changedPaths`/
`changedSymbolIds`/`changedDependencyEdgeIds` parameters. Two small, compatible
extensions close the only real gaps found: `DependencyGraph.remove_source_file` (004)
and `RepositoryMetadataStore.delete_source_file` (005), both needed so a modified or
deleted file never leaves stale nodes/edges/rows behind.

## Technical Context

**Language/Version**: Python 3.11 (matches `pyproject.toml`, consistent with every
sibling feature)

**Primary Dependencies**: No new third-party dependency. Reuses in-repo packages:
`repo_scanner` (001, classification primitives only — research.md §1),
`parser_engine` (002/003), `repository_metadata` (005, plus its new
`delete_source_file` method), `dependency_graph` (004, plus its new
`remove_source_file` method), `repository_metadata.summary_pipeline.CodeSummaryPipeline`
(010), `vector_index`/`embedding_engine` (006/007/009), `doc_generator` (012), and
`repo_watcher`'s `ChangeBatch`/`FileChange`/`ChangeType` (017) as the input shape

**Storage**: N/A for new storage — reuses the existing SQLite-backed metadata store
(005), dependency-graph snapshot (004), vector-index metadata (006/007), and
doc-page manifest (012); this feature's own state is transient (in-memory per batch run)

**Testing**: `pytest`, matching the existing `tests/unit`, `tests/integration`,
`tests/contract` layout

**Target Platform**: Local developer machine, running as part of the same local
process that already hosts the watcher (017) and the rest of the analysis pipeline —
no standalone service

**Project Type**: Single Python library/package added to the existing `src/` layout,
composing existing packages rather than introducing a new architectural layer

**Performance Goals**: A single-file batch's incremental run completes in a time far
shorter than a full repository re-index (SC-001) — dominated by one file's parse +
one file's LLM summary call + one file's embedding call, not by repository size

**Constraints**: MUST NOT call the scanner's full-tree walk (`scan_repository`) or
otherwise touch any file/symbol/embedding/documentation page outside a batch's impact;
MUST leave no stale dependency-graph or metadata entries after a file changes or is
deleted (research.md §4); MUST NOT let local-LLM unavailability block metadata/graph/
embedding updates that don't need it ([[constitution 2.3]], research.md §5)

**Scale/Scope**: One pipeline instance per configured local repository; batches on the
order of a handful of files per run (matching the watcher's, 017, debounced burst
size), against repositories on the order of tens of thousands of files total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
| --- | --- | --- |
| 2.1 Confidentialité absolue | Pipeline only calls already-local components (parser, metadata store, dependency graph, local LLM via `CodeSummaryPipeline`, local embedding engine, doc generator); no new network calls | PASS |
| 2.2 Zero exposition réseau | No server or network listener introduced | PASS |
| 2.3 Jamais de repli silencieux vers le cloud | Summary regeneration still uses `CodeSummaryPipeline`'s existing hard-fail-on-unavailable behavior (010); metadata/graph/embedding updates proceed independently since they don't need the LLM (research.md §5) | PASS |
| 2.4 Traçabilité des réponses IA | Regenerated summaries remain attached to their source symbol via the existing `CodeSummaryPipeline`/metadata-store linkage (010); this feature does not change that attribution | PASS |
| 2.5 Ré-indexation incrémentale | This feature *is* the incremental-reindexing principle made concrete: it exists specifically to avoid ever re-analyzing the full repository on a change | PASS (directly implements this principle) |
| 2.6 Infrastructure minimale et stockage local | No new storage or service; reuses existing local SQLite-backed stores; the two new methods extend existing local components rather than adding new ones | PASS |
| 2.7 Dépôt analysé en lecture seule | Pipeline only reads source files to re-parse/re-hash/re-embed them; all writes go to the existing local stores (metadata, graph, vector index, doc output), never back into the watched repository | PASS |

No violations identified; Complexity Tracking is not needed for this feature.

## Project Structure

### Documentation (this feature)

```text
specs/018-incremental-reindex-pipeline/
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
├── reindex_pipeline/                # New package for this feature
│   ├── __init__.py
│   ├── models.py                     # ReindexBatch, ChangeConfirmation,
│   │                                  # PathClassification, ReindexOutcome
│   ├── classification.py             # Per-path classify + hash-confirm (research §1, §3)
│   ├── graph_sync.py                 # Load/mutate/save the dependency graph for a
│   │                                  # batch (research §4), calling the new
│   │                                  # DependencyGraph.remove_source_file
│   ├── embeddings.py                 # Per-symbol chunk building + VectorIndex calls
│   │                                  # (research §6)
│   └── pipeline.py                   # IncrementalReindexPipeline: orchestrates
│                                      # classification.py, graph_sync.py,
│                                      # embeddings.py, CodeSummaryPipeline (010),
│                                      # and DocGenerator (012) per research §8
│
├── dependency_graph/
│   └── graph.py                      # + remove_source_file (research §4) — small,
│                                      # compatible extension to 004
│
└── repository_metadata/
    ├── sqlite_store.py               # + delete_source_file_records-based public wrapper
    └── store.py                      # + RepositoryMetadataStore.delete_source_file
                                       # (research §2) — small, compatible extension to 005

tests/
├── unit/
│   └── test_reindex_pipeline.py       # Classification, hash-confirmation, and
│                                       # graph/metadata-extension logic in isolation
├── integration/
│   └── test_reindex_pipeline.py       # End-to-end batches against a real (small)
│                                       # indexed sample repository — US1-US4, edge cases
└── contract/
    └── test_reindex_pipeline_interface.py  # Verifies IncrementalReindexPipeline
                                              # matches contracts/incremental-reindex-pipeline.md
```

**Structure Decision**: Single project layout, consistent with every prior feature in
this codebase. `reindex_pipeline` is added as its own top-level package under `src/`,
following the same one-package-per-feature convention already used by `repo_watcher`
(017) and the rest; it depends on `repo_scanner`, `parser_engine`, `repository_metadata`,
`dependency_graph`, `vector_index`, `embedding_engine`, and `doc_generator` rather than
duplicating any of their logic. `dependency_graph` and `repository_metadata` each gain
one small new method (research.md §2, §4) rather than being forked or reimplemented.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — this section is not applicable.
