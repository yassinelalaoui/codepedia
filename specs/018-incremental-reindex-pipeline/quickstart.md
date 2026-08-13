# Quickstart: Incremental Reindexing Pipeline

## Prerequisites

- Python 3.11 or later, local project dependencies installed
- A local LLM running and available (for the summary-regeneration
  scenarios; the non-summary scenarios below do not need it)
- A sample repository already fully indexed once: scanned (001), parsed
  (002/003), stored (005), with a saved dependency graph (004), generated
  summaries (010), a populated vector index (006/007/009), and generated
  documentation (012) — i.e., the state a first full index run produces
- An `IncrementalReindexPipeline` constructed against that repository's
  existing metadata store, dependency graph path, summary pipeline,
  vector index, and doc generator (`contracts/incremental-reindex-pipeline.md`)

## Validate a single-file update (US1, primary success criterion)

1. Record the current documentation output for one module page.
2. Modify one source file's content (a real code change, e.g. add a
   statement to a function).
3. Time a full re-index of the sample repository from scratch; record the
   duration and the resulting documentation/summaries/embeddings.
4. Reset the repository's stored state to before step 2, then run
   `pipeline.run(batch)` with a `ChangeBatch` containing just that one
   `MODIFIED` file; time it.
5. Confirm the incremental run's duration is far shorter than the full
   re-index's duration (SC-001).
6. Confirm the incremental run's resulting stored metadata, dependency
   graph, summaries, embeddings, and documentation for the changed file
   (and its direct dependents) match the full re-index's result for the
   same files (SC-002).
7. Confirm `ReindexOutcome.reprocessedPaths` contains only the changed
   file, and no other file's stored symbols, summary, embedding, or
   documentation page changed.

## Validate the hash-confirmation skip (US2)

1. Touch a file (e.g., rewrite it with byte-for-byte identical content,
   or update its modified-time without changing bytes) so the watcher
   reports it as `MODIFIED`.
2. Run `pipeline.run(batch)` with that file in the batch.
3. Confirm `ReindexOutcome.skippedPaths` contains the file and
   `reprocessedPaths` does not.
4. Confirm no re-parsing, summary regeneration, embedding update, or
   documentation regeneration occurred for that file (e.g., via a spy on
   the summary pipeline / vector index / doc generator, or by asserting
   their stored outputs are byte-identical to before the run).

## Validate create/delete symmetry (US3)

1. Add a new source file to the sample repository and run `pipeline.run`
   with a batch containing it as `CREATED`.
2. Confirm the new file's symbols, summary, embeddings, and a new
   documentation page all exist afterward.
3. Delete a different, already-indexed file and run `pipeline.run` with a
   batch containing it as `DELETED`.
4. Confirm the deleted file's symbols and edges are gone from the
   dependency graph, its stored metadata and embeddings are gone, and its
   documentation page is removed.
5. Confirm any documentation page that referenced the deleted file's page
   (e.g., a home page listing modules) was regenerated to no longer
   reference it.

## Validate multi-file batch handling (US4)

1. Modify two files in the same batch, where a function in file A calls a
   function in file B and both changed.
2. Run `pipeline.run` with both files in one `ChangeBatch`.
3. Confirm `ReindexOutcome.regeneratedSymbolIds` includes both changed
   symbols and any symbol identified as directly depending on either one,
   regenerated exactly once each (not duplicated).
4. Separately, run the same two changes as two sequential single-file
   batches on a fresh copy of the pre-change state.
5. Confirm the final stored metadata, graph, summaries, embeddings, and
   documentation are the same whether processed as one batch or as two
   sequential batches.

## Validate resilience to local-LLM unavailability (edge case)

1. Stop the local LLM service.
2. Modify one file and run `pipeline.run` with it in the batch.
3. Confirm `ReindexOutcome.summaryFailure` is set and no summary was
   silently produced by a remote fallback.
4. Confirm the file's stored metadata, dependency-graph entries, and
   embeddings were still updated despite the summary failure.

## Expected result

A batch of changed files, run through the pipeline, updates only the
metadata, dependency graph, summaries, embeddings, and documentation
those files actually affect — skipping files whose reported "modified"
signal doesn't correspond to a real content change — and produces a final
state identical to what a full re-index of the repository would produce
for the same files, in a fraction of the time.
