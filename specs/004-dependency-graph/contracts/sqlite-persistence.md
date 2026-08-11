# SQLite Persistence Contract

## Purpose

Document the local SQLite layout used to persist dependency graph snapshots.

## Storage model

The persisted representation stores:

- graph metadata
- graph nodes
- typed edges
- optional lookup indexes for reverse dependency queries

## Required logical tables

### `graphs`

Stores one row per persisted graph snapshot.

Required fields:

- `graph_id`
- `repository_root`
- `snapshot_version`
- `created_at`
- `node_count`
- `edge_count`

### `nodes`

Stores one row per graph node.

Required fields:

- `graph_id`
- `node_id`
- `kind`
- `name`
- `source_file`
- `symbol_type`
- `metadata`

### `edges`

Stores one row per typed directed edge.

Required fields:

- `graph_id`
- `source_id`
- `target_id`
- `type`
- `source_file`
- `metadata`

## Persistence expectations

- Re-saving the same graph snapshot must not create duplicate logical nodes or
  edges
- Reloading a persisted graph must preserve the same forward and reverse query
  answers
- The SQLite file must remain local to the user's environment
