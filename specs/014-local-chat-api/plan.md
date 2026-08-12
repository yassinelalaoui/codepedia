# Implementation Plan: Local Chat API

Branch: `014-local-chat-api` | Date: 2026-08-12 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/014-local-chat-api/spec.md`

## Summary

Add a thin local HTTP layer on top of the existing local RAG pipeline
(`chat.ChatSession`, feature 011) so a web interface can drive it over HTTP
instead of importing it as a Python library. The service exposes three
operations — create a session, ask a question on a session, and read a
session's message history — as JSON endpoints, and binds only to
`127.0.0.1` (or another local/private address the user explicitly chooses)
so it is never reachable from the public internet by default.

No retrieval, generation, or citation logic is added: every request is
translated directly into a call on the existing `ChatSession`, and every
response is a JSON projection of the existing `ChatMessage`/`Citation`
dataclasses. Sessions live in an in-memory registry for the lifetime of the
running process — no new database or broker is introduced.

## Technical Context

Language/Version: Python 3.11+, consistent with the rest of the toolchain
(`chat`, `vector_index`, `embedding_engine`, `local_llm`, `doc_generator`)

Primary Dependencies: FastAPI + uvicorn (new); reuses the existing `chat`,
`vector_index`, `embedding_engine`, and `local_llm` packages unchanged as the
answer-generation backend

Storage: No new persistence. Sessions are held in an in-memory registry
scoped to the running server process; the underlying `VectorIndex` and its
SQLite files are the same ones already produced by the existing indexing
pipeline (004/007/009) and are opened read-only from this feature's
perspective

Testing: pytest, using FastAPI's in-process `TestClient` (ASGI transport, no
real socket) plus fake embedding/LLM engines — the same fake-engine pattern
already used in `tests/integration/test_chat_session.py` — to assert
response shapes, status codes, and that no outbound network call occurs

Target Platform: Runs as a local process on the same machine as the rest of
the toolchain (Windows/macOS/Linux); consumed by an HTTP client on
`localhost` or the user's local network

Project Type: Extension of the existing internal pipeline — a new thin API
package (`chat_api`) that composes `chat`, `vector_index`, `embedding_engine`,
and `local_llm` behind HTTP endpoints; no frontend is built by this feature

Performance Goals: Interactive, single-user local usage (one browser tab
talking to one local server); no concurrent-load or throughput target

Constraints: Server MUST bind to `127.0.0.1` (or another explicit
local/private address) by default; MUST NOT accept connections from the
public internet without an explicit, separate user action; MUST NOT make any
outbound network call while handling a request, beyond what the already-local
embedding/LLM engines do against `localhost`

Scale/Scope: Single repository's index served per running instance, single
local user, session count and history length bounded only by process memory

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentialite absolue: pass; the API layer adds no new outbound calls —
  it only orchestrates the already-local `ChatSession`, `EmbeddingEngine`,
  and `LocalLLMEngine`, which already talk to `localhost` only
- Zero exposition reseau par defaut: pass; this is the feature's central
  constraint — the server binds to `127.0.0.1` by default (Decision 2) and
  requires an explicit, separate flag to bind elsewhere
- Jamais de repli silencieux vers le cloud: pass; `LocalDependencyUnavailableError`
  from `ChatSession.ask` is mapped to an explicit `503` response (Decision 6)
  instead of any fallback
- Tracabilite des reponses IA: pass; every answer response serializes the
  existing `citedSymbolIds`/`citedFilePaths` from `ChatMessage` as structured
  fields (Decision 7), never prose-only
- Re-indexation incrementale: not applicable; this feature does not touch
  indexing, it only reads an already-built index
- Infrastructure minimale et stockage local: pass; sessions are an in-memory
  registry inside the existing process (Decision 3), no new database, broker,
  or external service; FastAPI/uvicorn are local, in-process libraries, not
  infrastructure
- Depot analyse en lecture seule: pass; the API never writes to the analyzed
  repository, it only reads the pre-built local vector index

## Project Structure

### Documentation for this feature

`specs/014-local-chat-api/`
- `spec.md`
- `plan.md`
- `research.md`
- `data-model.md`
- `quickstart.md`
- `contracts/`
  - `chat-api.md`

### Source Code

`src/`
- `chat_api/` (new package)
  - `__init__.py`
  - `app.py` (FastAPI app factory: `create_app(vector_index, embedding_engine, llm_engine)`)
  - `schemas.py` (Pydantic request/response models, decoupled from `chat`'s internal dataclasses)
  - `session_store.py` (in-memory `session_id -> ChatSession` registry)
  - `errors.py` (maps `LocalDependencyUnavailableError` / unknown session id / empty question to structured HTTP error responses)
  - `server.py` (uvicorn entrypoint; binds `127.0.0.1` by default, requires an explicit `--host` to bind elsewhere)
- `chat/` (reused, unmodified: `ChatSession`, `ChatMessage`, `Citation`, `RAGContext`, `LocalDependencyUnavailableError`)
- `vector_index/`, `embedding_engine/`, `local_llm/` (reused, unmodified)

`tests/`
- `integration/test_chat_api.py` (new: end-to-end HTTP flow against the FastAPI app with fake engines)
- `integration/test_chat_api_network_boundary.py` (new: starts a real server instance and confirms it accepts connections only on `127.0.0.1`, not the machine's LAN-visible address)
- `unit/test_chat_api_errors.py` (new: error-mapping unit tests)
- `unit/test_chat_api_server.py` (new: uvicorn bind-configuration unit tests)

Structure Decision: introduce a new `chat_api` package rather than adding
HTTP concerns into the existing `chat` package. `chat` is a pure local
library with no knowledge of HTTP, sessions-as-a-resource, or wire formats;
keeping the API layer separate mirrors how `doc_generator` composes
`dependency_graph` and `repository_metadata` from the outside instead of
absorbing them, and lets `chat` keep being usable as a plain library (e.g.
by a future CLI) without an HTTP server in the loop.

## Phase 0: Research

### Decision 1

Use FastAPI (with Pydantic request/response models) over Express/Node, since
the entire toolchain this feature composes (`chat`, `vector_index`,
`embedding_engine`, `local_llm`) is already Python — an in-process Python
call is simpler and has fewer moving parts than adding a second-language
process boundary and a cross-process protocol.

### Decision 2

Default the server to `uvicorn.run(..., host="127.0.0.1")` and require an
explicit `--host` argument to bind anywhere else (e.g. a private LAN
address). There is no default that resolves to a public-reachable bind
address; changing the bind address is always a deliberate, separate action
by the user, per the spec's local-only requirement and constitution 2.2.

### Decision 3

Hold sessions in a plain in-memory dictionary (`session_id -> ChatSession`)
owned by the FastAPI app's state, rather than adding a new database table.
This matches the spec's Assumption that sessions are process-lifetime only,
and keeps this feature from introducing new persistent storage the
constitution's "infrastructure minimale" principle would have to justify.

### Decision 4

Generate session identifiers as random UUID4 hex strings, assigned at
creation time and never reused, so identifiers are unguessable and stable
for the life of the process.

### Decision 5

Construct exactly one `VectorIndex`, one `EmbeddingEngine`, and one
`LocalLLMEngine` at server startup (via the existing `create_embedding_engine`
/ `create_local_llm_engine` factories and `VectorIndex(...)`), and share them
across all sessions created by that running server. This matches the spec's
Assumption of a single local user operating against one indexed repository
per running instance; a new repository means starting a new server instance,
not switching repositories mid-process.

### Decision 6

Map `chat.LocalDependencyUnavailableError` to an HTTP `503` response with a
structured JSON body carrying a stable machine-readable `code` field (e.g.
`"local_dependency_unavailable"`), map an unknown session id to `404`, and
map an empty/whitespace-only question to `422` (FastAPI/Pydantic's standard
validation-error shape). Every error path returns before any answer text is
generated and before anything is appended to session history, matching
`ChatSession.ask`'s existing behavior of raising before mutating state.

### Decision 7

Define API-facing Pydantic schemas (`AskQuestionResponse`, `ChatMessageView`,
etc.) that are separate from `chat`'s internal dataclasses, mapping field for
field (`citedSymbolIds`, `citedFilePaths`, `role`, `content`, `timestamp`).
This keeps the HTTP wire contract stable even if the internal `chat` package
evolves, and gives the response an explicit, documented shape instead of
relying on dataclass introspection.

### Decision 8

Rely on the network-level bind restriction (Decision 2) as the sole access
boundary; do not add an application-level auth token or login flow. This
matches the spec's Non-Goal of authentication beyond local-machine/network
trust, and avoids adding credential storage — itself a piece of
infrastructure the constitution's minimalism principle would have to
justify — for a single-local-user tool.

## Phase 1: Design

### Data model

Define new API-layer entities: `CreateSessionResponse`, `AskQuestionRequest`,
`AskQuestionResponse`, `ChatMessageView`, `SessionHistoryResponse`, and
`ApiErrorResponse`. Reuse `chat.ChatSession`, `chat.ChatMessage`,
`chat.Citation`, `chat.RAGContext`, and `chat.LocalDependencyUnavailableError`
unchanged as the underlying model. See `data-model.md`.

### Contracts

Document three HTTP endpoints — `POST /sessions`, `POST
/sessions/{sessionId}/messages`, `GET /sessions/{sessionId}/messages` — their
request/response schemas, status codes, and the default local-only bind
behavior. See `contracts/chat-api.md`.

### Quickstart

Provide validation steps that start the server bound to `127.0.0.1`, drive
the three endpoints end-to-end with `curl` (create a session, ask a
question, read history), and confirm both that no outbound network request
occurs during a question and that the server does not accept connections on
a non-local interface without an explicit `--host` override. See
`quickstart.md`.

## Constitution Check After Design

No violations introduced by the chosen design. FastAPI and uvicorn are new,
local, in-process dependencies (declared in `pyproject.toml`), not new
infrastructure; no new persistent storage, no new outbound network path, and
no change to the analyzed repository's read-only status.
