# Research: Dependency Graph Assembly

## Decision 1: NetworkX-backed graph in Python with local fallback

Decision: Prefer NetworkX as the in-memory graph engine when it is available,
with a small custom directed-graph fallback for environments where the
dependency is not installed yet.

Rationale: The repository is already Python-based, and NetworkX provides a
well-understood directed graph model with straightforward node/edge traversal
and reverse lookup support. A custom fallback keeps the feature usable in local
or constrained test environments without blocking the implementation.

Alternatives considered: A custom graph structure only. Rejected because it
would duplicate traversal and adjacency logic that NetworkX already provides
and would make the implementation harder to validate.

## Decision 2: SQLite persistence

Decision: Persist graph snapshots in SQLite.

Rationale: The feature explicitly requires local persistence, and SQLite keeps
the storage layer simple, portable, and fully offline while satisfying the
project's minimal infrastructure constraints.

Alternatives considered: Flat files only. Rejected because queryable persistence
and reload consistency are easier to guarantee with a relational store. External
databases were rejected because the constitution forbids heavier infrastructure.

## Decision 3: File and symbol node model

Decision: Store file nodes and symbol nodes in the same graph with explicit node
types.

Rationale: The feature needs both repository-level and symbol-level queries.
A typed node model lets the graph answer questions about modules, classes, and
functions without maintaining separate graphs.

Alternatives considered: Separate graphs per entity kind. Rejected because it
would complicate cross-cutting queries and filtered exports.

## Decision 4: Typed edges for dependency semantics

Decision: Represent imports, calls, and inheritance as typed edges.

Rationale: The user needs to ask distinct dependency questions and see precise
relationships. Typed edges preserve semantics while still using one directed
graph.

Alternatives considered: Unlabeled adjacency links. Rejected because they would
lose the distinction between import, call, and inheritance dependencies.

## Decision 5: Diagram-friendly filtered export

Decision: Export filtered subgraphs as node-and-edge collections that are easy
to feed into diagram generation.

Rationale: The feature needs a reusable dependency slice rather than a final
rendering. A simple structured export keeps the graph agnostic to the rendering
tool.

Alternatives considered: Export directly to a rendering format. Rejected because
it would couple graph assembly to a specific diagramming tool.
