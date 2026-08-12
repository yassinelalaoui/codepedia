# Tasks: Local Chat API

## Phase 1: Setup

**Goal:** Establish the new `chat_api` package and its dependencies so the feature has somewhere to live.

**Independent test criteria:** `import chat_api` succeeds and `fastapi`/`uvicorn` are installed as project dependencies.

- [X] T001 Add `fastapi` and `uvicorn` to the `dependencies` list in `pyproject.toml`, per `plan.md` Technical Context.
- [X] T002 [P] Create the `src/chat_api/` package skeleton (`src/chat_api/__init__.py`), per `plan.md` Project Structure.

## Phase 2: Foundational

**Goal:** Build the shared schemas, session registry, error mapping, app factory, and server entrypoint every user story depends on.

**Independent test criteria:** `chat_api.app.create_app(...)` returns a working FastAPI app (no routes yet) with `chat.LocalDependencyUnavailableError`, an unknown session id, and an empty question all mapping to distinct structured error responses when exercised directly against the registered handlers.

- [X] T003 [P] Create `src/chat_api/schemas.py` with the Pydantic models `CreateSessionResponse`, `AskQuestionRequest`, `AskQuestionResponse`, `ChatMessageView`, `SessionHistoryResponse`, and `ApiErrorResponse` per `data-model.md`, with `AskQuestionRequest.question` rejecting empty/whitespace-only values (per `research.md` Decision 6).
- [X] T004 [P] Create `src/chat_api/session_store.py` with a `SessionRegistry` class per `data-model.md`: `create_session()` generates a session id via `uuid.uuid4().hex` (per `research.md` Decision 4) and stores a new `chat.ChatSession` sharing one injected `VectorIndex`/`EmbeddingEngine`/`LocalLLMEngine` (per `research.md` Decision 5); `get_session(session_id)` raises a new `SessionNotFoundError` when the id is absent.
- [X] T005 Create `src/chat_api/errors.py` registering FastAPI exception handlers that map `chat.LocalDependencyUnavailableError` to `503` (`code: "local_dependency_unavailable"`), `chat_api.session_store.SessionNotFoundError` to `404` (`code: "session_not_found"`), and a `RequestValidationError` on an empty `question` to `422` (`code: "empty_question"`), each returning an `ApiErrorResponse` body (T003), per `research.md` Decision 6 and `contracts/chat-api.md`. Depends on T003, T004.
- [X] T006 Create `src/chat_api/app.py` with a `create_app(vector_index, embedding_engine, llm_engine)` FastAPI factory that constructs one `SessionRegistry` (T004), stores it on `app.state`, and registers the exception handlers from `errors.py` (T005). Depends on T004, T005.
- [X] T007 [P] Create `src/chat_api/server.py`: a CLI entrypoint that constructs the shared `VectorIndex`, `EmbeddingEngine` (via `embedding_engine.create_embedding_engine`), and `LocalLLMEngine` (via `local_llm.create_local_llm_engine`), calls `create_app(...)` (T006), and runs it with `uvicorn.run(..., host="127.0.0.1")` by default, requiring an explicit `--host` CLI argument to bind elsewhere, per `research.md` Decision 2. Depends on T006.

**Checkpoint**: Foundation ready - user story implementation can now begin.

## Phase 3: User Story 1 - Start a chat session

**Goal:** Let a client create a new chat session and receive a unique identifier for it.

**Independent test criteria:** `POST /sessions` returns `201` with a `sessionId`, and two consecutive calls return distinct ids.

- [X] T008 [US1] Implement `POST /sessions` in `src/chat_api/app.py`, calling `SessionRegistry.create_session()` (T004) and returning a `201` `CreateSessionResponse` (T003), per `contracts/chat-api.md`. Depends on T006.
- [X] T009 [US1] Add an integration test in `tests/integration/test_chat_api.py` (new file) verifying `POST /sessions` returns `201` with a `sessionId` field, and that two consecutive calls return distinct ids. Depends on T008.

**Checkpoint**: At this point, a client can create sessions independently of asking questions (US2) or reading history (US3).

## Phase 4: User Story 2 - Ask a question and receive a structured, cited answer

