# Data Model: Dependency Graph Assembly

## DependencyGraph

Represents the assembled directed dependency graph for one repository snapshot.

Fields:
- `id`
- `sourceFile`
- `nodes`
- `edges`

Methods:
- `addEdge(source, target, type)`
- `exportDiagram()`

Relationships:
- Consumes repository-wide symbol extraction results
- Owns graph nodes and edges
- Supports bidirectional traversal and filtered exports

Validation:
- `id` must be stable for the same repository snapshot
- `nodes` must not contain duplicates for the same entity identity
- `edges` must not contain duplicate typed relationships between the same
  source and target
- `sourceFile` must preserve repository attribution for loaded inputs

## DependencyNode

Represents one vertex in the graph.

Fields:
- `id`
- `kind` (`file` or `symbol`)
- `name`
- `sourceFile`
- `symbolType` (when `kind` is `symbol`)
- `metadata`

Relationships:
- Can represent a file or a symbol such as a class or function

Validation:
- `kind` must be one of the supported node kinds
- `sourceFile` must identify the extraction source for the node

## DependencyEdge

Represents one directed dependency relation between two nodes.

Fields:
- `sourceId`
- `targetId`
- `type`
- `sourceFile`
- `metadata`

Relationships:
- Connects file and symbol nodes through typed dependencies

Validation:
- `type` must be one of `import`, `call`, or `inheritance`
- `sourceId` and `targetId` must refer to existing nodes
- Duplicate edges with the same source, target, and type must be suppressed

## GraphQuery

Represents a lookup against the graph.

Fields:
- `focusId`
- `direction`
- `relationType`
- `depth`

Relationships:
- Used for forward and reverse dependency retrieval

Validation:
- Queries must return deterministic results for the same graph state

## DiagramExport

Represents a filtered subgraph ready for downstream diagram generation.

Fields:
- `rootId`
- `nodes`
- `edges`
- `selectionType`
- `generatedAt`

Relationships:
- Derived from a selected module, file, or symbol

Validation:
- Exported nodes and edges must be limited to the selected dependency slice

## GraphPersistenceRecord

Represents the persisted SQLite view of the graph snapshot.

Fields:
- `graphId`
- `repositoryRoot`
- `nodeCount`
- `edgeCount`
- `createdAt`
- `snapshotVersion`

Relationships:
- Used to reload graphs for later queries and exports

Validation:
- Reloaded graph content must preserve direct dependency answers
