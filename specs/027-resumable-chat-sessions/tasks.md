---

description: "Task list template for feature implementation"
---

# Tasks: Resumable Chat Sessions via Streaming, Listing & History

**Input**: Design documents from `/specs/027-resumable-chat-sessions/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included — this project's existing convention (every prior feature under `specs/`) is contract/unit/integration tests per package, and plan.md's Project Structure already names the test files this feature extends or adds. Frontend tests use the existing Vitest + Testing Library setup (`frontend/tests/`).

**Organization**: Tasks are grouped by user story (spec.md priorities: US1 = P1, US2 = P2, US3 = P3) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task names its exact file path(s)

## Path Conventions

Existing web-application layout, unchanged by this feature: `src/chat/`,
`src/chat_api/` for backend packages, `tests/{unit,contract,integration}/`
for backend tests, `frontend/src/` and `frontend/tests/` for the bundled UI
(per plan.md's Project Structure). No new dependency, no schema/migration,
no new top-level directory.

---

## Phase 1: Setup

**Purpose**: Nothing new to install or scaffold — every dependency and
directory this feature needs already exists (research.md Decision 5).

- [X] T001 Confirm `pytest-asyncio` (already added in spec 026) and Vitest (already configured) run cleanly on a clean checkout of this branch — no changes expected, this is a sanity check only, not a task that edits any file.

**Checkpoint**: No foundation work required beyond Phase 1's sanity check — proceed straight to Phase 2.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The one new read path (`list_sessions`) every other backend
piece of US1 builds on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Contract test: add `list_sessions` coverage to `tests/contract/test_chat_persistence_interface.py` — asserts the persistence module exposes a `list_sessions(db_path)` callable returning `ChatSession` instances (empty `messages`), per `contracts/chat-api-session-listing-delta.md` and `data-model.md`. Write first, confirm it fails.
- [X] T003 [P] Unit test: add ordering/persistence coverage to `tests/unit/test_chat_sqlite_store.py` — sessions with different `last_activity_at` values come back ordered most-recent-first; a session with no messages yet is still included; an empty database returns `()`. Write first, confirm it fails.
- [X] T004 Implement `list_sessions(db_path: str | Path) -> tuple[ChatSession, ...]` in `src/chat/sqlite_store.py` — `SELECT id, created_at, last_activity_at FROM chat_sessions ORDER BY last_activity_at DESC`, mapping each row the same way `load_session` already does (empty `messages`). Depends on T002, T003 (tests must fail first).

**Checkpoint**: Foundation ready — `chat.sqlite_store.list_sessions` is available and tested; user story implementation can now begin.

---

## Phase 3: User Story 1 - Rediscover and resume a conversation after reconnecting (Priority: P1) 🎯 MVP

**Goal**: A client with no remembered session id can list every existing
session (surviving a server restart) and pull back any one of them's
complete, correctly ordered history.

**Independent Test**: With sessions already containing prior messages,
call `GET /sessions` (no session id known ahead of time), confirm every
session appears with enough info to pick one, then call
`GET /sessions/{id}/messages` for the chosen id and confirm it matches
exactly what was actually asked/answered.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T005 [P] [US1] Contract test for `GET /sessions` in `tests/integration/test_chat_api.py` — response shape (`SessionListResponse`/`SessionSummary`), ordering by `lastActivityAt` descending, empty list when no sessions exist, per `contracts/chat-api-session-listing-delta.md`.
- [X] T006 [P] [US1] Integration test in new `tests/integration/test_session_registry.py` — `SessionRegistry.list_sessions()` returns every persisted session even when the in-memory cache is empty (simulating a fresh process after restart), matching `chat.sqlite_store.list_sessions`; also covers ordering and the in-memory-only fallback (no `metadata_db_path`).
- [X] T007 [P] [US1] Extend the existing restart-simulation test `test_session_history_survives_a_simulated_restart_via_http` in `tests/integration/test_chat_api.py` (builds two `build_test_app()`/`TestClient` instances against the same `metadata_db_path` — reuse that exact pattern rather than writing a new harness) with a `GET /sessions` assertion: after the simulated restart, the session still appears in the list with its original `createdAt` and updated `lastActivityAt` (spec.md Acceptance Scenarios 1.1, 1.2, 1.5).

### Implementation for User Story 1

- [X] T008 [US1] Add `SessionSummary` and `SessionListResponse` pydantic models to `src/chat_api/schemas.py`, per `data-model.md`. Depends on tests T005–T007 failing first.
- [X] T009 [US1] Add `SessionRegistry.list_sessions()` to `src/chat_api/session_store.py` — when `metadata_db_path` is set, reads directly from `chat.sqlite_store.list_sessions` (not the in-memory cache alone), so a session from a previous process is included; when `metadata_db_path` is `None` (in-memory-only mode), falls back to the in-memory cache sorted by `lastActivityAt` descending, mirroring `get_session`'s existing cache-as-authoritative behavior in that mode. Depends on T004, T008.
- [X] T010 [US1] Add the `GET /sessions` route to `src/chat_api/app.py`, returning `SessionListResponse` built from `SessionRegistry.list_sessions()`. Depends on T009.

**Checkpoint**: At this point, User Story 1 is fully functional and testable independently — a client can discover and resume any persisted session without knowing its id ahead of time.

---

## Phase 4: User Story 2 - Watch the answer arrive as it's generated (Priority: P2)

**Goal**: The bundled chat UI actually displays the answer progressively,
using the SSE stream `POST /sessions/{id}/messages` has returned since
spec 026 — closing the gap research.md Decision 4 identified (the client
currently calls `response.json()` on that stream, which throws in a real
browser).

**Independent Test**: Ask a question through the bundled UI (or any client
using the updated `chatApiClient.ts`) and confirm the answer visibly builds
up fragment-by-fragment rather than appearing all at once, with the final
displayed text and citations matching what `done`'s payload contains.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T011 [P] [US2] New test file `frontend/tests/chatApiClient.test.ts` — mocks `fetch` to return a real SSE-formatted body (`data: {"fragment": "..."}\n\n` lines followed by `event: done\ndata: {...}\n\n`) and asserts `askQuestion()`: (a) invokes the `onFragment` callback once per fragment, in order, with the right text; (b) resolves with an `AskQuestionResponse` whose `answer` equals every fragment concatenated; (c) rejects with `ChatApiError` on a terminal `event: error`. Per `contracts/chat-client-streaming-delta.md`.
- [X] T012 [P] [US2] New test in `frontend/tests/chatApiClient.test.ts` — `listSessions()` performs a plain `GET /sessions` and resolves with the parsed `SessionListResponse`.
- [X] T013 [P] [US2] Update `frontend/tests/ChatPanel.test.tsx`'s `fetch` mock for the ask-a-question flow to return a real SSE body (replacing today's plain-JSON mock, which is why this gap went undetected) and assert the assistant message's content grows across fragments before the final citations are attached.

### Implementation for User Story 2

- [X] T014 [US2] Rewrite `askQuestion()` in `frontend/src/lib/chatApiClient.ts` to read the `fetch` response body as a `ReadableStream`, parse SSE `fragment`/`done`/`error` events, invoke a new `onFragment` callback per fragment, and resolve/reject exactly as `contracts/chat-client-streaming-delta.md` specifies. Depends on T011 failing first.
- [X] T015 [P] [US2] Add `listSessions(): Promise<SessionListResponse>` to `frontend/src/lib/chatApiClient.ts`, using the existing `request()` JSON helper against `GET /sessions`. Depends on T010 (backend route must exist), T012 failing first.
- [X] T016 [US2] Update `frontend/src/components/ChatPanel.tsx`'s `handleSubmit` to pass an `onFragment` callback to `askQuestion()` that appends to an in-progress assistant message in `messages` state, attaching citations only once the call resolves. Depends on T014, T013 failing first.

**Checkpoint**: At this point, User Stories 1 AND 2 both work independently — sessions are discoverable/resumable, and the bundled UI actually shows progressive delivery instead of throwing.

---

## Phase 5: User Story 3 - New capabilities stay as local-only as the rest of the API (Priority: P3)

**Goal**: Confirm the new `GET /sessions` route inherits the existing
local-only binding with no separate exposure configuration.

**Independent Test**: With the API under its default configuration, confirm
`GET /sessions` succeeds from the local machine and is unreachable from
outside it, identically to the existing routes.

### Tests for User Story 3

- [X] T017 [US3] Extend `test_combined_server_accepts_on_loopback_but_refuses_on_lan_interface` in `tests/integration/test_local_web_server.py:147` to also call `GET /sessions` — same binding behavior, no new configuration path introduced. Write first, confirm it fails only in the sense that the route doesn't exist yet if run before T010; otherwise this simply extends existing passing coverage to the new route.

### Implementation for User Story 3

- [X] T018 [US3] Verify (no code change expected): `GET /sessions` is registered on the same `FastAPI` app instance / same `uvicorn` binding as every other route in `src/chat_api/app.py` and `src/cli/serve_command.py` — no per-route host/port override exists anywhere in the new code from T010. If T017 fails for any reason other than "route doesn't exist yet," fix the binding here.

**Checkpoint**: All three user stories are independently functional. Full feature ready for polish.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and end-to-end validation across all three
stories.

- [X] T019 [P] Update `README.md`'s chat bullet and `docs/architecture.md`'s `chat_api` row to mention session listing, per this repo's "diagrams/docs updated alongside every implementation" maintenance convention.
- [X] T020 [P] Update `docs/diagrams/sequence-diagrams/03-chat-rag.md` to add the `GET /sessions` interaction (client → `ChatApiApp` → `ChatStore`) alongside the existing `ask`/history flows.
- [X] T021 Run all six scenarios in `quickstart.md` against a locally running server and the bundled UI in a real browser; fix any discrepancy found. This is the only validation for SC-002 (time-to-first-fragment stays flat, Scenario 4) and SC-005 (list+history round trip within 2 seconds, Scenario 3) — both are manually validated here rather than by an automated task: SC-002 because it re-confirms an already-tested 026 guarantee, SC-005 because a hard latency assertion isn't worth the flakiness risk in the automated suite at this feature's scale. Scenarios 1-5 verified against a real `uvicorn` socket (not `TestClient`). Scenario 6 verified with a real Chromium browser (Playwright, installed into an isolated scratchpad project, not added to the repo) driving the actual rebuilt `wiki-ui.js` bundle against a real generated wiki: a mid-stream screenshot shows a truncated in-progress answer, a later screenshot shows the complete one, zero console/page errors were captured (confirming the pre-existing `response.json()`-on-SSE bug is fixed), a page reload correctly resumed the conversation, and `GET /sessions` returned the real session from the browser's own origin.
- [X] T022 Run the full backend (`pytest`) and frontend (`vitest`) suites; confirm no regression beyond this feature's own new coverage. Backend: same 3 pre-existing, unrelated failures as the pre-implementation baseline (`test_parser_interface_returns_ast`, `test_multi_language_batch_includes_one_failure`, `test_batch_continues_after_failure`), zero new failures. Frontend: 16/16 passing (3 test files).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — a sanity check only.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS User Story 1 (and, transitively, US2's `listSessions()` client function needs T010, which needs Phase 2).
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2). No dependency on US2/US3.
- **User Story 2 (Phase 4)**: Independent of US1 for its core streaming-consumption fix (T011, T013, T014, T016 touch only the frontend's existing `POST /sessions/{id}/messages` path, already implemented since spec 026); only its `listSessions()` piece (T012, T015) depends on US1's T010.
- **User Story 3 (Phase 5)**: Depends on T010 (US1) existing, to have a route to verify.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — no dependency on US2/US3.
- **User Story 2 (P2)**: Its streaming-consumption fix (T011/T013/T014/T016) can start immediately after Setup, in parallel with US1 — it depends only on the already-existing `POST /sessions/{id}/messages` (spec 026), not on anything new in this feature. Its `listSessions()` piece (T012/T015) depends on US1's T010.
- **User Story 3 (P3)**: Depends on US1's T010 (needs the route to exist to verify its binding).

### Within Each User Story

- Tests MUST be written and FAIL before implementation.
- Backend: persistence (`sqlite_store`) before registry (`session_store`) before route (`app.py`).
- Frontend: client library (`chatApiClient.ts`) before the component that consumes it (`ChatPanel.tsx`).
- Story complete before moving to the next priority (though US2's streaming fix may be worked in parallel with US1, per above).

### Parallel Opportunities

- T002 and T003 (Phase 2 tests) in parallel.
- T005, T006, T007 (US1 tests) in parallel.
- T011, T012, T013 (US2 tests) in parallel.
- T015 in parallel with T014/T016 once its own dependency (T010) is met.
- US1 (Phase 3) and US2's streaming-fix tasks (T011, T013, T014, T016) can proceed in parallel by different contributors once Phase 2 is done, since they touch disjoint files (backend `chat_api`/`chat` vs. frontend `chatApiClient.ts`/`ChatPanel.tsx`) — only US2's `listSessions()` half (T012/T015) must wait on US1's T010.

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Contract test for GET /sessions in tests/integration/test_chat_api.py"
Task: "Integration test for SessionRegistry.list_sessions() cache-miss fallback in tests/integration/test_chat_session.py"
Task: "Integration test for end-to-end resume-after-restart in tests/integration/test_chat_api.py"
```

