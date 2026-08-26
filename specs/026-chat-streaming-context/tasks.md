---

description: "Task list template for feature implementation"
---

# Tasks: Chat Streaming & Conversational Context Retrieval

**Input**: Design documents from `/specs/026-chat-streaming-context/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included — this project's existing convention (every prior feature under `specs/`) is contract/unit/integration tests per package, and plan.md's Project Structure already names the test files this feature extends or adds.

**Organization**: Tasks are grouped by user story (spec.md priorities: US1 = P1, US2 = P1, US3 = P2) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task names its exact file path(s)

## Path Conventions

Existing web-application layout, unchanged by this feature: `src/local_llm/`,
`src/chat/`, `src/chat_api/`, `src/cli/` for backend packages,
`tests/{unit,contract,integration}/` for backend tests (per plan.md's
Project Structure). No frontend changes.

---

## Phase 1: Setup

**Purpose**: The one piece of tooling every async task below needs.

- [X] T001 Add `pytest-asyncio` to `[project.optional-dependencies].test` in `pyproject.toml` (test-only dependency — research.md Decision 7)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared `LLMEngine` streaming interface and its local implementation — both US1 (local streaming) and US3 (`GroqLLMEngine` implementing the same interface) build directly on this.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Define the `LLMEngine` Protocol (`isAvailableLocally`, `checkAvailability`, `generate`, `generateStream`) in `src/local_llm/protocol.py`, per `contracts/llm-engine-interface.md`
- [X] T003 [P] Extend the contract test in `tests/contract/test_local_llm_engine_interface.py`: assert `LocalLLMEngine` exposes `generateStream` as an async-generator-producing callable, and that draining it and joining the fragments is what `generate()` now does internally — write this first and confirm it fails
- [X] T004 Add a streaming call to `src/local_llm/transport.py`'s `LocalLLMTransport`: an `httpx.AsyncClient`-based method that posts to Ollama's `/api/generate` with a `stream: true` payload variant (`PromptEnvelope.to_request_payload()` currently hard-codes `"stream": False` — build a separate payload for this call rather than reusing it unmodified) and yields each NDJSON line's `response` text as it arrives, until `"done": true`
- [X] T005 In `src/local_llm/engine.py`: add `LocalLLMEngine.generateStream` (async generator wrapping T004, with the same pre-flight `checkAvailability()` gate `generate()` already has); change `generate()` to a synchronous wrapper that drains `generateStream` via `asyncio.run(...)` and concatenates. Depends on T004.

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Progressive answer delivery instead of a silent wait (Priority: P1) 🎯 MVP

**Goal**: Chat answers stream to the caller fragment-by-fragment as they're generated, for the local engine, with the same complete answer/citations at the end as today's blocking response.

**Independent Test**: Ask a question the local model can answer via `POST /sessions/{id}/messages`; confirm fragments arrive over time (not one block), the first fragment arrives well before the last, and concatenating every fragment equals the final `done` event's answer.

### Tests for User Story 1

- [X] T006 [P] [US1] Unit tests in `tests/unit/test_local_llm.py` (extend): `LocalLLMEngine.generateStream` yields fragments in order against a fake/mocked streaming transport, and `generate()` (now a wrapper) returns their concatenation; monkeypatching `httpx.AsyncClient` (the new transport, replacing the old `urllib`-based `_blocked_urlopen` pattern which doesn't intercept `httpx` calls) to raise if a request targets anything other than the configured local endpoint, proving no stray host is ever reached; and, using a fake transport that yields fragments with a small artificial delay between them, that time-to-first-fragment is comparable for a short vs. a long fake response (SC-002 — structural analog of quickstart.md's manual timing check)
- [X] T007 [P] [US1] Integration test: `ChatSession.askStream()` yields fragments then a final `ChatMessage`; concatenated fragments equal the message's content; citations attach only to the final message; the user question is persisted immediately and the assistant message is persisted once, at completion, in `tests/integration/test_chat_session.py` (extend)
- [X] T008 [P] [US1] Integration test: `POST /sessions/{id}/messages` returns an SSE stream of `fragment` events followed by one `done` event whose fields match today's `AskQuestionResponse` shape, per `contracts/chat-streaming-api-delta.md`, in `tests/integration/test_chat_api.py` (extend)
- [X] T009 [US1] Integration test: a mid-stream generation failure ends the SSE stream with an `event: error` (same `{code, message}` shape as `ApiErrorResponse`) and leaves no assistant message in the session's history (FR-011), in `tests/integration/test_chat_api.py` (extend, same file as T008)

### Implementation for User Story 1

- [X] T010 [US1] In `src/chat/session.py`: replace `ChatSession.ask()` with `ChatSession.askStream()` — an async generator per `contracts/chat-retrieval-and-session-interface.md` (persist user message immediately; run existing evidence-sufficiency checks; stream fragments from `self.llmEngine.generateStream(envelope)`; on completion, assemble the answer, compute citations exactly as `ask()` did, persist the final `ChatMessage` via the existing `_persist()`, and yield it last; on a mid-stream exception, persist nothing and let it propagate). Depends on T005.
- [X] T011 [P] [US1] Add `fragment`/`done`/`error` SSE event payload shapes to `src/chat_api/schemas.py`, per `contracts/chat-streaming-api-delta.md` — the `done` event reuses `AskQuestionResponse`'s existing fields (`answer`/`citedSymbolIds`/`citedFilePaths`) directly rather than defining a parallel model; only `fragment` and `error` (reusing `ApiErrorResponse`'s `code`/`message`) are genuinely new shapes
- [X] T012 [US1] In `src/chat_api/app.py`: change the `POST /sessions/{session_id}/messages` route to `async def`, returning a `StreamingResponse` (`text/event-stream`) that consumes `session.askStream(...)`, emitting a `data:` line per fragment and a final `event: done`/`event: error` line per T011's shapes. Depends on T010, T011.

**Checkpoint**: User Story 1 is fully functional and independently testable — local-engine chat answers stream, with the same final content/citations as before.

---

## Phase 4: User Story 2 - Follow-up questions retrieve the right evidence (Priority: P1)

**Goal**: A session's recent conversation enriches the search query for a new question, so elliptical follow-ups retrieve evidence about their real subject instead of unrelated results.

**Independent Test**: Directly unit-test `build_enriched_query`/`retrieve_evidence(history=...)` with a fabricated conversation history — no streaming, no live model calls needed, since enrichment is pure local text/citation concatenation (research.md Decision 3).

### Tests for User Story 2

- [X] T013 [P] [US2] Unit tests in `tests/unit/test_chat_retrieval.py` (new file): empty `history` leaves the query unchanged (FR-007); non-empty `history` includes up to the configured `context_window` of recent user-question text and recent assistant `citedSymbolIds`/`citedFilePaths`; a self-contained new question (Acceptance Scenario 3) still surfaces its own subject as the dominant signal even with unrelated prior history present; `is_insufficient_evidence`/`detect_ambiguous_evidence` (unchanged functions) still correctly flag insufficient/ambiguous results when applied to evidence returned for an *enriched* query, not just a plain one (FR-009); and no `httpx` call is attempted anywhere in `build_enriched_query`/`retrieve_evidence` (enrichment stays local-only — FR-006/FR-010), monkeypatched to raise if invoked
- [X] T014 [P] [US2] Integration test in `tests/integration/test_chat_session.py` (extend): with a fake vector index seeded so only history-aware enrichment finds the right chunk, an elliptical follow-up (`"what about the other one?"`) after a prior exchange retrieves the evidence that exchange's answer actually cited, not unrelated chunks

### Implementation for User Story 2

- [X] T015 [US2] In `src/chat/retrieval.py`: add a `history: tuple[ChatMessage, ...] = ()` parameter and a `context_window` keyword to `retrieve_evidence`, plus a `build_enriched_query(question, history, *, context_window)` helper implementing the composition in `data-model.md` (current question + recent user questions + recent assistant citation data). Depends on T013 (test-first).
- [X] T016 [US2] In `src/chat/session.py`: update `ChatSession.askStream()` to call `retrieve_evidence(self.vectorIndex, question, history=tuple(self.messages), k=self.topK)`. Depends on T015, T010.

**Checkpoint**: User Stories 1 AND 2 both work independently — streaming and history-aware retrieval are both covered.

---

## Phase 5: User Story 3 - Choosing an explicit remote engine for chat answers (Priority: P2)

**Goal**: An operator can explicitly configure a remote (Groq) engine as an alternative to the local one — never on by default, never used as a silent fallback in either direction, with clear disclosure at configuration time.

**Independent Test**: With no remote engine configured, confirm chat is unchanged from US1/US2 behavior. Then configure one and confirm answers come from it (streamed, same as US1); confirm an unreachable configured remote engine reports unavailable rather than silently using the local model.

### Tests for User Story 3

- [X] T017 [P] [US3] Extend `tests/contract/test_local_llm_engine_interface.py`: assert `GroqLLMEngine` satisfies the same `LLMEngine` Protocol shape as `LocalLLMEngine` (`isAvailableLocally`, `checkAvailability`, `generate`, `generateStream`)
- [X] T018 [P] [US3] Unit tests in `tests/unit/test_groq_llm_engine.py` (new file): `GroqLLMEngine.generateStream` yields fragments parsed from a fake Groq SSE response; `generate()` concatenates them; `checkAvailability()` reports a clear message when `GROQ_API_KEY` is unset or the endpoint is unreachable
- [X] T019 [P] [US3] Unit tests in `tests/unit/test_local_llm.py` (extend): `create_llm_engine(config)` returns a `LocalLLMEngine` when `config.llmProvider == "local"` and a `GroqLLMEngine` when `"groq"`; it never returns a composite/fallback engine, and never consults the other provider regardless of availability (FR-014)
- [X] T020 [P] [US3] Extend `tests/contract/test_cli_interface.py`: `codepedia config --llm-provider groq --remote-llm-model <name>` saves the config and prints the required disclosure before doing so; omitting `--remote-llm-model` with `--llm-provider groq` is rejected; `--llm-provider local` reverts cleanly

### Implementation for User Story 3

- [X] T021 [P] [US3] Add a `RemoteLLMError` hierarchy (mirroring `LocalLLMError`'s shape: `kind`, `message`, `endpointUrl`, `modelName`) to `src/local_llm/errors.py`
- [X] T022 [US3] Implement `GroqLLMTransport` in `src/local_llm/groq_transport.py` (new): `httpx.AsyncClient` streaming call to Groq's OpenAI-compatible chat-completions endpoint (`stream: true`, parsing `data: {...}` SSE lines up to `data: [DONE]`), reading `GROQ_API_KEY` from the environment. Depends on T021.
- [X] T023 [US3] Implement `GroqLLMEngine` in `src/local_llm/groq_engine.py` (new), satisfying the `LLMEngine` Protocol (T002) using T022's transport; default `endpointUrl` is `https://api.groq.com/openai/v1`, never passed through `local_llm.models.normalize_endpoint_url` (that stays local-only-only). Depends on T022.
- [X] T024 [US3] Add `local_llm.create_llm_engine(provider, model_name, endpoint_url=None, *, timeout=5.0, generate_timeout=None) -> LLMEngine` factory and export it (plus `GroqLLMEngine`) from `src/local_llm/__init__.py`, per `contracts/llm-engine-interface.md`'s "Engine selection contract" (exactly one engine, no fallback branch). Takes plain primitives rather than `CLIConfiguration` directly - `local_llm` is an earlier architecture layer than `cli` and must not import from it; the caller extracts the right values from its own config. Depends on T023.
- [X] T025 [P] [US3] Add `llmProvider: str = "local"` and `remoteLlmModel: str | None = None` to `CLIConfiguration` in `src/cli/config.py`, with `save_config` validation (`llmProvider` is `"local"` or `"groq"`; `remoteLlmModel` required when `llmProvider == "groq"`)
- [X] T026 [US3] In `src/cli/config_command.py`: add `--llm-provider`/`--remote-llm-model` flags to `run_config`; print the FR-013 disclosure when saving a configuration that sets `llmProvider` to `"groq"`; extend `_print_status` to report the active provider and (for `groq`) whether `GROQ_API_KEY` is set and the endpoint/model are reachable. Depends on T024, T025.
- [X] T027 [P] [US3] Update `check_ai_dependencies`'s type hint in `src/cli/availability.py` from `LocalLLMEngine` to the `LLMEngine` Protocol (T002) — no behavior change, just accurate typing now that either engine can be passed
- [X] T028 [US3] Update `src/cli/index_command.py` and `src/cli/serve_command.py` to build a **separate** chat engine via `cli.config.build_chat_llm_engine(config)` (new helper), added to `IndexRunResult` as `chatLlmEngine`, and used by `main.py`'s `start_local_server(...)` calls instead of `result.llmEngine`. Deliberately does NOT change `run_index`/`run_serve`'s existing `llm_engine` (still always `create_local_llm_engine`, unchanged) - that instance feeds `CodeSummaryPipeline`, which must stay local-only regardless of `llmProvider`, since the constitution's remote-engine exception (2.1 v2.0.0) is scoped to chat answer generation only, not to sending source code to a third party during indexing. Depends on T024, T025.

