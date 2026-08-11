# Implementation Plan: Local Embedding Engine

Branch: `009-local-embedding-engine` | Date: 2026-08-11 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/009-local-embedding-engine/spec.md`

## Summary

Build a fully local embedding engine that converts either code fragments or
natural-language text into vectors, using a local embedding model by default
via an Ollama-compatible endpoint. The engine will expose a small
`EmbeddingEngine` abstraction, perform explicit availability checks before
embedding, and surface clear local-only errors when the model runtime or model
is unavailable.

The engine will be wired into the existing vector indexing path so that code
chunks and user queries share the same embedding behavior.

## Technical Context

Language/Version: Python 3.11+
Primary Dependencies: Python standard library HTTP/JSON utilities, dataclasses,
pathlib, typing, and the existing pytest-based test stack
Storage: None required; the engine is stateless and operates against a local
model runtime
Testing: pytest with unit, contract, and integration coverage
Target Platform: Local CLI/library usage on Windows, macOS, and Linux
Project Type: Internal library layer used by indexing and semantic retrieval
Performance Goals: Fast preflight availability checks and interactive embedding
latency suitable for search and indexing workflows
Constraints: Local-only execution, no silent fallback to a remote service, and
explicit error reporting when the local embedding model is stopped or missing
Scale/Scope: Single-process embedding abstraction shared by indexing and query
vectorization

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentiality absolute: pass
- Zero exposure network by default: pass
- Never reply silently with a cloud service: pass
- Traceability of AI responses: pass; embeddings are derived locally and are
  associated with source fragments for retrieval, not exposed through hidden
  remote routing
- Incremental local operation: pass; embedding checks and vectorization are
  local operations
- Minimal infrastructure and local storage: pass; no extra service beyond the
  local embedding runtime
- Repository analysis read-only: pass; this feature does not mutate analyzed
  source code

## Project Structure

### Documentation for this feature

`specs/009-local-embedding-engine/`
- `spec.md`
- `research.md`
- `data-model.md`
- `quickstart.md`
- `contracts/`
  - `embedding-engine.md`

### Source Code

`src/`
- `embedding_engine/`
  - `__init__.py`
  - `engine.py`
  - `errors.py`
  - `models.py`
  - `transport.py`
- `vector_index/`
  - `chunking.py`
  - `search.py`

Structure Decision: keep the embedding engine in its own package so the code
chunk pipeline and the search/query pipeline can share one local embedding
abstraction without tying the feature to a single caller. The existing
`vector_index` package remains the integration surface for code fragments and
semantic search queries.

## Phase 0: Research

### Decision 1

Use an Ollama-compatible local embedding endpoint as the default backend, with
`nomic-embed-text` as the default model name.

### Decision 2

Expose an explicit availability check that verifies the local runtime is
reachable and the configured embedding model is present before any vector is
requested.

### Decision 3

Model the user-facing surface as a compact `EmbeddingEngine` abstraction with a
single `embed(text)` method and clear local-only failures for missing or
unavailable models.

### Decision 4

Integrate the engine at the existing vectorization call sites in
`src/vector_index/chunking.py` and `src/vector_index/search.py` so both code
fragments and user queries use the same vectorization path.

### Decision 5

Keep the transport implementation on the Python standard library to avoid new
runtime dependencies while preserving the repository's offline footprint.

## Phase 1: Design

### Data model

Define the embedding engine, vector payload, availability result, embedding
request/response, and explicit local-only errors. Capture the empty-input rule
as a deterministic validation outcome.

### Contracts

Document the `EmbeddingEngine` interface and the expected failure behavior when
the local model service is stopped, the configured model is missing, or the
input text is invalid.

### Quickstart

Provide validation steps that prove local availability checks, vector
generation, semantic proximity, and explicit failure behavior against a real
local embedding runtime.

## Constitution Check After Design

No violations introduced by the chosen design.
