# Feature Specification: Local Vector Index

## Overview

The product maintains a local vector index for code fragments and generated
summaries so semantic search can retrieve the most relevant fragments for a
given query. The index stores fragment embeddings together with their source
symbol metadata and persists all data on disk without relying on any remote
service.

The index must support incremental updates, including adding new vectors,
removing vectors for changed or deleted files, and serving top-k similarity
search results with scores and source-symbol attribution.

## User Scenarios & Testing

### Primary user scenario

A developer indexes a repository, then asks a natural-language or code-centric
question. The system searches the local vector index and returns the most
relevant code fragments and generated summaries, along with their similarity
scores and the symbol each fragment came from.

### Acceptance scenarios

1. A repository index can persist code-fragment vectors and generated-summary
   vectors to a local file and reopen them later.
2. Adding new fragments extends the index without rebuilding all existing
   vectors.
3. Updating or deleting a file removes the vectors that belong to that file.
4. A semantic search returns the `k` closest fragments together with their
   scores and source-symbol references.
5. The search results remain relevant enough for interactive chat-style use on
   a previously indexed repository.
6. Search can target both code fragments and generated summaries when those
   vectors are available.
7. Reopening the application preserves the previously indexed vectors and
   their associated metadata.

### Edge Cases

1. A file with no vectorizable fragments does not add empty entries to the
   index.
2. A query can return fewer than `k` results when the index contains fewer
   matching fragments.
3. A deleted file removes all of its associated vectors from future search
   results.
4. Re-indexing a modified file replaces the old vectors for that file rather
   than duplicating them.
5. A search over an empty index returns no matches instead of failing.

## Requirements

### Functional Requirements

1. The system must persist vector embeddings for code fragments in a local
   on-disk index.
2. The system must persist vector embeddings for generated summaries when those
   summaries are provided.
3. The system must associate every stored vector with the source symbol it came
   from.
4. The system must support incremental addition of new vectors without a full
   rebuild.
5. The system must support removal of all vectors associated with a specific
   file when that file changes or is deleted.
6. The system must allow replacement of the vectors for a modified file while
   leaving unrelated vectors intact.
7. The system must support similarity search over stored vectors using a
   textual or semantic query.
8. The system must return the top `k` most similar fragments for a search
   request.
9. The system must return a similarity score for each search result.
10. The system must return the source symbol associated with each search result.
11. The system must persist the index so it can be reopened later without
    losing stored vectors or metadata.
12. The system must remain fully local and must not require a distant service
    for indexing or search.
13. The system must keep vector metadata synchronized with the file and symbol
    that produced it.
14. The system must handle empty, duplicate, or repeated indexing input without
    creating duplicate live entries.

### Non-Functional Requirements

1. Search must remain suitable for interactive use in a chat workflow.
2. The index must remain usable after reopen without forcing a rebuild of all
   vectors.
3. Incremental updates must preserve the responsiveness of the index on
   previously indexed repositories.
4. Search results must be deterministic for the same index state and query.

## Assumptions

1. Fragment embeddings are produced by an existing local embedding pipeline and
   are supplied to the index together with fragment metadata.
2. Generated summaries are treated as searchable fragments in the same local
   index.
3. The index is used for local retrieval and chat assistance rather than for
   cross-user synchronization.
4. Search requests ask for the most relevant fragments available in the local
   repository snapshot.

## Success Criteria

1. After indexing a batch of code fragments, semantic search returns the
   fragments that are actually closest to the query content.
2. The index can be reopened after the application closes and still returns the
   same search results for the same stored state.
3. Adding or removing a file updates only that file's stored vectors and keeps
   unrelated vectors available.
4. A search request returns the top `k` fragments with their scores and source
   symbol references.
5. Search latency remains compatible with interactive chat-style usage on a
   previously indexed repository.

## Key Entities

### Vector Index

The persisted local collection of stored embeddings and their metadata.

### Vector Entry

A single stored embedding associated with one code fragment or generated
summary.

### Fragment Reference

The source information that ties a vector entry back to the file, symbol, and
fragment it represents.

### Search Query

A semantic request that asks the index for the most relevant stored fragments.

### Search Result

A ranked match that includes the fragment reference and similarity score.