**Checkpoint**: All three user stories are independently functional — local streaming, history-aware retrieval, and the opt-in remote engine are all covered.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Keep the project's documentation set current with this implementation, per this repository's standing convention that `README.md`, `docs/architecture.md`, `docs/stack.md`, and `docs/diagrams/` are updated alongside the feature they document.

- [ ] T029 [P] Run through `specs/026-chat-streaming-context/quickstart.md` end-to-end: local streaming, elliptical follow-up retrieval, and (with a real `GROQ_API_KEY`) the opt-in remote engine
- [X] T030 [P] Update `docs/architecture.md`'s description of the `local_llm` layer to note it now hosts two `LLMEngine` implementations (local, and an opt-in remote one), and reference the constitution's v2.0.0 amendment where the "local only" guarantee is described
- [X] T031 [P] Update `docs/diagrams/sequence-diagrams/03-chat-rag.md`'s sequence diagram to show fragments streaming back to the reader as they're generated (rather than one final response), and note the engine choice (local/remote) as a branch point
- [X] T032 [P] Update `docs/stack.md` to note `httpx.AsyncClient` is now used for streaming LLM calls (local and, optionally, Groq), and that `pytest-asyncio` is a test-only addition
- [X] T033 [P] Update the chat bullet in `README.md`'s "What it does" section to mention answers stream progressively, and that an optional remote engine can be configured explicitly (with its privacy trade-off noted)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001, needed by any test exercising the new async code) — BLOCKS all user stories.
- **User Stories (Phase 3-5)**: All depend on Foundational (Phase 2) completion.
  - US1 and US2 are both P1; US2's retrieval-enrichment tests (T013) don't need US1's code, but US2's *integration* into the live pipeline (T016) touches the same `askStream()` US1 built (T010), so US2 is sequenced after US1.
  - US3 (P2) needs Foundational's `LLMEngine` Protocol (T002) but not US1/US2's own code, other than sharing `askStream()` for its own integration test (T017-T020 don't need it; the CLI/factory wiring in T021-T028 doesn't either).
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2). No dependency on US2/US3.
- **User Story 2 (P1)**: T013 (retrieval unit tests) can start after Foundational alone; T016 additionally depends on US1's T010 (`askStream()` must exist to wire history into it).
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) — independent of US1/US2's own code; T028's CLI wiring is the only place it touches shared files (`index_command.py`/`serve_command.py`), and only to swap which factory builds the engine.

