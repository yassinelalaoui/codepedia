# Implementation Plan: Resumable Chat Sessions via Streaming, Listing & History

**Branch**: `027-resumable-chat-sessions` | **Date**: 2026-08-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/027-resumable-chat-sessions/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Expose session discovery on the existing local chat API: a new `GET /sessions`
route lists every persisted session (id, `createdAt`, `lastActivityAt`,
ordered most-recently-active first) so a client that lost track of its
session id — after a page reload, a dropped connection, or a server
restart — can find it again and pull back its complete history through the
already-existing per-session history route. Progressive answer delivery
(the "streaming" half of the request) is already implemented end-to-end at
the pipeline and HTTP layers (`ChatSession.askStream()`, `POST
/sessions/{id}/messages` as Server-Sent Events, spec 026) — this feature's
technical work there is to actually wire up the shipped web client
(`chatApiClient.ts`, `ChatPanel.tsx`) to consume that stream progressively,
since it currently still calls `response.json()` against an SSE body (a gap
026 explicitly deferred as "No frontend changes"), which is why User Story 2
cannot yet be demonstrated end-to-end through the project's own UI. No new
route is added for asking a question; no new dependency, database table, or
network-exposure change is introduced — every new route stays bound to
`127.0.0.1` by default under the existing local-only policy (constitution
2.2, spec Part 5.1), unchanged.

## Technical Context

**Language/Version**: Python 3.11 (backend, `chat_api`/`chat` packages); TypeScript + React 18 (frontend, `frontend/src`)

**Primary Dependencies**: FastAPI + Starlette (existing, `chat_api/app.py`), pydantic (existing, `chat_api/schemas.py`), stdlib `sqlite3` via `repository_metadata.sqlite_store.connect` (existing) — no new backend dependency. React + Vite (existing, `frontend/`) — no new frontend dependency.

**Storage**: SQLite, reusing the existing `chat_sessions` / `chat_messages` tables (spec 025, `repository_metadata.sqlite_store.SCHEMA_STATEMENTS`) — no schema change, no migration.

**Testing**: pytest + pytest-asyncio (backend, `tests/contract`, `tests/integration`, `tests/unit`); Vitest + Testing Library (frontend, `frontend/tests`) — both already configured.

**Target Platform**: Cross-platform local server (Windows/Linux/macOS) served by the existing local web server (spec 015); consumed by the bundled documentation-wiki web UI (spec 016) served from the same origin.

**Project Type**: Web application (existing backend + frontend split: `src/chat_api`, `src/chat` for backend; `frontend/` for the bundled UI) — Option 2 structure, already established by specs 014–026.

**Performance Goals**: Time-to-first-fragment for a streamed answer stays roughly flat regardless of final answer length (SC-002, already met by the existing `askStream()`/SSE pipeline — this feature does not change pipeline timing). Listing sessions and retrieving a chosen session's full history together complete within 2 seconds (SC-005) — trivially met by a single indexed `SELECT` over a locally-stored, moderate-sized table.

**Constraints**: New routes MUST bind only to `127.0.0.1`/local-network by default, inheriting the existing server's binding — no new binding logic, no per-route exposure configuration (FR-008, constitution 2.2). No new runtime dependency, no schema/migration (constitution 2.6). Existing callers of `POST /sessions`, `POST /sessions/{id}/messages`, `GET /sessions/{id}/messages` MUST see unchanged behavior (FR-009).

**Scale/Scope**: Single local user/operator; a moderate number of accumulated sessions over the tool's lifetime (not a multi-tenant or high-volume server) — full, unpaginated listing is sufficient (per spec.md Assumptions).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| 2.1 Confidentialite par defaut | Not implicated: listing sessions and reading history are local reads of already-persisted, already-generated data; no new network call, no new engine involved. PASS. |
| 2.2 Zero exposition reseau par defaut | New routes are registered on the same FastAPI app instance, bound the same way as every existing route (127.0.0.1 by default, per Part 5.1) — no new binding surface is introduced. PASS. |
| 2.3 Jamais de repli silencieux vers le cloud | Not implicated: no engine-selection logic in this feature. PASS. |
| 2.4 Tracabilite des reponses IA | Unaffected: citations already attached to persisted messages (spec 011/014) are returned unchanged by the existing history route; this feature adds no new answer-generation path. PASS. |
| 2.5 Re-indexation incrementale | Not implicated: no indexing/analysis logic touched. PASS. |
| 2.6 Infrastructure minimale et stockage local | No new dependency, no new table, no external service — `GET /sessions` is one new `SELECT` against the existing SQLite file. PASS. |
| 2.7 Depot analyse en lecture seule | Not implicated: no source-repository writes. PASS. |

No violations. Complexity Tracking table intentionally omitted (nothing to justify).

**Post-Phase-1 re-check**: Phase 1 design (`data-model.md`, `contracts/`)
introduces one new SQL read (`list_sessions`, no new table/column), two new
pydantic view types, one new route, and a frontend fix to actually consume
data the backend already sends. None of this adds a network exposure
surface, a remote call, a new dependency, or a repository write. All gates
above still PASS unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/027-resumable-chat-sessions/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── chat/
│   ├── models.py            # ChatSession/ChatMessage (unchanged)
│   ├── sqlite_store.py       # + list_sessions(db_path) -> tuple[ChatSession, ...]
│   ├── session.py            # ChatSession.askStream() (unchanged, already exists - 026)
│   └── retrieval.py          # unchanged
├── chat_api/
│   ├── app.py                # + GET /sessions route
│   ├── schemas.py            # + SessionSummary, SessionListResponse
│   └── session_store.py      # + SessionRegistry.list_sessions()
└── repository_metadata/
    └── sqlite_store.py       # unchanged (chat_sessions/chat_messages DDL already present - 025)

frontend/
├── src/
│   ├── lib/
│   │   └── chatApiClient.ts  # askQuestion(): parse the SSE body progressively instead
│   │                          #   of response.json(); + listSessions()
│   └── components/
│       └── ChatPanel.tsx     # render assistant fragments progressively as they arrive
└── tests/
    ├── ChatPanel.test.tsx     # extend for progressive rendering + session listing
    └── chatApiClient.test.ts # new: SSE parsing, listSessions()

tests/
├── contract/
│   └── test_chat_persistence_interface.py  # + list_sessions contract coverage
├── integration/
│   ├── test_chat_api.py           # + GET /sessions coverage
│   └── test_chat_session.py       # + list_sessions coverage via SessionRegistry
└── unit/
    └── test_chat_sqlite_store.py  # + list_sessions ordering/persistence coverage
```

**Structure Decision**: Extends the existing web-application split (`src/chat*` backend
packages + `frontend/`) already established by specs 014–026; no new top-level
directory or package is introduced. All new code lands inside modules that
already exist for this exact concern (session persistence, the chat HTTP
API, the bundled chat UI).

## Complexity Tracking

Not applicable — no constitution violations to justify.
