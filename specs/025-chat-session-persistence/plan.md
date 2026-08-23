# Implementation Plan: Chat Session Persistence

**Branch**: `025-chat-session-persistence` | **Date**: 2026-08-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/025-chat-session-persistence/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Persist chat sessions and their messages so a conversation survives a server
restart or a wiki page reload. Two new tables — `chat_sessions` and
`chat_messages` — are added to the same per-repository `repository-metadata.sqlite`
file that already holds `repositories`/`source_files`/`symbols` (`repository_metadata`,
005), indexed on `(session_id, timestamp)` for a single-query ordered read. The
existing in-memory `chat.models.ChatSession`/`ChatMessage` dataclasses become the
direct object mapping for these rows — extended with `createdAt`/`lastActivityAt`
on `ChatSession` — with no new/duplicate persistence DTOs. `chat_api.SessionRegistry`
gains a SQLite-backed fallback so `get_session()` reloads a session's full history
from disk on a cache miss (covering both "process restarted" and "browser
reloaded, in-memory session evicted"), and each message is written the instant
`ChatSession.ask()` appends it — never as a full-session rewrite.

## Technical Context

**Language/Version**: Python 3.11 (backend, unchanged), TypeScript/React via Vite (frontend, minor `ChatPanel.tsx` change only)

**Primary Dependencies**: `sqlite3` (stdlib, already used by `repository_metadata.sqlite_store`) — no new runtime dependency; reuses the existing `RepositoryMetadataStore`/`connect()`/`ensure_schema()` machinery.

**Storage**: SQLite — the existing per-repository `repository-metadata.sqlite` file (`cli/paths.py:metadata_db_path`), extended with two tables (`chat_sessions`, `chat_messages`). No new database file, engine, or service.

**Testing**: `pytest` for `chat`/`chat_api`/`repository_metadata` (`tests/unit`, `tests/contract`, `tests/integration`, matching this project's existing per-package layout); `vitest` for the small `ChatPanel.tsx` session-id-resumption change.

**Target Platform**: Same as the rest of the project — local machine (Windows/macOS/Linux), server bound to `127.0.0.1`.

**Project Type**: Web application (existing `src/*` backend packages + `frontend/` — no structural change, this feature extends existing packages).

**Performance Goals**: Appending one message stays a single-row insert (plus a single-row `chat_sessions.lastActivityAt` update) regardless of how many messages already exist in the session (SC-003); reading a session's full history stays exactly one query (SC-004).

**Constraints**: Fully offline, bound to `127.0.0.1`, no new infrastructure/storage engine (FR-009/FR-010); messages are append-only (no edit/delete, per spec Assumptions); must respect `docs/architecture.md`'s downward-only inter-package dependency rule (`repository_metadata` is an earlier layer than `chat` and must not import from it — see research.md Decision 2).

**Scale/Scope**: Backend: two new tables + their CRUD in one existing package (`chat`) plus a schema addition in another (`repository_metadata`), and a `SessionRegistry` change in `chat_api`. Frontend: one component (`ChatPanel.tsx`) gains local-storage-backed session resumption. Validated up to 500 messages/session (SC-003).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
| --- | --- | --- |
| 2.1 Confidentialité absolue | Session/message content never leaves the machine; it's written to the same local SQLite file already used for repository metadata. | PASS |
| 2.2 Zéro exposition réseau | No new server/port/endpoint exposed beyond the existing `127.0.0.1`-bound API; `GET/POST /sessions/...` already exist. | PASS |
| 2.3 Jamais de repli silencieux vers le cloud | Not applicable — this feature adds local durability, no model/inference behavior changes. | PASS |
| 2.4 Traçabilité des réponses IA | `citedSymbolIds`/`citedFilePaths` are persisted per message (FR-002) exactly as generated, so restored history keeps its citations. | PASS |
| 2.5 Ré-indexation incrémentale | Not applicable — no re-indexing behavior involved. | PASS |
| 2.6 Infrastructure minimale, stockage local | Reuses the existing SQLite file; explicitly no new storage engine (FR-009). | PASS |
| 2.7 Dépôt analysé en lecture seule | Not applicable — nothing here touches the analyzed repository's own files, only the tool's local state dir. | PASS |

No violations. Re-checked after Phase 1 design below — still PASS (see end of this document).

## Project Structure

### Documentation (this feature)

```text
specs/025-chat-session-persistence/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This feature extends the project's existing package-per-feature layout
(`docs/architecture.md`); it introduces no new top-level directory.

```text
src/
├── repository_metadata/
│   └── sqlite_store.py       # + chat_sessions/chat_messages DDL in SCHEMA_STATEMENTS,
│                                the (session_id, timestamp) index (still no import of `chat`)
│
├── chat/
│   ├── models.py              # ChatSession gains createdAt/lastActivityAt fields
│   ├── sqlite_store.py        # NEW: create/touch session, append message, load session +
│   │                            ordered history — builds chat.models objects directly,
│   │                            reuses repository_metadata.sqlite_store.connect()
│   └── session.py             # ChatSession.ask() persists each message as it's appended
│
├── chat_api/
│   ├── session_store.py       # SessionRegistry: create_session persists a row; get_session
│   │                            falls back to chat.sqlite_store on an in-memory cache miss
│   ├── app.py                 # create_app(...) takes the metadata db path/store so
│   │                            SessionRegistry can reach chat/sqlite_store.py
│   └── server.py               # threads the metadata db path through from CLI args
│
└── cli/
    ├── index_command.py       # IndexRunResult carries the metadata store/db path onward
    ├── serve_command.py       # same, for the resume path
    └── server.py               # start_local_server(...) passes it into create_app(...)

frontend/src/
└── components/
    └── ChatPanel.tsx          # persist/resume the session id via browser local storage
                                  instead of only an in-memory ref

tests/
├── contract/     test_chat_persistence_interface.py (new), test_repository_metadata_interface.py (extended)
├── unit/         test_chat_api_server.py (existing, unaffected by this feature),
│                  test_chat_sqlite_store.py (new), _chat_persistence_support.py (new, shared fixture),
│                  test_repository_metadata.py (extended)
└── integration/  test_chat_api.py (extended: HTTP-level restart coverage),
                   test_chat_session.py (extended: restart/incremental-write scenarios)
```

**Structure Decision**: Existing web-application layout (`src/*` backend
packages and `frontend/`) — no new package or directory. The two new tables live in the
already-existing `repository_metadata` package (same file as
`Repository`/`SourceFile`/`Symbol`, per the request); the code that maps those
rows to `chat.models.ChatSession`/`ChatMessage` lives in a new module inside
the `chat` package rather than in `repository_metadata`, per the layering
rationale in research.md Decision 2.

## Complexity Tracking

No Constitution Check violations — this section is not applicable.

## Post-Design Constitution Check

*Re-evaluated after Phase 1 (data-model.md, contracts/, quickstart.md).*

All seven principles re-checked against the finalized design (two tables in
the existing `repository-metadata.sqlite`, no new endpoints, no new
dependency, mapping code kept inside `chat` to preserve the layer-dependency
direction): still **PASS**, unchanged from the pre-research check above. The
one design question the research phase resolved — where the row↔object
mapping code should live — was an internal-architecture choice (research.md
Decision 2), not a constitution gate; it does not change any of the seven
principle checks.
