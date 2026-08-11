# Quickstart: Local Vector Index

## Prerequisites

- Python 3.11 or later
- Local project dependencies installed in an isolated environment
- A repository with code fragments and generated summaries available
- A writable local path for the persistent vector index files

## Build the initial index

1. Create a local vector index for a repository batch.
2. Add code fragments and generated summaries to the index.
3. Confirm that each stored chunk keeps its source symbol reference.
4. Persist the index and reopen it from the same local SQLite-backed files.

## Validate incremental updates

1. Add a new fragment to the index.
2. Update one existing file and reindex only that file.
3. Delete one file and remove its vectors from the index.
4. Confirm that unrelated chunks remain searchable.

## Validate semantic search

1. Run a semantic search for a code or natural-language query.
2. Request a top-k result set.
3. Confirm that results include fragment content, similarity score, and source
   symbol identity.

## Validate reopen behavior

1. Close the application after indexing.
2. Reopen the local index from disk.
3. Run the same semantic search query again.
4. Confirm that the results match the previously stored state.

## Expected result

The local vector index persists on disk, supports incremental updates and file
deletions, and returns the most relevant fragments for a query with scores and
source-symbol attribution in interactive time.
