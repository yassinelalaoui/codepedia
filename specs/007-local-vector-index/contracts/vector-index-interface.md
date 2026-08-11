# Vector Index Interface Contract

## Purpose

Define the public search and maintenance operations for the local vector index.

## Core types

### `CodeChunk`

Fields:

- `id`
- `content`
- `embedding`
- `sourceSymbolId`

Expected behavior:

- Represents one searchable unit in the local index
- Can describe a code fragment or a generated summary fragment
- Preserves traceability to the source symbol that produced it

### `VectorIndex`

Constructor inputs:

- `repositoryRoot`
- `indexPath`
- `metadataPath`
- existing chunks or persisted state

Required methods:

- `addChunk(chunk)`
- `addChunks(chunks)`
- `removeChunksForFile(path)`
- `reindexFile(path, chunks)`
- `search(queryText, k)`
- `save()`
- `load()`

Expected behavior:

- Stores vectors locally on disk
- Supports incremental add/remove operations
- Reopens with the same retrievable state
- `indexPath` and `metadataPath` may point to the same local SQLite-backed store

### `SearchResult`

Fields:

- `chunkId`
- `content`
- `score`
- `sourceSymbolId`
- `sourceFilePath`
- `chunkType`

Expected behavior:

- Returns ranked semantic matches
- Includes similarity score and source attribution

## Search expectations

- A search request returns the top `k` fragments by semantic similarity
- Results are deterministic for the same index state and query
- Empty indexes return no matches
- Search results are deterministic for the same stored state and query

## Maintenance expectations

- Adding new chunks does not require a full rebuild
- Updating a file replaces the prior chunks for that file
- Deleting a file removes all of its stored chunks