### Within Each User Story

- Tests are written first and confirmed to fail before the corresponding implementation task.
- Foundational's local streaming (T004/T005) before US1's `askStream()` (T010), which US2 and US3 both build on or alongside.
- Story complete and checkpointed before moving to the next priority.

### Parallel Opportunities

- T002, T003 (Foundational) can run in parallel — different files, no dependencies among them.
- T006, T007, T008 (US1 tests) can run in parallel with each other once Foundational is done; T009 follows T008 (same file).
- T011 (US1, schemas) can run in parallel with T010 (askStream) — different files; T012 needs both.
- T013, T014 (US2 tests) can run in parallel with each other and with any remaining US1 task.
- T017, T018, T019, T020 (US3 tests) can all run in parallel with each other and with US1/US2 tasks.
- T021, T025, T027 (US3 implementation) can start immediately once Foundational is done, in parallel with each other. T021 and T025 are also prerequisites the later chain (T022 → T023 → T024, then T026, T028) waits on — only T027 has nothing downstream depending on it.
- All of Phase 6 (T029-T033) can run in parallel — five independent files.

---

## Parallel Example: Foundational Phase

```bash
# Launch the Protocol definition and its contract test together:
Task: "Define the LLMEngine Protocol in src/local_llm/protocol.py"
Task: "Extend the contract test for generateStream in tests/contract/test_local_llm_engine_interface.py"
```

