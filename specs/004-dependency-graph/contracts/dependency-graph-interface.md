# Dependency Graph Interface Contract

## Purpose

Define the public API for assembling, querying, persisting, and exporting the
repository dependency graph.

## Core types

### `DependencyGraph`

Constructor inputs:

- `id`
- `sourceFile`
- `nodes`
- `edges`

Required methods:

- `addEdge(source, target, type)`
- `exportDiagram()`

Expected behavior:

- Accepts repository-wide extracted symbol inventory as input
- Maintains typed directed edges
- Supports forward and reverse dependency queries
- Suppresses duplicate edges and duplicate node identities

### `DependencyEdge`

Fields:

- `sourceId`
- `targetId`
- `type`

Expected behavior:

- Encodes one typed directed dependency relation
- Preserves the semantic type of the relationship

## Query expectations

- A file-level query can answer which other files depend on a selected module
  or file
- A symbol-level query can answer which functions call a given function and
  which functions are called by that function
- A class query can answer inheritance in both directions

## Persistence expectations

- The graph can be saved to local SQLite storage
- The graph can be loaded back with the same direct dependency answers
- Persistence must not change the analyzed source repository

## Export expectations

- `exportDiagram()` returns a filtered dependency slice
- The export includes nodes and typed edges needed for diagram generation
- The export is deterministic for the same root selection and graph snapshot
