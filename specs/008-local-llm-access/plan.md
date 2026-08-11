# Implementation Plan: Local LLM Access Layer

Branch: `008-local-llm-access` | Date: 2026-08-11 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/008-local-llm-access/spec.md`

## Summary

Build a local-only LLM access layer that targets an Ollama-compatible HTTP
server on `http://localhost:11434`, verifies availability before generation,
and returns explicit local errors when the service or model is unavailable.
The same engine will be reused by both summary generation during indexing and
chat response generation.

## Technical Context

Language/Version: Python 3.11+
Primary Dependencies: Python standard library HTTP/JSON utilities, dataclasses,
pathlib, typing, and the existing pytest-based test stack
Storage: None required beyond in-memory configuration; the engine talks to the
local Ollama HTTP service only
Testing: pytest with unit, contract, and integration coverage
Target Platform: Local CLI/library usage on Windows, macOS, and Linux
Project Type: Internal library layer used by indexing and chat workflows
Performance Goals: Fast availability checks before each generation request and
low-latency local prompt execution suitable for interactive use
Constraints: Local-only networking, no silent fallback to cloud providers, and
explicit error reporting when Ollama is stopped or the model is missing
Scale/Scope: Single-process access layer used by two product paths

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentiality absolute: pass
- Zero exposure network by default: pass
- Never reply silently with a cloud service: pass
- Traceability of AI responses: pass; the layer surfaces model output and
  explicit errors, not hidden remote routing
- Incremental local operation: pass; availability checks and generation are
  local and stateless
- Minimal infrastructure and local storage: pass; no extra service beyond the
  local model server
- Repository analysis read-only: pass; this feature does not mutate source code

## Project Structure

### Documentation for this feature

`specs/008-local-llm-access/`
- `spec.md`
- `research.md`
- `data-model.md`
- `quickstart.md`
- `contracts/`
  - `local-llm-engine.md`

### Source Code

`src/`
- `local_llm/`
  - `__init__.py`
  - `engine.py`
  - `errors.py`
  - `models.py`
  - `transport.py`

Structure Decision: Keep the local LLM integration in a dedicated package so
summary generation and chat generation can share the same availability check,
error model, and HTTP transport without coupling to indexing or chat logic.

## Phase 0: Research

### Decision 1

Use Ollama-compatible HTTP endpoints on `http://localhost:11434` as the
default local backend.

### Decision 2

Use `GET /api/version` as the primary service availability check and
`GET /api/tags` to confirm that the configured model is installed locally
before sending generation traffic.

### Decision 3

Use `POST /api/generate` with streaming disabled for a single text response
that can serve both code summaries and chat replies.

### Decision 4

Model the user-facing surface as a small `LocalLLMEngine` abstraction with
explicit local-only errors and no fallback path.

### Decision 5

Keep the transport implementation on the Python standard library to avoid new
third-party dependencies and preserve the repository's minimal local footprint.

## Phase 1: Design

### Data model

Define the local engine, prompt envelope, generation request/response payloads,
availability result, and explicit local-only errors.

### Contracts

Document the `LocalLLMEngine` interface and the expected failure behavior when
the service or model is unavailable.

### Quickstart

Provide validation steps that prove availability checks, generation, and
failure behavior against a real local Ollama instance.

## Constitution Check After Design

No violations introduced by the chosen design.
