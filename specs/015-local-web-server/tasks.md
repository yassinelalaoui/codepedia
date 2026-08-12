# Tasks: Local Web Server

## Phase 1: Setup

**Goal:** Add the `--docs-root` CLI argument surface the rest of this feature wires up.

**Independent test criteria:** `chat_api.server.parse_args([...])` accepts and stores a `--docs-root` value.

- [X] T001 XPLACEHOLDERAdd a `--docs-root` argument to `build_arg_parser()` in `src/chat_api/server.py` (path to the `doc_generator` output directory to serve as the wiki), per `plan.md` Project Structure. Argument surface only — not yet wired into `create_app(...)`.

## Phase 2: Foundational

**Goal:** Extend `create_app(...)` to mount the wiki as static files, with the routing precedence and non-blocking missing-wiki diagnostic the rest of the feature depends on.

**Independent test criteria:** `create_app(..., docs_root=...)` returns an app where the existing chat routes still resolve, and any other path is resolved against `docs_root` (200 for a real file, 404 otherwise), even when `docs_root` does not exist.

- [X] T002 XPLACEHOLDERExtend `create_app(...)` in `src/chat_api/app.py` to accept a new `docs_root: Path` parameter; after the existing chat routes (`/sessions`, `/sessions/{session_id}/messages`) are registered, mount `StaticFiles(directory=docs_root, html=True, check_dir=False)` at `/` via `app.mount("/", ...)`, per `research.md` Decision 2.
- [X] T003 XPLACEHOLDERIn `create_app(...)`, check whether `docs_root / "index.html"` exists at call time and print a clear diagnostic to stdout if not (e.g. "No documentation wiki found at {docs_root}; run the documentation generator first."), without raising, per `research.md` Decision 3 and Decision 4. Depends on T002.
- [X] T004 XPLACEHOLDERWire the `--docs-root` CLI value into `create_app(...)` inside `main()` in `src/chat_api/server.py`, converting it to a `Path` the same way `--repo` already is. Depends on T001, T002.

**Checkpoint**: Foundation ready - user story implementation can now begin.

## Phase 3: User Story 1 - Browse the generated wiki from a browser

**Goal:** Serve a real generated wiki's pages and static resources correctly through the combined server.

**Independent test criteria:** With a real `doc_generator`-produced `docs_root`, `GET /` returns the home page, `GET /modules/{slug}.html` and `GET /diagrams/{slug}.html` return the corresponding pages, and the diagram's static script asset is reachable — all through one `create_app(...)` instance.

- [X] T005 [US1] Add an integration test in `tests/integration/test_local_web_server.py` (new file) that builds a real wiki via `doc_generator.DocGenerator.generateRepositoryDocumentation` (reusing `tests/integration/_doc_generator_support.build_indexed_repo` the same way `tests/integration/test_mermaid_diagram.py` does) into a `docs_root`, builds the app via `chat_api.app.create_app(vector_index=..., embedding_engine=..., llm_engine=..., docs_root=docs_root)`, and asserts `GET /` returns `200` and contains the wiki's home page content, and `GET /modules/{slug}.html` for a real generated module returns `200` and contains that module's content, per `contracts/wiki-serving.md`. Additionally, parse a real `href` out of the home page's returned HTML (e.g. via a simple regex for `href="([^"]+\.html)"`) and assert requesting that exact href through the same client also returns `200` — verifying an actual in-wiki link resolves end-to-end through the server (not just a known path requested directly), closing the G2 gap from `/speckit-analyze`.
- [X] T006 [US1] Extend the same test file to assert `GET /diagrams/{slug}.html` for that module returns `200` and contains its diagram content, and `GET /assets/mermaid.min.js` returns `200` with non-empty content, confirming a diagram page's static asset loads through the server. Depends on T005.
- [X] T007 [US1] Add an integration test in `tests/integration/test_local_web_server.py` asserting a request for a wiki path with no corresponding file (e.g. `GET /modules/does-not-exist.html`) returns a standard `404`, per `contracts/wiki-serving.md` and `spec.md` Edge Cases. Depends on T005.

**Checkpoint**: At this point, the wiki is fully browsable through the server, independently of the chat API (US2) or the local-only guarantee (US3).

## Phase 4: User Story 2 - Ask questions through the same local address

**Goal:** Confirm the chat API remains fully reachable, unshadowed, on the same app instance that now also serves the wiki.

**Independent test criteria:** On an app built with a `docs_root` mount, `POST /sessions`, `POST /sessions/{sessionId}/messages`, and `GET /sessions/{sessionId}/messages` all behave exactly as `specs/014-local-chat-api/contracts/chat-api.md` defines.

