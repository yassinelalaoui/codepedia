# Phase 1 Data Model: Incremental Reindexing Pipeline

This feature introduces one small orchestration package plus two compatible
extensions to existing components (research.md §2, §4). It deliberately
reuses existing types rather than redefining them where a match already
exists.

## Reused types (not redefined here)

| Type | Source | Role in this feature |
|---|---|---|
| `ChangeBatch`, `FileChange`, `ChangeType` | `repo_watcher` (017) | The pipeline's input shape — a `ReindexBatch` (below) is built directly from one `ChangeBatch`. |
| `FileSymbolInventory` | `parser_engine` (002/003) | Result of re-parsing one file. |
| `RepositoryMetadataStore` | `repository_metadata` (005) | Per-file metadata persistence and content-hash comparison. |
| `DependencyGraph` | `dependency_graph` (004) | Loaded once per batch, mutated, saved once per batch. |
| `ImpactedSymbolSet` | `repository_metadata.summary_context` (010) | Produced internally by `CodeSummaryPipeline.summarizeRepository`; this feature does not recompute it. |
| `CodeChunk`, `VectorEntry` | `vector_index` (006/007) | Per-symbol embedding chunks. |
| `DocumentationSet`, `RegenerationImpactSet`, `EdgeId` | `doc_generator` (012) | Produced by `generateRepositoryDocumentation`; this feature does not recompute page impact itself. `RegenerationImpactSet` **is** spec.md's `ImpactedDocumentationSet` Key Entity — the same concept, not a separate type. `EdgeId` is the shape `graph_sync.py` (below) returns its changed-edge set as. |

## ReindexBatch

The pipeline's normalized view of one incoming `ChangeBatch` (017), grouped
by what each file needs.

| Field | Type | Notes |
|---|---|---|
| `repositoryRoot` | `Path` | The repository this batch applies to. |
| `changes` | `tuple[FileChange, ...]` | Taken directly from the source `ChangeBatch.changes` (017) — not copied into a new shape. |

Derived groupings (computed by the pipeline, not stored):

- **toReprocess**: files with `CREATED` or `MODIFIED` whose `ChangeConfirmation.changed` is `True`.
- **toSkip**: files with `MODIFIED` whose `ChangeConfirmation.changed` is `False` (§3, research.md).
- **toRemove**: files with `DELETED`.

## ChangeConfirmation

The result of comparing one file's current content hash against its
previously stored hash (research.md §3).

| Field | Type | Notes |
|---|---|---|
| `relativePath` | `str` | The file this confirmation is about. |
| `currentHash` | `str` | Computed via `repository_metadata.fingerprints.compute_content_hash`. |
| `changed` | `bool` | `True` when no prior hash exists or it differs from `currentHash`. |

Validation rule: a `DELETED` file never has a `ChangeConfirmation` — deletion
does not require a hash comparison, only removal (research.md §3).

## PathClassification

The outcome of classifying one batch path without a full repository scan
(research.md §1), reusing the scanner's (001) own exclusion/binary/language
primitives.

| Field | Type | Notes |
|---|---|---|
| `relativePath` | `str` | |
| `excluded` | `bool` | Re-confirmed via `IgnoreMatcher.ignores` (defensive; the watcher, 017, should already have filtered this). |
| `isBinary` | `bool` | Via `is_binary_path`; not evaluated for a `DELETED` path. |
| `language` | `str \| None` | Via `LanguageDetector.detect`; `None` means the file is skipped from parsing/symbols/summaries/embeddings, exactly as a full scan would skip it. |

Validation rule: a path with `excluded = True` or (`isBinary = True` or
`language is None`, for a `CREATED`/`MODIFIED` path) is dropped from
`toReprocess` before any parsing happens — this is what keeps the
incremental result identical to a full re-index for that path (spec's
consistency requirement).

## ReindexOutcome

