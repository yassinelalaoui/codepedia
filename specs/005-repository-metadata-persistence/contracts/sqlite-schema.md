# SQLite Schema Contract

## Purpose

Document the logical SQLite layout used to persist repository metadata locally.

## Storage model

The persisted representation stores:

- repository metadata
- source-file metadata
- symbol metadata with subtype-specific attributes
- dependency graph nodes and edges
- file content fingerprints

## Required logical tables

### `repositories`

Stores one row per indexed repository.

Required fields:

- `id`
- `root_path`
- `detected_languages`
- `last_indexed_at`

### `source_files`

Stores one row per scanned source file.

Required fields:

- `id`
- `repository_id`
- `path`
- `language`
- `content_hash`
- `last_modified`

### `symbols`

Stores one row per extracted symbol.

Required fields:

- `id`
- `source_file_id`
- `kind`
- `name`
- `line_start`
- `line_end`
- `docstring`
- `generated_summary`
- `metadata`

### `module_symbols`

Stores module-specific symbol fields.

Required fields:

- `symbol_id`
- `file_path`
- `imports`

### `class_symbols`

Stores class-specific symbol fields.

Required fields:

- `symbol_id`
- `parent_class`
- `methods`

### `function_symbols`

Stores function-specific symbol fields.

Required fields:

- `symbol_id`
- `parameters`
- `return_type`
- `nested_symbols`
- `owner`

### `dependency_graphs`

Stores one row per repository dependency-graph snapshot.

Required fields:

- `id`
- `repository_id`
- `last_indexed_at`

### `dependency_edges`

Stores one row per typed directed dependency relation.

Required fields:

- `source_id`
- `target_id`
- `type`
- `source_file_id`
- `metadata`

## Persistence expectations

- Re-saving a single file updates only the rows for that file and its related
  symbols and edges
- File lookups by path or identity must remain efficient
- Module lookups must return all stored symbols for the selected module
- Reloading a repository must preserve direct metadata answers
