# Implementation Plan: Chat Streaming & Conversational Context Retrieval

**Branch**: `026-chat-streaming-context` | **Date**: 2026-08-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/026-chat-streaming-context/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Two independent changes to the chat/RAG pipeline. (1) `LLMEngine` becomes a
formal interface with `generateStream(prompt) -> AsyncIterator[str]` as the
primitive; `generate()` becomes a sync convenience wrapper that drains the
stream and concatenates. `LocalLLMEngine` gains a real streaming transport
(`httpx.AsyncClient`, Ollama's `"stream": true` NDJSON), and a new
`GroqLLMEngine` implements the same interface against Groq's OpenAI-compatible
streaming chat API — added only as an explicit, opt-in alternative (never a
default, never an automatic fallback), which required amending the project
constitution (2.1/2.3, now v2.0.0) first. (2) `retrieve_evidence` gains a
`history` parameter (the session's last 2-3 exchanges, already available via
`chat.sqlite_store` from 025) and builds a locally-assembled, conversationally
-enriched search query from it before calling `VectorIndex.search` — no LLM
call, no network dependency beyond whichever engine is already configured for
answers. `ChatSession.ask()` is replaced by `ChatSession.askStream()`, an
async generator yielding answer fragments and finally the persisted
`ChatMessage`. `POST /sessions/{id}/messages` becomes a Server-Sent-Events
streaming endpoint.

## Technical Context

**Language/Version**: Python 3.11 (backend). No frontend change — spec.md's
Assumptions explicitly scope the wiki chat UI out of this feature.

**Primary Dependencies**: `httpx` (already a direct dependency, `>=0.27`) for
both the new local streaming transport and the new Groq transport — no new
runtime dependency. `pytest-asyncio` added as a **test-only** dependency to
drive the new async generators (`generateStream`, `askStream`) in unit tests
without hand-rolled `asyncio.run()` boilerplate in every test.

**Storage**: No schema change. Reuses `chat.sqlite_store` (025) exactly as
built — `askStream()` persists the completed assistant `ChatMessage` the same
way `ask()` did, once the stream finishes; nothing new is added to
`chat_sessions`/`chat_messages`.

**Testing**: `pytest` + `pytest-asyncio` for the new async engine/session
code (`tests/unit`, `tests/contract`, `tests/integration`, matching this
project's existing per-package layout); FastAPI's `TestClient` already
handles async route handlers and streaming responses without needing
`pytest-asyncio` at the HTTP-contract-test level.

**Target Platform**: Same as the rest of the project — local machine, server
bound to `127.0.0.1`. `GroqLLMEngine` is the project's first component that,
when explicitly configured, makes an outbound call to a non-local host; this
is a deliberate, narrow exception (constitution 2.1 v2.0.0), not a change to
the server's own network binding (2.2, untouched).

**Project Type**: Web application (existing `src/*` backend packages +
`frontend/`) — this feature touches only backend packages; `GroqLLMEngine`
lives inside the existing `local_llm` package (this project's "Partie 3.1"),
not a new top-level package, per the request's own framing.

**Performance Goals**: Time-to-first-fragment stays flat regardless of final
answer length (SC-002) — achieved structurally by streaming from the first
network chunk rather than buffering the whole response. Query enrichment
(FR-005) adds no LLM round-trip (pure local text/citation concatenation), so
it adds negligible latency ahead of retrieval.

**Constraints**: Query enrichment MUST stay local-only regardless of which
answer-generation engine is configured (FR-006/FR-010) — this is why
enrichment uses plain local concatenation of recent question text and
already-persisted citation data, never an LLM rewrite call (see research.md
Decision 3). A remote engine, once configured, is never used silently as a
fallback for the local engine or vice versa (FR-014, constitution 2.3
v2.0.0). No new dependency beyond `httpx` (already present) plus a test-only
`pytest-asyncio`.

**Scale/Scope**: Backend: `local_llm` gains a Protocol, a streaming local
transport, and a full new Groq engine+transport+errors; `chat` gains
history-aware retrieval and an async `askStream()` replacing `ask()`;
`chat_api` gains an SSE streaming route; `cli` gains remote-engine
configuration (provider selection, model, API key via environment variable —
never persisted to `config.json`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

This feature required a constitution amendment before this gate could pass —
see spec.md's Clarifications (the `/speckit-plan`-time Q&A) and
`.specify/memory/constitution.md`'s Sync Impact Report (v1.0.0 → v2.0.0).
Checked against the **amended** constitution:

| Principle | Check | Status |
| --- | --- | --- |
| 2.1 Confidentialité par défaut, moteur distant sur choix explicite | Analysis/indexing/embeddings stay local-only, no exception (unchanged). Chat answer generation may use an explicitly-configured remote engine (`GroqLLMEngine`) — never default, never automatic; configuring one discloses that questions + cited code context leave the machine (FR-013). | PASS |
| 2.2 Zéro exposition réseau | No new inbound exposure; the server's own bind address is untouched. `GroqLLMEngine` is an *outbound* call, made only when explicitly configured — orthogonal to this principle, which governs the server's own listening socket. | PASS |
| 2.3 Jamais de repli silencieux vers le cloud | No fallback logic is written between engines in either direction (FR-014) — the engine factory (research.md Decision 2) builds exactly the one engine configured; unavailability of the configured engine is reported, never silently substituted. | PASS |
| 2.4 Traçabilité des réponses IA | Citations are still computed from retrieved evidence and attached to the complete, assembled answer only, once generation finishes (FR-004) — unchanged regardless of streaming or which engine is configured. | PASS |
| 2.5 Ré-indexation incrémentale | Not applicable — no indexing behavior involved. | PASS |
| 2.6 Infrastructure minimale, stockage local | No new runtime dependency (`httpx` already present); `pytest-asyncio` is test-only. No new storage — reuses 025's schema unchanged. | PASS |
| 2.7 Dépôt analysé en lecture seule | Not applicable — nothing here touches the analyzed repository's files. | PASS |

No unjustified violations. Re-checked after Phase 1 design below — still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/026-chat-streaming-context/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

Extends existing backend packages only; no new top-level package.

```text
src/
├── local_llm/
│   ├── protocol.py         # NEW: LLMEngine Protocol (isAvailableLocally, checkAvailability,
│   │                          generate, generateStream)
│   ├── models.py            # + no change to PromptEnvelope/GenerationResult/AvailabilityStatus
│   │                          (reused as-is by both engines)
│   ├── engine.py             # LocalLLMEngine: + generateStream (async), generate() becomes
│   │                          a sync wrapper draining the stream
│   ├── transport.py          # LocalLLMTransport: + streaming Ollama call via httpx.AsyncClient
│   ├── groq_engine.py        # NEW: GroqLLMEngine (same Protocol)
│   ├── groq_transport.py     # NEW: Groq streaming chat-completions HTTP client
│   ├── errors.py             # + RemoteLLMError hierarchy alongside existing LocalLLMError
│   └── __init__.py           # + create_llm_engine(config) factory, new exports
│
├── chat/
│   ├── retrieval.py          # retrieve_evidence(...) + history param, build_enriched_query()
│   ├── session.py            # ChatSession.ask() -> askStream() (async generator); persists
│   │                          the completed ChatMessage once the stream finishes
│   └── prompting.py           # unchanged - still builds a PromptEnvelope from RAGContext
│
├── chat_api/
│   ├── app.py                 # POST /sessions/{id}/messages becomes an async SSE route
│   └── schemas.py             # + streamed-fragment/completion event shapes
│
└── cli/
    ├── config.py               # CLIConfiguration: + llmProvider, remoteLlmModel
    │                             (API key read from GROQ_API_KEY env var, never persisted)
    ├── config_command.py       # + --llm-provider/--remote-llm-model flags, disclosure message
    ├── availability.py         # check_ai_dependencies(...) typed against the LLMEngine Protocol
    ├── index_command.py        # uses local_llm.create_llm_engine(config) instead of always
    └── serve_command.py         # create_local_llm_engine(...) directly

tests/
├── contract/  test_local_llm_engine_interface.py (extended: Protocol + generateStream),
│              test_chat_api_server.py (extended if the SSE contract needs a dedicated check)
├── unit/      test_local_llm.py (extended), test_chat_session.py-equivalent unit coverage,
│              new test_groq_llm_engine.py, new test_chat_retrieval.py
└── integration/  test_chat_session.py (extended: streaming + enriched retrieval),
                   test_chat_api.py (extended: SSE contract)

pyproject.toml  # + pytest-asyncio under [project.optional-dependencies].test
```

**Structure Decision**: Existing web-application layout, no new package.
`GroqLLMEngine` lives inside `local_llm` (this project's "Partie 3.1")
alongside `LocalLLMEngine`, per the request's own framing, rather than a new
package — both implement the same `LLMEngine` Protocol defined in a new
`local_llm/protocol.py`.

## Complexity Tracking

No unjustified Constitution Check violations — the one real violation this
feature touches (a network-calling component, previously forbidden outright)
is the deliberate, explicitly-authorized subject of the constitution
amendment itself (Sync Impact Report, v2.0.0), not an undocumented exception
snuck past the gate. Nothing further to track here.

## Post-Design Constitution Check

*Re-evaluated after Phase 1 (data-model.md, contracts/, quickstart.md).*

All seven amended principles re-checked against the finalized design: still
**PASS**, unchanged from the pre-research check above. Two design choices
worth calling out against 2.1/2.3 specifically, since they're where this
design could have quietly drifted:

- **Query enrichment (Decision 3) stays local-only even when a remote
  engine is configured** — it never routes through `GroqLLMEngine`, closing
  off what would have been the easiest way for this feature to silently
  grow its cloud exposure beyond what the constitution's amendment
  authorized (chat answer generation only).
- **The engine factory (Decision 2) contains no fallback branch at all** —
  2.3's "never silent, never automatic" guarantee is satisfied by the
  absence of switching code, not by a runtime check that could later be
  bypassed or forgotten.