The pipeline's report of what one `ReindexBatch` actually did, returned to
the caller (and used by `quickstart.md`'s validation scenarios).

| Field | Type | Notes |
|---|---|---|
| `reprocessedPaths` | `tuple[str, ...]` | Files that were re-parsed and had their metadata/graph/embeddings updated. |
| `skippedPaths` | `tuple[str, ...]` | `MODIFIED` files whose hash confirmation found no real change (§3). |
| `removedPaths` | `tuple[str, ...]` | `DELETED` files whose metadata/graph/embeddings/pages were removed. |
| `regeneratedSymbolIds` | `tuple[str, ...]` | From `CodeSummaryPipeline`'s result (010) — the changed symbols plus their direct dependents. |
| `documentation` | `DocumentationSet` | The `doc_generator` (012) result for this run — which pages were (re)written. |
| `summaryFailure` | `str \| None` | Set when summary regeneration failed (e.g., local LLM unavailable); metadata/graph/embedding updates still completed (research.md §5). |
| `failedPaths` | `tuple[str, ...]` | Files that failed to re-parse (e.g., invalid syntax); excluded from `reprocessedPaths`, reported clearly rather than silently dropped, per `contracts/incremental-reindex-pipeline.md` "Failure expectations." |

## Implementation note: shared `DependencyGraph` instance

`graph_sync.py`'s sync function takes the **live `DependencyGraph` instance** already
held by the caller's `CodeSummaryPipeline`/`DocGenerator` (constructor-injected into
`IncrementalReindexPipeline` — see `contracts/incremental-reindex-pipeline.md`) and
mutates it in place (`remove_source_file` + `ingest_inventory`), then saves it to
`dependencyGraphPath`. It does not call `DependencyGraph.load(...)` itself — the
caller is responsible for having loaded the graph once and constructing
`summaryPipeline`/`docGenerator` with that same instance, so their internal
`dependents()`/diagram lookups see the update without a separate synchronization step.

## New extension: `DependencyGraph.remove_source_file`

Added to `dependency_graph` (004; research.md §4) — not a new type, a new
method on the existing `DependencyGraph` class.

- **Input**: `source_file: str` (matches `DependencyNode.sourceFile`).
- **Effect**: removes every node whose `sourceFile == source_file`, and
  every edge whose source or target was one of those removed nodes.
- **Used for**: clearing a file's previous nodes/edges before
  `ingest_inventory` re-adds its current version (`MODIFIED`), or as the
  only step for a `DELETED` file.

## New extension: `RepositoryMetadataStore.delete_source_file`

Added to `repository_metadata` (005; research.md §2) — not a new type, a
new method on the existing `RepositoryMetadataStore` class.

- **Input**: `repository_root`, `path`.
- **Effect**: removes the file's `SourceFile` row and its symbols/edges
  (reusing the existing private deletion logic already used internally by
  `store_inventory`'s replace-on-write path), without inserting a
  replacement.
- **Used for**: `DELETED` files only.

## State flow (per batch)

```
ChangeBatch (017)
      │
      ▼
classify + hash-confirm each path (research.md §1, §3)
      │
      ├── excluded / binary / undetected language ──▶ dropped (not reprocessed)
      ├── MODIFIED, hash unchanged ──▶ skippedPaths
      │
      ▼
toReprocess (CREATED + confirmed-changed MODIFIED)     toRemove (DELETED)
      │                                                       │
      ▼                                                       ▼
re-parse, store_inventory, graph.remove_source_file +   graph.remove_source_file
graph.ingest_inventory (research.md §2, §4)             + metadataStore.delete_source_file
      │                                                       │
      └───────────────────────┬───────────────────────────────┘
                               ▼
                     graph.save() (research.md §4)
        [graph_sync also returns the EdgeId set added/removed by this
         update — carried forward to the DocGenerator call below]
                               │
                               ▼
        CodeSummaryPipeline.summarizeRepository(changed_paths=toReprocess)
                       (research.md §5)
                               │
                               ▼
   VectorIndex.reindexFile(...) for toReprocess, .removeChunksForFile(...) for toRemove
                       (research.md §6)
                               │
                               ▼
   DocGenerator.generateRepositoryDocumentation(changedPaths=..., changedSymbolIds=..., changedDependencyEdgeIds=...)
                       (research.md §7)
                               │
                               ▼
                        ReindexOutcome
```
