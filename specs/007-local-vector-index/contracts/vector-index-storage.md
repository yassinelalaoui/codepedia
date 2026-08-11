# Vector Index Storage Contract

## Purpose

Document the local file-based storage layout used by the vector index.

## Storage model

The persisted representation stores:

- repository-level index metadata
- code chunks and generated-summary chunks
- chunk embeddings
- source file attribution
- source symbol attribution
- file-scoped lifecycle status
- the latest index metadata and last-indexed timestamp

## Required logical storage records

### `indexes`

Stores one row per local vector index.

Required fields:

- `id`
- `repository_root`
- `index_path`
- `metadata_path`
- `created_at`
- `last_indexed_at`

### `chunks`

Stores one row per searchable chunk.

Required fields:

- `id`
- `index_id`
- `source_file_path`
- `source_symbol_id`
- `chunk_type`
- `content`
- `embedding`
- `dimensionality`

The table stores the current active chunk rows for the index.

### `chunk_lifecycle`

Stores the lifecycle state of a chunk or chunk group.

Required fields:

- `chunk_id`
- `source_file_path`
- `lifecycle_state`
- `updated_at`

## Persistence expectations

- Adding a chunk appends it to local storage without rebuilding unrelated data
- Removing a file deletes all chunks linked to that file
- Reindexing a file replaces only that file's chunk records
- Reopening the index restores the same search results for the same stored
  state
