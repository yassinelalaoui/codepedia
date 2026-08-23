---

description: "Task list template for feature implementation"
---

# Tasks: Chat Session Persistence

**Input**: Design documents from `/specs/025-chat-session-persistence/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included — this project's existing convention (every prior feature under `specs/`) is contract/unit/integration tests per package, and plan.md's Project Structure already names the test files this feature extends.

**Organization**: Tasks are grouped by user story (spec.md priorities: US1 = P1, US2 = P1, US3 = P2) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task names its exact file path(s)

## Path Conventions

Existing web-application layout, unchanged by this feature: `src/<package>/` for
each backend package (`repository_metadata`, `chat`, `chat_api`, `cli`),
`frontend/src/` and `frontend/tests/` for the wiki UI, `tests/{unit,contract,integration}/`
for backend tests (per plan.md's Project Structure).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Shared test scaffolding used by both the Foundational phase and every user story's tests below.

- [X] T001 [P] Add a temp-SQLite test helper (opens a fresh `repository-metadata.sqlite` under `tmp_path` via `repository_metadata.sqlite_store.connect`, returning its path) shared by chat-persistence unit/integration tests, in `tests/unit/_chat_persistence_support.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The durable storage layer every user story's independent test depends on — none of the three stories can be verified until this phase is complete.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Contract test asserting `chat.sqlite_store` exposes `create_session`, `touch_session`, `append_message`, `load_session`, `load_messages`, and that `repository_metadata.sqlite_store.SCHEMA_STATEMENTS` creates `chat_sessions`/`chat_messages` (per contracts/chat-persistence-interface.md and contracts/chat-persistence-schema.md), in `tests/contract/test_chat_persistence_interface.py` (new file) — write this first and confirm it fails
- [X] T003 [P] Add the `chat_sessions` and `chat_messages` table DDL plus the `idx_chat_messages_session_timestamp` index to `SCHEMA_STATEMENTS` in `src/repository_metadata/sqlite_store.py`, exactly as specified in `specs/025-chat-session-persistence/contracts/chat-persistence-schema.md`
- [X] T004 [P] Add `createdAt: str` and `lastActivityAt: str` fields (ISO-8601 UTC, defaulting to now, normalized in `__post_init__` like `ChatMessage.timestamp` already is) to `ChatSession` in `src/chat/models.py`, per research.md Decision 3
- [X] T005 Implement `src/chat/sqlite_store.py` (new file): `create_session`, `touch_session`, `append_message` (single-row insert with a per-session `sequence` counter and a generated synthetic row id — e.g. `uuid4().hex` — for `chat_messages.id`, since `ChatMessage` itself carries no `id` field; refreshes `chat_sessions.last_activity_at`), `load_session` (raises `KeyError` for an unknown id), `load_messages` (single query, ordered by `timestamp, sequence`) — building/reading `chat.models.ChatSession`/`ChatMessage` directly, reusing `repository_metadata.sqlite_store.connect()`. Depends on T003, T004.
- [X] T006 Update `ChatSession.ask()` in `src/chat/session.py` to persist the user message and the assistant message individually and immediately after each is appended to `self.messages`, via an optional `messageStore` collaborator set on the instance (per research.md Decision 4). Depends on T005.

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Conversation survives a server restart (Priority: P1) 🎯 MVP

**Goal**: A session created and given several exchanges is recoverable, identical and in order, after the server process fully stops and restarts; an unknown session id still 404s.

**Independent Test**: Create a session, exchange several question/answer pairs, stop and restart the server process, then fetch the session's history again — it matches the pre-restart history exactly, in the same order.

### Tests for User Story 1

- [X] T007 [P] [US1] Integration test: a session's history, fetched after simulating a full server restart (closing and reopening the SQLite connection between two `chat.sqlite_store` calls, per quickstart.md's "Automated coverage" note), matches the pre-restart history exactly in content and order; a never-created session id raises `SessionNotFoundError` rather than returning empty history — in `tests/integration/test_chat_session.py` (extend)
- [X] T008 [P] [US1] HTTP-level integration test (covering `contracts/chat-api-persistence-delta.md` end-to-end): using the existing `_chat_api_support.build_test_app` pattern, `POST /sessions` and exchange a few messages, then build a fresh `create_app(...)`/`SessionRegistry` instance pointed at the *same* metadata db path (simulating a restart) and confirm `GET /sessions/{id}/messages` on the same `sessionId` returns identical history over real HTTP requests; also confirm `GET` on a never-created `sessionId` still returns `404 session_not_found` — in `tests/integration/test_chat_api.py` (extend). Write this first — it will fail until T009/T010 land.

