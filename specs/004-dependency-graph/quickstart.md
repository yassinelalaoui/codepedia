# Quickstart: Dependency Graph Assembly

## Prerequisites

- Python 3.11 or later
- The project dependencies installed in a local virtual environment
- A repository snapshot with symbol extraction results available for multiple
  source files
- A local SQLite file path for persistence tests

## Build the graph

1. Load extracted symbol inventories for a repository containing at least two
   files.
2. Assemble the dependency graph from those inventories.
3. Confirm that file nodes, module nodes, and symbol nodes are present.
4. Confirm that import, call, and inheritance edges are present where expected.

## Validate forward and reverse queries

1. Query a module or file for its direct dependencies.
2. Query the same module or file for reverse dependents.
3. Query a function symbol for the functions it calls directly.
4. Query the same function symbol for the functions that call it.
5. Query a class symbol for its inheritance relations in both directions.

## Validate persistence

1. Persist the assembled graph to a local SQLite file.
2. Reload the graph from SQLite.
3. Re-run the same forward and reverse queries.
4. Confirm that the answers match the original in-memory graph.

## Validate filtered export

1. Export a filtered view for one selected module or symbol.
2. Confirm that the export contains only the connected dependency slice.
3. Confirm that the export is suitable for a diagramming tool or renderer.

## Expected result

The graph returns exact direct dependencies and dependents for files and
symbols, survives a persistence round-trip, and exports a filtered diagram
slice without unrelated nodes.