**Goal:** Let a client submit a question to an existing session and get back the generated answer plus its structured citations.

**Independent test criteria:** `POST /sessions/{sessionId}/messages` returns `200` with `answer`/`citedSymbolIds`/`citedFilePaths` on success, and returns `404`/`422`/`503` (never a fabricated answer) for an unknown session, an empty question, or an unavailable local model, respectively, without mutating the session's history on any of those three failure paths.

- [X] T010 [US2] Implement `POST /sessions/{sessionId}/messages` in `src/chat_api/app.py`: resolve the session via `SessionRegistry.get_session` (letting `SessionNotFoundError` propagate to the T005 404 handler), call `ChatSession.ask(question)` (letting `LocalDependencyUnavailableError` propagate to the T005 503 handler), and return a `200` `AskQuestionResponse` built from the returned `ChatMessage`'s `content`/`citedSymbolIds`/`citedFilePaths`, per `contracts/chat-api.md`. Depends on T006, T004.
- [X] T011 [US2] Add an integration test in `tests/integration/test_chat_api.py` verifying a full ask flow returns `200` with the generated `answer`, `citedSymbolIds`, and `citedFilePaths`, using fake embedding/LLM engines equivalent to `FakeEmbeddingEngine`/`FakeLLMEngine` from `tests/integration/test_chat_session.py`, and asserting no outbound network request occurs (reusing that test's `urlopen`-blocking pattern). Depends on T010.
- [X] T012 [US2] Add integration tests in `tests/integration/test_chat_api.py` verifying `404` for an unknown `sessionId`, `422` for an empty/whitespace-only question, and `503` with `code: "local_dependency_unavailable"` when the fake LLM/embedding engine reports itself unavailable — and, for every one of those three failure cases, that the targeted session's `messages` list (inspected directly via the app's `SessionRegistry` on `app.state`, not through the history endpoint) is unchanged, per `spec.md` Edge Cases. Depends on T010.

**Checkpoint**: At this point, US1 and US2 both work independently — a client can create a session and ask it a question.

## Phase 5: User Story 3 - Review a session's message history

**Goal:** Let a client retrieve the ordered message history of a session, including citations.

**Independent test criteria:** `GET /sessions/{sessionId}/messages` returns `200` with an empty list for an unused session, `404` for an unknown session, and, after questions have been asked, the messages in the order they occurred with matching citations.

- [X] T013 [US3] Implement `GET /sessions/{sessionId}/messages` in `src/chat_api/app.py`: resolve the session via `SessionRegistry.get_session` (404 on unknown id), map its `messages` to `ChatMessageView` entries preserving order, and return a `200` `SessionHistoryResponse`, per `contracts/chat-api.md`. Depends on T006, T004.
- [X] T014 [US3] Add an integration test in `tests/integration/test_chat_api.py` verifying a freshly created session returns `200` with an empty `messages` list, and an unknown `sessionId` returns `404`. Depends on T013.
- [X] T015 [US3] Add an integration test in `tests/integration/test_chat_api.py` that creates a session, asks a question, then reads history, and asserts the returned `messages` contain the user question followed by the assistant answer in order, with the assistant message's `citedSymbolIds`/`citedFilePaths` matching the ask response. Depends on T013, T010.

**Checkpoint**: All three user stories are independently functional; a client can create a session, ask it questions, and read its history back.

## Phase 6: Polish & Cross-Cutting Concerns

**Goal:** Confirm the local-only network default, the error-mapping contract, and the full quickstart flow all hold end to end.

**Independent test criteria:** The server's default configuration never binds beyond `127.0.0.1`, and a real instance started with that default only accepts connections on `127.0.0.1`, not the machine's LAN-visible address; every error-mapping case in `contracts/chat-api.md` is covered by a direct unit test; the full quickstart passes.

