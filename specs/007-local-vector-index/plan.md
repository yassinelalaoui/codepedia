# Implementation Plan: Local Vector Index

Branch: `007-local-vector-index` | Date: 2026-08-11 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/007-local-vector-index/spec.md`

## Summary

Build a fully local vector index for code fragments and generated summaries
that supports semantic search, incremental additions, and file-scoped removal
without rebuilding the entire index. The index stores embeddings on disk and
returns ranked fragments with similarity scores and source-symbol attribution.

The design uses FAISS as the in-memory similarity engine with persistent index
files on disk, plus local metadata storage for chunk identity, file ownership,
and symbol attribution.

## Technical Context

Language/Version: Python 3.11+
Primary Dependencies: FAISS for vector search, sqlite3 or local metadata files
for index bookkeeping, dataclasses, pathlib, hashlib, and the existing code
fragment and symbol extraction pipeline
Storage: Local on-disk vector index files with local metadata persistence; no
remote service
Testing: pytest with unit, contract, and integration coverage
Target Platform: Local CLI/library usage on Windows, macOS, and Linux
Project Type: Internal indexing and retrieval pipeline for semantic code search
Performance Goals: Interactive top-k retrieval, incremental vector updates, and
quick deletion of all vectors for a modified or removed file
Constraints: Fully local execution, no cloud fallback, read-only analyzed
source repositories, and deterministic search results for the same index state
Scale/Scope: Repository-level semantic retrieval over batches of code fragments
and generated summaries

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentiality absolute: pass
- Zero exposure network by default: pass
- Never repli silently vers le cloud: pass
- Traceabilite des reponses IA: pass; feature stores embeddings and metadata,
  not AI-generated answers
- Re-indexation incrementale: pass; vector additions and deletions are file
  scoped
- Infrastructure minimale et stockage local: pass; the index remains a local
  file-based artifact
- Depot analyse en lecture seule: pass

## Project Structure

### Documentation for this feature

`specs/007-local-vector-index/`
- `plan.md`
- `research.md`
- `data-model.md`
- `quickstart.md`
- `contracts/`
  - `vector-index-interface.md`
  - `vector-index-storage.md`

### Source Code

`src/`
- `vector_index/`
  - `__init__.py`
  - `models.py`
  - `index.py`
  - `storage.py`
  - `search.py`
  - `chunking.py`
- `parser_engine/`
- `dependency_graph/`

Structure Decision: Keep vector search isolated in a dedicated vector-index
package so semantic retrieval can consume code chunks, embeddings, and source
symbol references without coupling search logic to AST parsing or dependency
graph assembly.

## Phase 0: Research

### Decision 1

Use FAISS as the local similarity engine for top-k semantic search.

### Decision 2

Persist the vector index on disk with a separate local metadata store so chunk
identity, file ownership, and symbol attribution can be updated independently
from the vector payload.

### Decision 3

Model each searchable unit as a `CodeChunk` that carries content, embedding,
and source symbol identity.

### Decision 4

Support file-scoped rebuild and deletion operations so modified or deleted
files can be removed and re-added without affecting unrelated vectors.

### Decision 5

Return ranked search results with scores and source-symbol attribution so the
retrieval layer is directly useful in an interactive chat workflow.

## Phase 1: Design

### Data model

Define vector chunks, search queries, search results, local persistence
records, and index state with validation rules and file-scoped lifecycle
behavior.

### Contracts

Document the public vector-index interface and the persistent storage layout
expected by the retrieval layer.

### Quickstart

Provide validation steps that prove indexing, incremental updates, file
deletions, reopen behavior, and semantic search quality.

## Constitution Check After Design

No violations introduced by the chosen design.
