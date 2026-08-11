# Implementation Plan: Dependency Graph Assembly

Branch: `004-dependency-graph` | Date: 2026-08-11 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/004-dependency-graph/spec.md`

## Summary

Build a repository-wide dependency graph assembly module that converts extracted
file and symbol relations into a directed graph. The graph is centered on a
Python `DependencyGraph` wrapper backed by NetworkX for in-memory traversal and
querying, with SQLite persistence for reuse across runs.

The module must support both forward and reverse lookups for file-level and
symbol-level dependencies, eliminate duplicate nodes and edges, and export
filtered subgraphs suitable for diagram generation.

## Technical Context

Language/Version: Python 3.11+
Primary Dependencies: NetworkX, sqlite3, pytest, dataclasses, and the existing
symbol extraction output types
Storage: SQLite file for persisted graph snapshots; in-memory graph during
assembly and querying
Testing: pytest with unit, contract, and integration coverage
Target Platform: Local CLI/library on Windows, macOS, and Linux
Project Type: Internal analysis pipeline stage built on top of repository-wide
symbol extraction
Performance Goals: Build and query dependency graphs deterministically for
medium and large repositories, preserve direct dependency answers across
persistence round-trips, and avoid duplicate edges
Constraints: Fully local execution, no cloud fallback, no writes into analyzed
source repositories, preserve file and symbol attribution
Scale/Scope: Repository-level graph assembly across multiple extracted files with
cross-file imports, calls, and inheritance

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentiality absolute: pass
- Zero exposure network by default: pass
- Never repli silently vers le cloud: pass
- Traçabilité des réponses IA: pass; feature output is graph structure, not AI
  generated prose
- Ré-indexation incrémentale: pass in scope; graph assembly can be driven by
  changed extraction inputs and persisted for reuse
- Infrastructure minimale et stockage local: pass; SQLite satisfies the local
  persistence requirement
- Depot analyse en lecture seule: pass

## Project Structure

### Documentation for this feature

`specs/004-dependency-graph/`
├── `plan.md`
├── `research.md`
├── `data-model.md`
├── `quickstart.md`
└── `contracts/`
    ├── `dependency-graph-interface.md`
    ├── `diagram-export.schema.json`
    └── `sqlite-persistence.md`

### Source Code

`src/`
├── `dependency_graph/`
│   ├── `__init__.py`
│   ├── `graph.py`
│   ├── `models.py`
│   ├── `persistence.py`
│   ├── `queries.py`
│   └── `export.py`
└── `parser_engine/`

Structure Decision: Keep the graph assembly module separate from extraction so
`DependencyGraph` can consume repository-wide extraction outputs, build a stable
NetworkX-backed graph, and persist snapshots in SQLite without coupling the
graph logic to AST parsing.

## Phase 0: Research

### Decision 1

Use NetworkX as the in-memory directed graph engine for the Python
implementation.

### Decision 2

Use SQLite as the local persistence layer for graph metadata, nodes, and typed
edges.

### Decision 3

Model graph nodes explicitly as file nodes and symbol nodes so repository and
symbol-level queries can share the same graph.

### Decision 4

Represent the filtered diagram export as a graph slice with node and edge
records rather than as a rendering-specific format.

### Decision 5

Deduplicate graph content during assembly so repeated ingestion of the same
extraction data does not produce duplicate nodes or edges.

## Phase 1: Design

### Data model

Define graph nodes, typed edges, query shapes, persisted snapshots, and filtered
exports.

### Contracts

Document the public `DependencyGraph` API, the diagram-export schema, and the
SQLite persistence layout.

### Quickstart

Provide validation steps that prove cross-file imports, function calls,
inheritance links, persistence reloads, and filtered exports behave correctly.

## Constitution Check After Design

No violations introduced by the chosen design.