- [X] T016 [P] Add a unit test in `tests/unit/test_chat_api_server.py` asserting `chat_api.server`'s uvicorn configuration binds `host="127.0.0.1"` when no `--host` is supplied, and honors an explicit `--host` override, without starting a real server, per `research.md` Decision 2.
- [X] T017 [P] Add a unit test in `tests/unit/test_chat_api_errors.py` directly exercising `errors.py`'s exception-to-response mapping for all three error cases (`LocalDependencyUnavailableError` → 503/`local_dependency_unavailable`, `SessionNotFoundError` → 404/`session_not_found`, empty question → 422/`empty_question`), per `data-model.md` `ApiErrorResponse`.
- [X] T018 Validate the end-to-end flow against `specs/014-local-chat-api/quickstart.md` (local-only default binding, create→ask→history flow, empty history, explicit 503 on local-dependency failure, no outbound network requests) and fix any mismatches across `src/chat_api/`. Depends on T009, T011, T012, T014, T015, T016.
- [X] T019 [P] Add an integration test in `tests/integration/test_chat_api_network_boundary.py` (new file) that starts the real `chat_api` app via `uvicorn` in a background thread with the default configuration (no `--host`), on an ephemeral port, and asserts: a client can connect and receive a response via `127.0.0.1`, and a connection attempt to the same port via the machine's actual non-loopback LAN address is refused. This directly automates `spec.md`'s "an attempt to reach the API from outside the local machine or local network fails to connect by default" success criterion, closing the E1 gap identified in `/speckit-analyze` (previously validated only manually via quickstart). Depends on T006, T007.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories.
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion; can then proceed in parallel or in priority order (US1 → US2 → US3).
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Task-Level Dependencies

- `T001` and `T002` have no dependencies and can run in parallel.
- `T003` and `T004` have no dependencies on each other (`schemas.py` and `session_store.py` do not import one another) and can be written in parallel once T002 completes.
- `T005` depends on `T003` (uses `ApiErrorResponse`) and `T004` (uses `SessionNotFoundError`).
- `T006` depends on `T004` (constructs a `SessionRegistry`) and `T005` (registers its handlers).
- `T007` depends on `T006`.
- `T008`, `T010`, `T013` each depend on `T006` and `T004`, and can be implemented in parallel by different developers once Foundational is complete (they add independent routes to the same `app.py`, so merge coordination is needed even though the tasks themselves have no logical dependency on each other).
- `T009` depends on `T008`; `T011` and `T012` depend on `T010`; `T014` depends on `T013`; `T015` depends on `T013` and `T010`.
- `T016` depends on `T007`. `T017` depends on `T005`.
- `T018` is a final validation after every endpoint and its tests exist (`T009`, `T011`, `T012`, `T014`, `T015`, `T016`).
- `T019` depends on `T006` and `T007` (needs the real app factory and server entrypoint to start a live instance); it does not depend on `T016` even though both cover network binding — `T016` checks the uvicorn *configuration* in isolation, `T019` checks the *actual accept behavior* of a running instance, so they can be written in parallel.

### Parallel Opportunities

- `T001`/`T002` (Setup).
- `T003`/`T004` (Foundational schemas vs. session registry).
- `T007` (server entrypoint) can proceed in parallel with `T008`/`T010`/`T013` (route implementations) once `T006` is done, since none of them import `server.py`.
- `T016`/`T017`/`T019` (Polish tests, different files, no dependencies on each other).

## Parallel Execution Examples

### Foundational

```text
Task: T003 -> create Pydantic schemas in src/chat_api/schemas.py
Task: T004 -> create SessionRegistry in src/chat_api/session_store.py
```

### After Foundational completes

```text
Task: T008 -> implement POST /sessions in src/chat_api/app.py
Task: T010 -> implement POST /sessions/{sessionId}/messages in src/chat_api/app.py
Task: T013 -> implement GET /sessions/{sessionId}/messages in src/chat_api/app.py
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories).
3. Complete Phase 3: User Story 1 - a client can create a session.
4. **STOP and VALIDATE**: `POST /sessions` works end to end against the real FastAPI app.

### Incremental Delivery

1. Setup + Foundational → the app factory, registry, schemas, and error mapping all exist.
2. Add US1 (create session) → test independently → MVP.
3. Add US2 (ask a question, get a cited answer) → test independently — this is the feature's core value and explicit success criterion.
4. Add US3 (read history) → test independently — completes the three operations the spec requires.
5. Polish: lock in the local-only bind default (both its configuration and its actual accept behavior), the full error-mapping contract, and a full quickstart pass.
