# Feature Specification: Dependency Graph Assembly

## Overview

The product assembles repository-wide symbol extraction results into a directed
dependency graph. The graph provides a navigable view of how files and symbols
depend on one another, using import, function call, and class inheritance
relationships as typed edges.

The module must support lookups in both directions, preserve the ability to
persist the graph for later reuse, and export filtered subgraphs that can be
used to generate dependency diagrams.

## User Scenarios & Testing

### Primary user scenario

A developer or lead technical user runs the graph assembly step after symbol
extraction across a repository. The module builds a dependency graph, answers
questions such as which files import a module or which functions call another
function, and exports a focused view for one file or symbol when needed.

### Acceptance scenarios

1. A repository containing multiple source files with cross-file imports and
   function calls produces a dependency graph with the expected nodes and typed
   edges.
2. Given a module, the graph can return the list of files that depend on that
   module through import relationships.
3. Given a function symbol, the graph can return the functions that call it and
   the functions it calls directly.
4. Given a class symbol, the graph can return its inheritance relationships in
   both directions.
5. A filtered export for a single module or symbol contains only the connected
   dependency slice relevant to that selection.
6. A persisted graph can be loaded again and queried with the same results as
   the original in-memory graph.
7. A repository-level graph built from multiple extracted files preserves file
   attribution on nodes and edges.

### Edge Cases

1. A file with no outgoing dependencies still appears as a node in the graph.
2. A relation that cannot be fully resolved still appears in the graph in a
   usable, typed form when enough source context exists.
3. Duplicate extraction data for the same file does not create duplicate graph
   edges.
4. A filtered export for a missing module or symbol returns an empty result
   rather than corrupting the graph state.

## Requirements

### Functional Requirements

1. The module must assemble a directed dependency graph from all extracted
   symbols and relations available for a repository.
2. The graph must support file nodes and symbol nodes, including classes and
   functions.
3. The graph must support typed edges for imports, function calls, and class
   inheritance.
4. The graph must allow queries from source to target and from target back to
   sources.
5. The graph must answer dependency questions at the file level, such as which
   files import a given module.
6. The graph must answer dependency questions at the symbol level, such as
   which functions call a given function.
7. The graph must preserve attribution to the file or symbol that generated
   each node and edge.
8. The graph must persist to local storage and be loadable for later reuse.
9. The graph must export a filtered subgraph for a selected module, file, or
   symbol.
10. The filtered export must include only the nodes and edges needed for the
    selected dependency slice.
11. The export must be suitable for downstream diagram generation without
    requiring additional graph assembly.
12. The module must avoid duplicating nodes or edges when the same extraction
    input is processed more than once.
13. The module must not modify the analyzed source repository.

### Non-Functional Requirements

1. The graph must remain suitable for fully local execution.
2. The graph must provide stable results for repeated builds from the same
   extraction input.
3. Persistence and reload must preserve query results for the same graph
   content.
4. Filtered exports must be deterministic for the same selection criteria.

## Assumptions

1. Symbol extraction results are already available for the repository before
   graph assembly begins.
2. The graph is built from repository-local extraction output rather than from
   remote services.
3. Persistence is used for local reuse between runs, not for collaborative
   multi-user synchronization.
4. Exported filtered views are intended for visualization tools or diagram
   generation steps.

## Success Criteria

1. On a test repository with cross-file imports and function calls, the graph
   returns the exact direct dependencies for a selected module or symbol.
2. The graph can answer reverse dependency questions, such as which files
   import a module or which functions call a function, without rebuilding the
   graph.
3. A persisted graph reloads with the same direct dependency answers as the
   original graph.
4. A filtered export for a selected module or symbol contains only the relevant
   connected slice and no unrelated nodes.
5. Rebuilding the graph from the same extraction input produces the same
   dependency answers across repeated runs.

## Key Entities

### Dependency Graph

The directed graph that stores nodes and typed edges derived from repository
symbol extraction results.

### Node

A graph vertex representing either a file or a symbol such as a class or
function.

### Edge

A typed relationship between two nodes, such as import, call, or inheritance.

### Query

A lookup request that asks for dependencies or dependents from a selected file
or symbol.

### Filtered Export

A reduced graph view containing only the nodes and edges connected to a
selected module, file, or symbol.

### Persisted Graph

The stored graph representation that can be loaded again for later queries and
exports.
