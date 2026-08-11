# Tasks: Dependency Graph Assembly

## Implementation Strategy

Build the graph module in vertical slices. First establish the graph models and
package scaffold, then implement the in-memory NetworkX-backed assembly and
query layer, then add SQLite persistence, and finish with diagram-friendly
filtered exports and end-to-end validation on a cross-file repository fixture.

## Dependencies

1. Setup must complete before any implementation work.
2. Foundational graph models and repository inventory helpers must exist before
   graph assembly logic.
3. User Story 1 establishes the `DependencyGraph` core, node/edge types, and
   forward/reverse query behavior.
4. User Story 2 adds SQLite persistence and reload behavior on top of the core
   graph.
5. User Story 3 adds filtered exports and diagram-oriented output.

## Parallel Opportunities

- US1: graph models, query helpers, and contract tests can be developed in
  parallel once the package scaffold exists.
- US2: SQLite schema/persistence helpers and reload/query validation can be
  implemented in parallel before wiring them together.
- US3: export schema, diagram slice generation, and integration fixtures can be
  prepared in parallel.

## Phase 1: Setup

- [X] T001 Create the feature package scaffold in `src/dependency_graph/__init__.py`, `src/dependency_graph/graph.py`, `src/dependency_graph/models.py`, `src/dependency_graph/queries.py`, `src/dependency_graph/persistence.py`, `src/dependency_graph/export.py`, `tests/unit/test_dependency_graph.py`, `tests/contract/test_dependency_graph_interface.py`, and `tests/integration/test_dependency_graph.py`.
- [X] T002 Update project dependencies in `pyproject.toml` to add `networkx` and keep the existing pytest-based test configuration aligned with the new graph module.
- [X] T003 Create integration fixture directories for cross-file imports, function calls, inheritance, and duplicate-input cases in `tests/integration/fixtures/dependency-graph/`.

## Phase 2: Foundational

- [X] T004 Define the core graph data models in `src/dependency_graph/models.py` for `DependencyGraph`, `DependencyNode`, `DependencyEdge`, `GraphQuery`, `DiagramExport`, and `GraphPersistenceRecord`.
- [X] T005 Define repository-wide ingestion helpers in `src/dependency_graph/graph.py` for loading symbol inventories, creating nodes, and registering typed edges.
- [X] T006 Define forward and reverse query primitives in `src/dependency_graph/queries.py` for file-level and symbol-level dependency lookup.

## Phase 3: User Story 1 - Assemble and query the dependency graph

Story goal: build a directed dependency graph from repository-wide extraction
results and answer direct dependency questions in both directions.

Independent test criteria: a test repository with cross-file imports and calls
produces the expected nodes and typed edges, and queries return the exact
direct dependencies and dependents for files, modules, classes, and functions.

- [X] T007 [P] [US1] Implement the `DependencyGraph` core in `src/dependency_graph/graph.py` with `id`, `sourceFile`, `nodes`, `edges`, and `addEdge(source, target, type)`.
- [X] T008 [P] [US1] Implement graph assembly from extracted symbol inventories in `src/dependency_graph/graph.py`, including file nodes, symbol nodes, and typed import/call/inheritance edges.
- [X] T009 [P] [US1] Implement bidirectional query helpers in `src/dependency_graph/queries.py` for dependents and dependencies at the file and symbol level.
- [X] T010 [US1] Add contract coverage for the public graph interface in `tests/contract/test_dependency_graph_interface.py`.
- [X] T011 [P] [US1] Add unit tests for node creation, edge typing, deduplication, and `addEdge` behavior in `tests/unit/test_dependency_graph.py`.
- [X] T012 [P] [US1] Add integration fixtures for cross-file imports, function calls, and inheritance in `tests/integration/fixtures/dependency-graph/`.
- [X] T013 [US1] Add end-to-end integration tests for exact direct dependencies and reverse lookups in `tests/integration/test_dependency_graph.py`.

## Phase 4: User Story 2 - Persist and reload the graph in SQLite

Story goal: store the assembled graph locally in SQLite and load it back
without changing direct dependency answers.

Independent test criteria: a persisted graph reloads with the same nodes,
edges, and query results as the original in-memory graph.

- [X] T014 [P] [US2] Implement the SQLite persistence schema and write path in `src/dependency_graph/persistence.py` for graphs, nodes, and typed edges.
- [X] T015 [P] [US2] Implement the SQLite reload path in `src/dependency_graph/persistence.py` so persisted graphs restore nodes, edges, and attribution data.
- [X] T016 [US2] Wire graph persistence into `src/dependency_graph/graph.py` so graphs can be saved and reloaded through the public API.
- [X] T017 [P] [US2] Add unit tests for persistence round-tripping and duplicate-save protection in `tests/unit/test_dependency_graph.py`.
- [X] T018 [US2] Add integration tests that persist a repository graph to SQLite and confirm the reloaded graph returns the same dependency answers in `tests/integration/test_dependency_graph.py`.

## Phase 5: User Story 3 - Export filtered dependency slices

Story goal: export a focused subgraph for a selected file, module, or symbol so
it can drive dependency diagrams.

Independent test criteria: a filtered export contains only the connected slice
for the selected root and omits unrelated nodes and edges.

- [X] T019 [P] [US3] Implement filtered subgraph selection in `src/dependency_graph/export.py` for file, module, and symbol roots.
- [X] T020 [P] [US3] Implement `exportDiagram()` output assembly in `src/dependency_graph/graph.py` so filtered exports return nodes, edges, and selection metadata.
- [X] T021 [US3] Add the diagram export contract and schema coverage in `specs/004-dependency-graph/contracts/diagram-export.schema.json` and `specs/004-dependency-graph/contracts/dependency-graph-interface.md`.
- [X] T022 [P] [US3] Add unit tests for filtered slice selection and empty-result behavior in `tests/unit/test_dependency_graph.py`.
- [X] T023 [P] [US3] Add integration fixtures for filtered export scenarios and missing-root cases in `tests/integration/fixtures/dependency-graph/`.
- [X] T024 [US3] Add end-to-end integration tests that export a diagram-friendly subgraph and confirm unrelated nodes are excluded in `tests/integration/test_dependency_graph.py`.

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T025 Align `specs/004-dependency-graph/data-model.md`, `specs/004-dependency-graph/contracts/sqlite-persistence.md`, and `specs/004-dependency-graph/quickstart.md` with the final node, edge, persistence, and export field names.
- [X] T026 Update `src/dependency_graph/__init__.py` to expose the final public API for `DependencyGraph`, `DependencyNode`, `DependencyEdge`, and query/export helpers.
- [X] T027 Perform a final consistency pass over `src/dependency_graph/graph.py`, `src/dependency_graph/queries.py`, `src/dependency_graph/persistence.py`, and `src/dependency_graph/export.py` to ensure query, persistence, and export behavior are aligned with the spec.