### Implementation for User Story 1

- [X] T009 [US1] Update `SessionRegistry` in `src/chat_api/session_store.py`: accept a metadata db path in its constructor; `create_session()` persists a `chat_sessions` row via `chat.sqlite_store.create_session` in addition to caching in memory; `get_session()` falls back to `chat.sqlite_store.load_session` + `load_messages` on an in-memory cache miss, reconstructing a `ChatSession` with the registry's `vectorIndex`/`embeddingEngine`/`llmEngine` and a `messageStore` re-attached, raising `SessionNotFoundError` only when the store also has no such id. Depends on T005, T006.
- [X] T010 [US1] Update `create_app()` in `src/chat_api/app.py` to accept the repository-metadata db path and pass it through to `SessionRegistry`. Depends on T009.
- [X] T011 [P] [US1] Add a `metadataDbPath: Path` field to `IndexRunResult` and populate it (via `paths.metadata_db_path(...)`) in both `run_index` in `src/cli/index_command.py` and `run_serve` in `src/cli/serve_command.py`
- [X] T012 [US1] Update `start_local_server()` in `src/cli/server.py` to accept a metadata db path parameter and pass it into `create_app()`. Depends on T010.
- [X] T013 [US1] Update both `start_local_server(...)` call sites in `src/cli/main.py` to pass `result.metadataDbPath`. Depends on T011, T012.
- [X] T014 [US1] Update the standalone entrypoint `main()` in `src/chat_api/server.py` to resolve and pass a distinctly-named repository-metadata db path (separate from its existing `--metadata-db`, which points at the *vector* index's SQLite file) into `create_app()`. Depends on T010.

**Checkpoint**: At this point, User Story 1 is fully functional and independently testable — a restarted server recovers full chat history, verified both at the `chat` package level and through real HTTP requests.

---

## Phase 4: User Story 2 - Conversation survives a wiki page reload (Priority: P1)

**Goal**: A reader who reloads the wiki page mid-conversation, with the server still running, sees their prior conversation restored instead of a blank chat panel.

**Independent Test**: Create a session, exchange messages, reload the wiki page while the server keeps running, and confirm the same conversation reappears without creating a new, empty session.

### Tests for User Story 2

- [X] T015 [P] [US2] Extend `frontend/tests/ChatPanel.test.tsx`: mounting `ChatPanel` with a session id already present in local storage resumes that session (a `GET` to fetch its history, no new `POST /sessions` call) and renders the restored messages; mounting with no stored id still creates a new session as before

### Implementation for User Story 2

- [X] T016 [US2] Update `frontend/src/components/ChatPanel.tsx`: persist the session id to the browser's local storage when a session is created; on mount, if a stored id exists, resume it via the existing `getHistory` client call (`frontend/src/lib/chatApiClient.ts`) and render the restored messages before falling back to creating a brand-new session only when no id is stored or the stored id no longer resolves. Depends on T015 (test-first), T009/T010 (backend session resume must already work).

**Checkpoint**: At this point, User Stories 1 AND 2 both work independently — restart and reload are both covered.

---

## Phase 5: User Story 3 - Each new message is saved without rewriting history (Priority: P2)

**Goal**: Verify the incremental-write property already built in the Foundational phase (T005/T006): appending one message never touches or requires rewriting previously stored messages, including under the same-timestamp and interrupted-write edge cases from spec.md.

**Independent Test**: Append messages to a session one at a time and confirm each append leaves all previously stored messages unchanged and retrievable, without the append operation scaling with session length.

### Tests for User Story 3

- [X] T017 [P] [US3] Unit tests for `chat.sqlite_store.append_message` in `tests/unit/test_chat_sqlite_store.py` (new file, using the T001 helper): two messages with an identical `timestamp` still come back in insertion order via the `sequence` tie-break; a message with empty `citedSymbolIds`/`citedFilePaths` round-trips as empty lists, not `null`/omitted; `load_messages` on a session with zero messages returns an empty tuple, not an error
- [X] T018 [US3] Integration test: appending N+1 messages to a session with N already-persisted messages leaves all N prior messages retrievable and byte-identical afterward (per FR-004/SC-003's acceptance scenarios), in `tests/integration/test_chat_session.py` (extend)
- [X] T019 [US3] Integration test: appending messages to a session grown to 500 prior messages (SC-003) does not measurably slow down per-append — compare append time near the start (e.g. message 5) and near the end (e.g. message 500) of the session and confirm they're comparable, since each append remains a single-row insert plus a single-row `chat_sessions` update rather than a function of session length — in `tests/integration/test_chat_session.py` (extend)

**Checkpoint**: All three user stories are independently functional — restart, reload, and incremental-write durability are all verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Keep the project's documentation set current with this implementation, per this repository's standing convention that `README.md`, `docs/architecture.md`, `docs/stack.md`, and `docs/diagrams/` are updated alongside the feature they document, not as an afterthought.

- [ ] T020 [P] Run through `specs/025-chat-session-persistence/quickstart.md` end-to-end against a real indexed repository and a real server restart, confirming every step's expected outcome
- [X] T021 [P] Update the "Storage architecture" section of `docs/architecture.md` (~lines 138-152) to list `chat_sessions`/`chat_messages` under `repository_metadata`'s entry, and note this as a deliberate exception to "one SQLite file per owning component" — extending an existing store's file rather than the owning package, mirroring the existing 018 precedent already described at ~lines 227-230 — with the rationale from research.md Decision 1/2
- [X] T022 [P] Update `docs/diagrams/sequence-diagrams/03-chat-rag.md`'s Mermaid sequence diagram to show each `ChatMessage` being persisted (a step from `ChatSession` to a "Chat Persistence (025)" participant) as it's appended, alongside the existing RAG flow
- [X] T023 [P] Update the chat bullet in README.md's "What it does" section to note that conversations persist across server restarts and wiki page reloads

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001, used by T002's contract test) — BLOCKS all user stories.
- **User Stories (Phase 3-5)**: All depend on Foundational (Phase 2) completion.
  - US1 and US2 are both P1 and independent of each other; US3 (P2) exercises write behavior that US1's implementation (T005/T006) already provides.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2). No dependency on US2/US3.
- **User Story 2 (P1)**: Can start after Foundational (Phase 2); T016 additionally depends on US1's T009/T010 (the backend session-resume fallback US2's frontend change relies on).
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) — its tests exercise code already built there; no new production code is required for US3 itself.

