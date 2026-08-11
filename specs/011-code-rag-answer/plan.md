# Implementation Plan: Local Code RAG Answering

Branch: `011-code-rag-answer` | Date: 2026-08-11 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/011-code-rag-answer/spec.md`

## Summary

Build a local retrieval-augmented question-answering pipeline that turns a
developer question into an embedding, searches the local vector index for the
most relevant code fragments and summaries, assembles the retrieved evidence
into a prompt, and asks the local LLM for a grounded natural-language answer.
The answer must cite the files and symbols that support it and must stay fully
local end to end.

The design reuses the existing `EmbeddingEngine` for query vectorization, the
existing `VectorIndex` for similarity search, and the existing `LocalLLMEngine`
for answer generation. `ChatSession` will maintain ordered conversation state
while `ChatMessage` carries the generated response, citations, and timestamp.

## Technical Context

Language/Version: Python 3.11+
Primary Dependencies: Python standard library, `embedding_engine`,
`vector_index`, `local_llm`, and the existing pytest-based test stack
Storage: Existing local vector index persistence and index metadata; no new
remote service or external database
Testing: pytest with unit, contract, and integration coverage
Target Platform: Local CLI/library usage on Windows, macOS, and Linux
Project Type: Internal library layer used by local developer chat workflows
Performance Goals: Interactive question answering with fast retrieval and
bounded prompt assembly suitable for live chat use
Constraints: Local-only execution, no cloud fallback, explicit citation of
retrieved evidence, and no transmission of repository code to any non-local
service
Scale/Scope: Repository-level interactive question answering over indexed code
and generated summaries

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentiality absolute: pass
- Zero exposure network by default: pass
- Never reply silently with a cloud service: pass
- Traceability of AI responses: pass; answers must cite the files and symbols
  used as evidence
- Incremental local operation: pass; retrieval and response generation stay
  local and reuse precomputed index data
- Minimal infrastructure and local storage: pass; the feature reuses the local
  vector index and local LLM
- Repository analysis read-only: pass; question answering does not mutate the
  repository

## Project Structure

### Documentation for this feature

`specs/011-code-rag-answer/`
- `spec.md`
- `research.md`
- `data-model.md`
- `quickstart.md`
- `contracts/`
  - `chat-session.md`

### Source Code

`src/`
- `chat/`
  - `__init__.py`
  - `models.py`
  - `session.py`
  - `prompting.py`
  - `retrieval.py`
- `embedding_engine/`
  - `engine.py`
- `vector_index/`
  - `index.py`
  - `models.py`
  - `search.py`
- `local_llm/`
  - `engine.py`

Structure Decision: keep the chat-oriented orchestration in a dedicated
`chat` package so the question-answer flow can compose the existing embedding,
retrieval, and generation layers without introducing a new backend service or
mixing session state into the index implementation.

## Phase 0: Research

### Decision 1

Use the existing `EmbeddingEngine` to convert each user question into a local
vector query before retrieval.

### Decision 2

Use the existing `VectorIndex.search` API as the source of ranked local
evidence, because it already returns content, source symbol identity, source
file path, and similarity score.

### Decision 3

Assemble prompts from the retrieved code fragments and any available summary
text, then send the assembled prompt only to `LocalLLMEngine`.

### Decision 4

Model the conversation as an in-memory `ChatSession` that appends the question
and the generated answer to an ordered message history while returning a
`ChatMessage` for the current turn.

### Decision 5

Represent citations directly in `ChatMessage.citedSymbolIds` and
`ChatMessage.citedFilePaths`, while still rendering file names in the answer
text so the final response stays auditable without any extra external lookup.

## Phase 1: Design

### Data model

Define the session, message, retrieved-evidence, and prompt-context entities
used by the chat pipeline, including validation rules for citation-bearing
answers.

### Contracts

Document the public `ChatSession` and `ChatMessage` interface, the expected
local retrieval behavior, and the failure mode when the embedding engine or
local LLM is unavailable.

### Quickstart

Provide validation steps that prove the pipeline can answer a repository
question, cite the relevant files and symbols, and fail cleanly with no
external network access.

## Constitution Check After Design

No violations introduced by the chosen design.
