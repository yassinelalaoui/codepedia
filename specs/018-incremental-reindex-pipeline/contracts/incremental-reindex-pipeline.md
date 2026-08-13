# Incremental Reindexing Pipeline Contract

## Purpose

Define the public interface of the orchestrator that turns one watcher (017)
`ChangeBatch` into targeted updates to stored metadata, the dependency
graph, generated summaries, embeddings, and documentation — without ever
re-analyzing the whole repository.

## Core type

### `IncrementalReindexPipeline`

Constructor inputs:

- `repositoryRoot` — the local repository path, matching the scanner
  (001), metadata store (005), dependency graph (004), vector index
  (006/007), and doc generator (012) already in use for this repository.
- `metadataStore` — a `RepositoryMetadataStore` (005).
- `dependencyGraph` — the **live, already-loaded** `DependencyGraph` (004)
  instance — the *same object* already referenced by `summaryPipeline` and
  `docGenerator` below. The pipeline mutates this instance in place
  (`remove_source_file` / `ingest_inventory`) rather than loading a
  disconnected copy, so `summaryPipeline`/`docGenerator`'s own graph
  lookups see the update without needing to be told about it separately.
- `dependencyGraphPath` — where to persist `dependencyGraph` after
  mutating it.
- `summaryPipeline` — a `CodeSummaryPipeline` (010), constructed with the
  same `dependencyGraph` instance above.
- `vectorIndex` — a `VectorIndex` (006/007).
- `embeddingEngine` — the `EmbeddingEngine` (009) used to embed each
  reprocessed file's chunks before calling `vectorIndex.reindexFile`.
- `docGenerator` — a `DocGenerator` (012), constructed with the same
  `dependencyGraph` instance above.

Required method:

- `run(batch: ChangeBatch) -> ReindexOutcome` — processes one batch
  end-to-end per `data-model.md`'s state flow and returns a
  `ReindexOutcome`.

Expected behavior:

- Accepts the exact `ChangeBatch` shape the watcher (017) produces, so
  `pipeline.run` can be passed directly as a `RepositoryWatcher`'s
  `on_batch` callback (017's contract).
- Never calls the scanner's full-repository walk (`scan_repository`);
  classifies only the batch's own paths (research.md §1).
- Never reprocesses a `MODIFIED` file whose current content hash matches
  its previously stored hash (research.md §3).
- Never re-parses, re-summarizes, re-embeds, or regenerates documentation
  for any file outside the batch.
- Leaves no stale dependency-graph nodes/edges, stored metadata,
  embeddings, or documentation pages for a file after it is modified or
  deleted (research.md §4).
- Regenerates summaries only for the batch's changed symbols and their
  direct dependents (research.md §5), and continues updating metadata,
  the graph, and embeddings even if summary regeneration fails.

## Batch handoff expectations

- A batch containing only excluded, binary, or unrecognized-language paths
  results in no re-parsing, no summary regeneration, no embedding update,
  and no documentation change — equivalent to the scanner (001) skipping
  those same paths during a full scan.
- A batch containing several files is processed as one pass: cross-file
  impact between files in the same batch (e.g., file A calling into
  changed file B) is reflected in `regeneratedSymbolIds` and in the
  regenerated documentation, not missed because the files were processed
  in sequence in isolation.
- Processing the same set of files as one multi-file batch or as several
  single-file batches (run one after another) produces the same final
  stored metadata, graph, summaries, embeddings, and documentation.

## Consistency expectations

- After `run(batch)` completes, the stored metadata, dependency graph,
  summaries, embeddings, and documentation for the files in `batch` match
  what a full re-indexation of the repository at its current state would
  produce for those same files.

## Failure expectations

- If a file in the batch fails to re-parse, `ReindexOutcome` reports it
  clearly; other files in the batch are still processed, and downstream
  steps unaffected by the failed file (other files' summaries,
  embeddings, and pages) still complete.
- If the local summarization model is unavailable, `ReindexOutcome.summaryFailure`
  is set and no summary is silently skipped or produced by a remote
  fallback; metadata, dependency-graph, and embedding updates for the
  batch still complete (research.md §5).

## Extension: `DependencyGraph.remove_source_file` (004)

- **Input**: `source_file: str`.
- **Effect**: removes every node whose `sourceFile` equals the given
  value, and every edge attached to a removed node.
- **Contract addition**: called by this pipeline before re-ingesting a
  modified file's fresh inventory, and as the sole step for a deleted
  file, so no node or edge from a file's previous content survives past
  the batch that changed or removed it.

## Extension: `RepositoryMetadataStore.delete_source_file` (005)

- **Input**: `repository_root`, `path`.
- **Effect**: removes the file's stored `SourceFile` record and its
  symbols/dependency edges, without inserting a replacement.
- **Contract addition**: called by this pipeline for a deleted file, after
  `DependencyGraph.remove_source_file` has removed the same file's graph
  entries.

## Non-goals of this contract

- It does not define how the pipeline is scheduled or triggered — the
  watcher (017) or any other caller decides when `run` is invoked.
- It does not define the summary, embedding, or documentation content
  themselves — those remain the responsibility of `CodeSummaryPipeline`
  (010), `VectorIndex`/`EmbeddingEngine` (006/007/009), and `DocGenerator`
  (012) respectively.