### Within Each User Story

- Tests are written first and confirmed to fail before the corresponding implementation task.
- Backend session-store changes (US1) before the frontend resume change that depends on them (US2).
- Story complete and checkpointed before moving to the next priority.

### Parallel Opportunities

- T002, T003, T004 (Foundational) can run in parallel — different files, no dependencies among them.
- T007, T008, T011 (US1) can run in parallel with each other once Foundational is done — independent files, none of them depends on the `SessionRegistry`/`create_app` chain (T009 → T010 → T012 → T013/T014).
- T015 (US2 test) can run in parallel with any remaining US1 task.
- T017 (US3 unit tests) can run in parallel with T007/T008/T011.
- All of Phase 6 (T020-T023) can run in parallel — four independent files.

---

## Parallel Example: Foundational Phase

```bash
# Launch the contract test and the two independent schema/model changes together:
Task: "Contract test for chat.sqlite_store + chat_sessions/chat_messages DDL in tests/contract/test_chat_persistence_interface.py"
Task: "Add chat_sessions/chat_messages DDL + index to src/repository_metadata/sqlite_store.py"
Task: "Add createdAt/lastActivityAt fields to ChatSession in src/chat/models.py"
```

## Parallel Example: User Story 1

```bash
# Launch both restart-focused tests and the CLI wiring task together (backend
# session-store change T009 is the one thing on the critical path for
# T010/T012/T013/T014, so those stay sequential):
Task: "Integration test: session history survives a simulated restart in tests/integration/test_chat_session.py"
Task: "HTTP-level integration test: POST/GET session history survives a simulated restart in tests/integration/test_chat_api.py"
Task: "Add IndexRunResult.metadataDbPath in src/cli/index_command.py and src/cli/serve_command.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001).
2. Complete Phase 2: Foundational (T002-T006) — CRITICAL, blocks all stories.
3. Complete Phase 3: User Story 1 (T007-T014).
4. **STOP and VALIDATE**: run the restart scenario from quickstart.md by hand.
5. This alone delivers spec.md's core pain point: a server restart no longer discards conversation history.

### Incremental Delivery

1. Setup + Foundational → durable storage exists but nothing calls it yet.
2. Add User Story 1 → restart survives → MVP.
3. Add User Story 2 → reload survives too (small, frontend-only addition on top of US1's backend work).
4. Add User Story 3 → the incremental-write property is verified with tests (no new production code expected).
5. Polish → docs stay in sync with the shipped behavior.

### Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps each task to its user story for traceability.
- Commit after each task or logical group.
- Stop at any checkpoint to validate a story independently before moving on.