## Parallel Example: User Story 1

```bash
# Launch all three test-writing tasks together (all will fail until T010-T012 land):
Task: "Unit test: LocalLLMEngine.generateStream in tests/unit/test_local_llm.py"
Task: "Integration test: ChatSession.askStream in tests/integration/test_chat_session.py"
Task: "Integration test: SSE contract in tests/integration/test_chat_api.py"
```

## Parallel Example: User Story 3

```bash
# Launch the independent implementation pieces together:
Task: "Add RemoteLLMError hierarchy in src/local_llm/errors.py"
Task: "Add llmProvider/remoteLlmModel to CLIConfiguration in src/cli/config.py"
Task: "Retype check_ai_dependencies against the LLMEngine Protocol in src/cli/availability.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001).
2. Complete Phase 2: Foundational (T002-T005) — CRITICAL, blocks all stories.
3. Complete Phase 3: User Story 1 (T006-T012).
4. **STOP and VALIDATE**: run the streaming scenario from quickstart.md by hand.
5. This alone delivers spec.md's first pain point: chat answers stream instead of arriving as one blocking block.

### Incremental Delivery

1. Setup + Foundational → the streaming engine primitive exists, nothing calls it yet.
2. Add User Story 1 → local-engine streaming works end-to-end → MVP.
3. Add User Story 2 → elliptical follow-ups retrieve the right evidence too.
4. Add User Story 3 → an operator can opt into a remote engine, fully disclosed, never a silent fallback.
5. Polish → docs (and the already-amended constitution) stay in sync with the shipped behavior.

### Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps each task to its user story for traceability.
- Commit after each task or logical group.
- Stop at any checkpoint to validate a story independently before moving on.
