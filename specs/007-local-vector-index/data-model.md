# Data Model: Local Vector Index

## CodeChunk

Represents one searchable fragment stored in the local vector index.

Fields:
- `id`
- `content`
- `embedding`
- `sourceSymbolId`

Relationships:
- Belongs to one source file
- May represent a code fragment or a generated summary

Validation:
- `id` must be stable for the same chunk identity
- `content` must preserve the fragment text or generated summary text
- `embedding` must represent the searchable vector for the chunk
- `sourceSymbolId` must identify the symbol that produced the chunk

## IndexRecord

Represents the persisted local similarity index metadata.

Fields:
- `id`
- `repositoryRoot`
- `indexPath`
- `metadataPath`
- `createdAt`
- `lastIndexedAt`

Relationships:
- Owns many `CodeChunk` records
- Supports similarity search and file-scoped deletion

Validation:
- `indexPath` and `metadataPath` must point to local on-disk storage
- `repositoryRoot` must identify the indexed repository

## VectorEntry

Represents the stored vector payload for one chunk.

Fields:
- `chunkId`
- `vector`
- `dimensionality`
- `sourceFilePath`
- `sourceSymbolId`
- `chunkType`

Relationships:
- Belongs to one `CodeChunk`
- Is indexed for similarity search

Validation:
- `dimensionality` must match the vector length for the index
- `chunkType` must distinguish code fragments from generated summaries

## SearchQuery

Represents a semantic request against the local index.

Fields:
- `queryText`
- `k`
- `filters`

Relationships:
- Used to retrieve the most relevant chunks for chat-style use

Validation:
- `k` must be positive
- Optional filters must narrow results without altering similarity ranking for
  the allowed set

## SearchResult

Represents one ranked match returned by semantic search.

Fields:
- `chunkId`
- `content`
- `score`
- `sourceSymbolId`
- `sourceFilePath`
- `chunkType`

Relationships:
- Derived from one or more `VectorEntry` matches

Validation:
- Results must be ordered by descending similarity
- Each result must retain source attribution

## ChunkLifecycle

Represents the update state for a file's vectors.

States:
- `added`
- `replaced`
- `removed`
- `unchanged`

Relationships:
- Drives incremental file-scoped maintenance of the vector index

Validation:
- Modified files must replace their prior chunks
- Deleted files must remove all related chunks