- [X] T008 [US2] Add an integration test in `tests/integration/test_local_web_server.py` that builds the app with both a real `docs_root` mount and fake chat engines (reusing `tests/integration/_chat_api_support.py`'s `FakeEmbeddingEngine`/`FakeLLMEngine`/pattern), then repeats `tests/integration/test_chat_api.py`'s create-session → ask-question → read-history flow against that same app, asserting identical status codes and response shapes, proving the wiki mount never shadows the chat routes (`contracts/wiki-serving.md` Routing precedence). Depends on T002.

**Checkpoint**: At this point, US1 and US2 both work on the same running app — browsing and chat are both reachable from one server.

## Phase 5: User Story 3 - Local-only access stays enforced by default

**Goal:** Confirm the combined server (wiki + chat API) still only accepts connections from the local machine by default.

**Independent test criteria:** A real running instance of the combined app accepts a request for a wiki page and a chat API response via `127.0.0.1`, and refuses a connection attempt via the machine's actual LAN address.

- [X] T009 [US3] Add an integration test in `tests/integration/test_local_web_server.py` that starts a real server instance of the combined app (built with a `docs_root` mount) via `uvicorn` in a background thread bound to `127.0.0.1` on an ephemeral port — reusing the `_RunningServer`/`_discover_local_lan_ip` helpers from `tests/integration/test_chat_api_network_boundary.py` — and asserts both a wiki page (`GET /`) and a chat API call (`POST /sessions`) succeed via `127.0.0.1`, while the same requests via the machine's LAN address are refused. Depends on T002.

**Checkpoint**: All three user stories are independently verified on the combined server.

## Phase 6: Polish & Cross-Cutting Concerns

**Goal:** Confirm the missing-wiki startup behavior, the CLI argument wiring, the startup address message, and the full quickstart flow all hold end to end.

**Independent test criteria:** The server starts and the chat API works even when `docs_root` does not exist, with wiki paths returning `404`; `--docs-root` is correctly parsed; a clear message states the wiki's local address at startup; the full quickstart passes.

- [X] T010 [P] Add an integration test in `tests/integration/test_local_web_server.py` building the app with a `docs_root` that does not exist on disk, asserting the app still constructs successfully, `GET /` returns `404` (not a crash), and a chat API call (`POST /sessions`) still succeeds, per `research.md` Decision 3/4 and `spec.md` Edge Cases ("server started before wiki generated"). Depends on T002, T003.
- [X] T011 [P] Add a unit test in `tests/unit/test_chat_api_server.py` asserting `parse_args([..., "--docs-root", "some/path"])` stores the given value, per T001.
- [X] T012 Validate the end-to-end flow against `specs/015-local-web-server/quickstart.md` (browse the wiki through the server, chat API reachable at the same address, server starts before the wiki exists, local-only bind default) and fix any mismatches across `src/chat_api/`. Depends on T006, T007, T008, T009, T010, T011, T013.
- [X] T013 [P] Add a `_startup_message(host: str, port: int) -> str` helper in `src/chat_api/server.py` returning a clear message (e.g. `"Documentation wiki available at http://{host}:{port}/"`), call `print(_startup_message(args.host, args.port))` in `main()` before invoking `uvicorn.run(...)`, and add a unit test in `tests/unit/test_chat_api_server.py` asserting `_startup_message(...)` produces the expected address string for a given host/port — implementing and verifying `spec.md`'s "MUST clearly indicate the local address at which the wiki is reachable" requirement, closing the G1 gap from `/speckit-analyze` (previously unimplemented and unverified, relying only on uvicorn's own generic startup banner).

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: `T002`/`T003` do not depend on Setup's `T001`; only `T004` (CLI wiring) does. Foundational as a whole BLOCKS all user stories.
- **User Stories (Phase 3-5)**: All depend on Foundational (`T002`) completion; can then proceed in parallel or in priority order (US1 → US2 → US3).
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Task-Level Dependencies

- `T001` has no dependencies and can start immediately.
- `T002` has no dependencies and can start immediately (in parallel with `T001` — different files).
- `T003` depends on `T002`.
- `T004` depends on `T001` and `T002`.
- `T005` depends on `T002`. `T006` and `T007` depend on `T005` (same test file, built incrementally).
- `T008` depends on `T002`.
- `T009` depends on `T002`.
- `T010` depends on `T002` and `T003`. `T011` depends on `T001`.
- `T013` depends on `T004` (`main()` must already exist to be extended); it does not depend on `T010`/`T011` and can be written in parallel with them.
- `T012` is a final validation after `T006`, `T007`, `T008`, `T009`, `T010`, `T011`, `T013`.

### Parallel Opportunities

- `T001`/`T002` (Setup vs. Foundational — different files, no dependency between them).
- Once `T002` lands, `T005` (US1), `T008` (US2), and `T009` (US3) can all start in parallel (different test functions, though they land in the same new test file so merge coordination is needed).
- `T010`/`T011`/`T013` (Polish, different files, no dependencies on each other beyond their own prerequisites).

## Parallel Execution Examples

### Early (before Foundational's T003/T004)

```text
Task: T001 -> add --docs-root argument in src/chat_api/server.py
Task: T002 -> mount StaticFiles in create_app in src/chat_api/app.py
```

### After Foundational completes

```text
Task: T005 -> wiki-serving test in tests/integration/test_local_web_server.py
Task: T008 -> chat-API-still-works test in tests/integration/test_local_web_server.py
Task: T009 -> local-only-bind test in tests/integration/test_local_web_server.py
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories).
3. Complete Phase 3: User Story 1 - the wiki is browsable through the server.
4. **STOP and VALIDATE**: `GET /` and a module/diagram page all render correctly through `create_app(...)`.

### Incremental Delivery

1. Setup + Foundational → the static mount, routing precedence, and missing-wiki diagnostic all exist.
2. Add US1 (browse the wiki) → test independently → MVP.
3. Add US2 (chat API still reachable) → test independently — this is a regression guard proving 014's behavior survives the new mount unchanged.
4. Add US3 (local-only access) → test independently — the same guarantee as regression guard, this time for 014's bind default.
5. Polish: lock in the missing-wiki startup behavior, the CLI argument, the startup address message, and a full quickstart pass.