## Parallel Example: User Story 2

```bash
# Launch all tests for User Story 2 together:
Task: "SSE-parsing coverage for askQuestion() in frontend/tests/chatApiClient.test.ts"
Task: "listSessions() coverage in frontend/tests/chatApiClient.test.ts"
Task: "Progressive-rendering coverage in frontend/tests/ChatPanel.test.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (sanity check only).
2. Complete Phase 2: Foundational (`list_sessions` in `chat.sqlite_store`).
3. Complete Phase 3: User Story 1 (`GET /sessions` end-to-end).
4. **STOP and VALIDATE**: run Scenarios 1–3 of `quickstart.md` independently.
5. Deploy/demo if ready — a client can already discover and resume sessions, even before the UI streaming fix lands.

### Incremental Delivery

1. Complete Setup + Foundational → `list_sessions` ready.
2. Add User Story 1 → test independently → deploy/demo (MVP!) — session discovery/resume works via any HTTP client.
3. Add User Story 2 → test independently → deploy/demo — the bundled UI now shows progressive delivery instead of throwing.
4. Add User Story 3 → test independently → deploy/demo — local-only reachability confirmed for the new route.
5. Each story adds value without breaking previous stories (FR-009 holds throughout).

### Parallel Team Strategy

With multiple contributors:

1. Team completes Setup + Foundational together (small, one task).
2. Once Foundational is done:
   - Contributor A: User Story 1 (backend: `sqlite_store` → `session_store` → `app.py`)
   - Contributor B: User Story 2's streaming-consumption fix (frontend: `chatApiClient.ts` → `ChatPanel.tsx`), starting immediately since it doesn't depend on US1
3. Once US1's T010 lands, either contributor picks up US2's `listSessions()` half (T012/T015) and US3's verification (T017/T018).

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability.
- No task in this feature adds a dependency, a database table, or a migration (research.md Decision 5) — every implementation task is additive within an already-existing module.
- Verify tests fail before implementing.
- Commit after each task or logical group.
- Stop at any checkpoint to validate story independently.
