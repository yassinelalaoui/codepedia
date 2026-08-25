---

description: "Task list template for feature implementation"
---

# Tasks: Remote-Default AI Provider Chains with Explicit Fallback

**Input**: Design documents from `/specs/029-provider-fallback-chains/`

**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required for user stories), [research.md](./research.md) (see §13 for five post-analysis fixes folded into the tasks below), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Included — this project's established convention (every prior spec) is contract/unit/integration pytest coverage in `tests/{contract,unit,integration}/`, and `quickstart.md`'s "Automated coverage" section for this feature names the exact test files to extend/add.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P2/P3), sitting on top of a genuinely large Foundational phase — unlike a UI-only feature, this one restructures how every AI-consuming stage obtains its engine, so the new package, protocols, config shape, and schema are real blocking prerequisites shared by all four stories, not busywork.

**Note on revision**: A `/speckit-analyze` pass (2026-08-25) traced every current call site of the functions/fields this feature changes and found four concrete breakages the first draft of this file didn't cover (existing `index`/`serve`/`config` commands, and a second chat entrypoint, would each crash immediately after the planned changes landed), plus one real design ambiguity in the disclosure gate's timing. All five are folded into the task list below (each is called out inline as "(Cn fix)"/"(M1 fix)" etc.) rather than left as follow-up work.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- File paths are exact and relative to the repository root

## Path Conventions

Backend-only, existing multi-package layout: `src/<package>/`,
`tests/{contract,unit,integration}/`. No `frontend/` file is touched by
this feature (plan.md Structure Decision).

---

## Phase 1: Setup

- [X] T001 Create the `src/provider_routing/` package skeleton (`__init__.py` re-exporting the public names later tasks add: `ProviderRef`, `ProviderChain`, `FailoverExecutor`, `FailoverExhaustedError`) per plan.md's Project Structure

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The new provider abstraction, error taxonomy, router, config
shape, and schema — nothing user-observable changes yet (CLI/pipelines
still call today's single-engine paths), but every user story below
depends on this existing first.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Add `ProviderRef` (`parse`/`__str__` round-trip, `kind`/`model` validation) and `ProviderChain` (`stage`, non-empty `providers`) to `src/provider_routing/chain.py` (data-model.md ProviderRef/ProviderChain)
- [X] T003 [P] Add `RateLimitedError` to `src/local_llm/errors.py` (subclass `RemoteLLMError`, `kind="rate_limited"`, same `(message, endpointUrl, modelName)` shape as its siblings)
- [X] T004 [P] Add `RateLimitedError` and `MissingApiKeyError` to `src/embedding_engine/errors.py`, mirroring `local_llm`'s remote error family shape
- [X] T005 In `src/local_llm/groq_transport.py`, classify an HTTP 429 in `availability()` and in `generate_stream()`'s exception handling as `RateLimitedError` instead of falling into the existing generic ≥400/`RemoteGenerationFailedError` branches (depends on T003)
- [X] T006 [P] Add `isAvailable(self) -> bool` to `LocalLLMEngine` (`src/local_llm/engine.py`) and `GroqLLMEngine` (`src/local_llm/groq_engine.py`), each delegating to the existing `isAvailableLocally()` (research.md §2 — `isAvailableLocally` itself is not renamed or removed)
- [X] T007 Add `isAvailable(self) -> bool` to the `LLMEngine` Protocol in `src/local_llm/protocol.py` (depends on T006, so both existing implementations already satisfy it)
- [X] T008 [P] Create `src/embedding_engine/protocol.py` with a new `@runtime_checkable` `EmbeddingProvider` Protocol: `isAvailable`, `checkAvailability`, `embed` (contracts/provider-protocols.md)
- [X] T009 Add `isAvailable(self) -> bool` to the existing `EmbeddingEngine` class (`src/embedding_engine/engine.py`), delegating to `isAvailableLocally()`, so it satisfies `EmbeddingProvider` (depends on T008)
- [X] T010 [P] Create `src/embedding_engine/openai_transport.py`: httpx-based `POST https://api.openai.com/v1/embeddings` (model default `text-embedding-3-small`), reading `OPENAI_API_KEY` from the environment only (never persisted); maps a missing key / 401/403 to `MissingApiKeyError`, HTTP 429 to `RateLimitedError`, and network/timeout failures to `ServiceUnavailableError` (depends on T004)
- [X] T011 Create `src/embedding_engine/openai_provider.py` with `OpenAIEmbeddingProvider` (dataclass, mirrors `GroqLLMEngine`'s shape) and `create_openai_embedding_provider(model_name=...)`, built on T010's transport, satisfying `EmbeddingProvider` (depends on T008, T010)
- [X] T012 [P] Create `src/provider_routing/classify.py`: `classify_failure(exc: Exception) -> Literal["network_error", "rate_limited", "auth_failed", "unknown"]`, reading `.kind` off `local_llm`/`embedding_engine` error instances (research.md §6)
- [X] T013 [P] Create `src/provider_routing/errors.py`: `FailoverExhaustedError` (`kind="failover_exhausted"`, `stage`, `attempted: tuple[str, ...]`, `message`) per contracts/provider-protocols.md
- [X] T014 Add the `engine_failover_log` table (`id, timestamp, stage, attempted_provider, result_provider, reason`) plus its timestamp index to `src/repository_metadata/sqlite_store.py`'s `SCHEMA_STATEMENTS` tuple (contracts/sqlite-schema-deltas.md)
- [X] T015 Add a guarded `ALTER TABLE chat_messages ADD COLUMN generated_by TEXT NOT NULL DEFAULT ''` to `src/repository_metadata/sqlite_store.py`'s `ensure_schema()`, checking `PRAGMA table_info(chat_messages)` first so re-running against an already-migrated DB doesn't raise `sqlite3.OperationalError`
- [X] T016 [P] Add the equivalent guarded `ALTER TABLE chunks ADD COLUMN embedding_model_id TEXT NOT NULL DEFAULT ''` to `src/vector_index/storage.py`'s `ensure_schema()` (own `PRAGMA table_info(chunks)` guard — separate SQLite file/schema function from T014/T015)
- [X] T017 Create `src/provider_routing/failover_log.py`: `append_failover_event(connection, *, stage, attempted_provider, result_provider, reason)` and `list_failover_events(connection, *, stage=None, limit=100)` against the `repository_metadata` connection (depends on T014)
- [X] T018 Create `src/provider_routing/router.py`: `FailoverExecutor` with `run(call)` (sync path: tries each `(ProviderRef, engine)` pair in order, classifies failures via T012, appends a T017 log row on every actual switch, raises `FailoverExhaustedError` — T013 — when every entry fails), `stream(call)` (async path: identical retry logic, but only fails over if the underlying async generator raises before yielding its first item — research.md §7; once any fragment has been yielded, a later failure propagates instead of retrying), **and `isAvailable(self) -> bool`** (aggregate: `True` if any `(ProviderRef, engine)` pair's `engine.isAvailable()` is `True` — research.md §13, lets every existing single-engine pre-flight check keep working unchanged once handed a `FailoverExecutor`) (depends on T012, T013, T017)
- [X] T019 Create `src/provider_routing/factory.py`: resolve a `ProviderChain` + `CLIConfiguration` into an ordered tuple of `(ProviderRef, engine)` pairs — `"local:<model>"` → `create_local_llm_engine`/`create_embedding_engine` using the config's local endpoint/timeout settings, `"groq:<model>"` → `create_groq_llm_engine`, `"openai:<model>"` → `create_openai_embedding_provider` (T011) (depends on T002, T006, T009, T011)
- [X] T020 Extend `CLIConfiguration` in `src/cli/config.py`: add `embeddingChain: tuple[str, ...]` (default `("openai:text-embedding-3-small",)`), `summaryChain`/`chatChain: tuple[str, ...]` (default `("groq:llama-3.3-70b-versatile",)` each), `disclosureAcknowledgedSignature: str` (default `""`); remove `llmProvider`/`remoteLlmModel`; update `load_config`'s `data.get(...)` fallbacks and `save_config`'s validation (each chain non-empty, every entry parses via `ProviderRef.parse`) accordingly (depends on T002)
- [X] T021 **(C3 fix)** Update `src/cli/config_command.py`: remove `run_config`/`_print_status`'s direct reads of `config.llmProvider`/`config.remoteLlmModel` (fields T020 just removed — left as-is, this file would raise `AttributeError` on every `repo-scanner config` invocation); print the three new chains (`embeddingChain`/`summaryChain`/`chatChain`) and each entry's availability instead (depends on T020)

### Tests for Foundational

- [X] T022 [P] Extend `tests/contract/test_local_llm_engine_interface.py`: both `LocalLLMEngine` and `GroqLLMEngine` expose a callable `isAvailable()` returning a bool
- [X] T023 [P] Extend `tests/contract/test_embedding_engine_interface.py`: both `EmbeddingEngine` and the new `OpenAIEmbeddingProvider` satisfy `embedding_engine.protocol.EmbeddingProvider` (mirrors `test_local_llm_engine_interface.py`'s existing `isinstance(engine, LLMEngine)`-style assertions)
- [X] T024 [P] Create `tests/contract/test_provider_router_interface.py`: `FailoverExecutor.run` retries only on a classified-unavailable exception, never calls a provider outside the given chain, raises `FailoverExhaustedError` (with every attempted `ProviderRef` named) when all entries fail; `FailoverExecutor.stream` only fails over before the first yielded fragment; **`FailoverExecutor.isAvailable()` returns `True` iff at least one chain entry's `isAvailable()` is `True`, and `False` when every entry reports unavailable**
- [X] T025 [P] Create `tests/unit/test_provider_chain.py`: `ProviderRef.parse`/`__str__` round-trip for all three kinds, rejection of an unknown kind or empty model, `ProviderChain` rejecting an empty `providers` tuple. Scope note (research.md §13 L1): parsing validates only `kind`/non-empty `model` — it does not check that a named local model is actually installed, so no test here should assert that; that check stays at the engine's own `checkAvailability()`, exercised lazily when the chain is used
- [X] T026 [P] Create `tests/unit/test_failover_log.py`: `append_failover_event`/`list_failover_events` ordering (most-recent-first), the `result_provider IS NULL` exhausted case, and `stage` filtering
- [X] T027 [P] Create `tests/unit/test_openai_embedding_provider.py`: successful embed, 401/403 → `MissingApiKeyError`, HTTP 429 → `RateLimitedError`, unreachable host → `ServiceUnavailableError`, missing `OPENAI_API_KEY` → `MissingApiKeyError` without a network call
- [X] T028 [P] Extend `tests/unit/test_groq_llm_engine.py`: HTTP 429 from both `availability()` and `generate_stream()` raises/reports `RateLimitedError`, not the generic service-unavailable/generation-failed error
- [X] T029 [P] Extend `tests/unit/test_cli.py`: `CLIConfiguration`'s new chain fields round-trip through `load_config`/`save_config`; a config file predating this feature (no chain keys) loads with the new remote defaults; `save_config` rejects an empty chain or an unparseable `ProviderRef` string; `llmProvider`/`remoteLlmModel` are no longer accepted fields
- [X] T030 [P] **(C3 fix test)** Extend `tests/unit/test_cli.py` or `tests/integration/test_cli.py`: `repo-scanner config` (`run_config`/status display) no longer references `llmProvider`/`remoteLlmModel` and instead prints the three current chains without raising

**Checkpoint**: Foundational infrastructure exists and is fully unit/contract-tested. Nothing user-visible has changed yet — proceed to Phase 3.

---

## Phase 3: User Story 1 - Get useful results on a fresh install with zero configuration (Priority: P1) 🎯 MVP

**Goal**: A fresh install, with no configuration performed by the user,
shows the full blocking disclosure once, then actually routes code
summaries and chat answers to the default Groq chain and embeddings to the
default OpenAI chain — with the disclosure not re-blocking an unchanged
subsequent run. Every existing entrypoint that touches these stages
(`index`, `serve`, `chat_api`'s own pre-flight checks, and the standalone
`chat_api` server) keeps working once engines become chains.

**Independent Test**: On a machine with no prior configuration, run the
indexing command and confirm the disclosure appears first (naming the
default providers and the way back to local-only) and blocks until
acknowledged, then confirm summaries, embeddings, and (via a chat request)
answers are all actually produced through their respective default remote
providers with no manual provider setup.

### Tests for User Story 1

- [X] T031 [P] [US1] Extend `tests/integration/test_cli.py`: on a machine with no prior config file, invoking `index`/`serve` shows the blocking disclosure naming `openai:text-embedding-3-small` and `groq:llama-3.3-70b-versatile` and the `provider mode full-local` opt-out, and blocks (a decline aborts the command with no engine call made)
- [X] T032 [P] [US1] Extend `tests/integration/test_cli.py`: a second invocation with an unchanged configuration does not re-show the disclosure (signature match) — FR-013
- [X] T033 [P] [US1] Extend `tests/unit/test_code_summary_pipeline.py`: `CodeSummaryPipeline` summarizes successfully when its engine is a `FailoverExecutor` wrapping a single provider (regression parity with today's direct-engine behavior)
- [X] T034 [P] [US1] Extend `tests/integration/test_chat_session.py`: `ChatSession.askStream()` still answers correctly and progressively (specs 026/027/028 unaffected) when routed through a single-provider chat-stage `FailoverExecutor`
- [X] T035 [P] [US1] Extend `tests/integration/test_reindex_pipeline.py`: embedding computation during indexing succeeds through a single-provider embeddings-stage `FailoverExecutor`
- [X] T036 [P] [US1] **(C2 fix test)** Extend `tests/integration/test_chat_api.py`: `POST /sessions/{id}/messages`'s pre-flight check (`ensure_local_dependencies_available`, called directly in `chat_api/app.py`'s `ask_question` route, separately from `askStream()`'s own use of it) still returns a clean 503 when every provider in the chat/embedding chain is unavailable, and proceeds normally when at least one is — proves the route's *own* call site (not just `askStream()`'s) works once the session's engines are `FailoverExecutor`s
- [X] T037 [P] [US1] **(C1 fix test)** Extend `tests/unit/test_cli.py`: `check_ai_dependencies` (`cli/availability.py`) raises `LocalModelUnavailableError` when every provider in a stage's chain is unavailable, and passes when at least one is available, given `FailoverExecutor` arguments instead of raw engines
- [X] T038 [P] [US1] **(C4 fix test)** Extend `tests/unit/test_chat_api_server.py`: `chat_api/server.py`'s `main()` builds `FailoverExecutor`-wrapped engines (not raw engines) before constructing `VectorIndex`/`create_app`, so a chat request through this standalone entrypoint still succeeds

### Implementation for User Story 1

- [X] T039 [US1] In `src/repository_metadata/summary_pipeline.py`, change `CodeSummaryPipeline.__init__`'s `llmEngine` parameter from a concrete `LocalLLMEngine` to a `provider_routing.FailoverExecutor`; update `isReady()` and `_summarize_symbol()` to call through `FailoverExecutor.run(...)` instead of the engine directly (depends on T018)
- [X] T040 [US1] In `src/chat/session.py`, replace `askStream()`'s direct `self.llmEngine.generateStream(envelope)` call with a chat-stage `FailoverExecutor.stream(...)` call; **(C2 fix)** update `ensure_local_dependencies_available`'s two checks from `.isAvailableLocally()` to `.isAvailable()` (works identically whether handed a raw engine or a `FailoverExecutor`, per research.md §13) rather than removing the function — this keeps both its internal use here *and* `chat_api/app.py`'s separate external use of the same function correct with zero changes needed at that second call site (depends on T018)
- [X] T041 [US1] In `src/reindex_pipeline/embeddings.py` (`update_embeddings`), `src/vector_index/chunking.py` (`build_code_chunk`), **and `src/vector_index/index.py`'s `VectorIndex.search()`** (its own `self._embedding_engine.embed(search_query.queryText)` call — an additional call site found during analysis, same class of change as the other two), replace the direct `embedding_engine.embed(...)` call with an embeddings-stage `FailoverExecutor.run(...)` call (depends on T018)
- [X] T042 [US1] In `src/cli/index_command.py` and `src/cli/serve_command.py`, replace the single `create_llm_engine`/`create_embedding_engine` construction with `provider_routing.factory` calls building all three stages' `FailoverExecutor`s from `CLIConfiguration`'s chain fields; **(C1 fix)** update `check_ai_dependencies` (`src/cli/availability.py`) to call the new `FailoverExecutor.isAvailable()` aggregate instead of `.checkAvailability().available` on each engine, adjusting its error message to name the stage rather than repeat a single engine's specific status message (depends on T019, T039, T040, T041)
- [X] T043 [US1] **(C4 fix)** In `src/chat_api/server.py`, wrap the constructed `llm_engine`/`embedding_engine` in single-provider `FailoverExecutor`s (via `provider_routing.factory` or directly) before passing them to `VectorIndex(...)`/`create_app(...)`, so this standalone entrypoint's `ChatSession` receives objects matching the interface T040 now expects (`.stream()`, `.isAvailable()`) instead of a raw engine (depends on T018, T019)
- [X] T044 [US1] Create `src/cli/disclosure.py` with `ensure_disclosure_acknowledged(config: CLIConfiguration) -> CLIConfiguration`: computes the three-chain signature, compares against `config.disclosureAcknowledgedSignature`; on mismatch, prints the exact current provider for each of the three stages and the `provider mode full-local` opt-out, calls `typer.confirm(...)`, persists the new signature via `save_config` and returns the updated config; raises/aborts (nothing written, no engine called) on decline; on a match, returns `config` unchanged. Mount it in `src/cli/main.py`'s Typer app callback, run before every subcommand that touches a chain-consuming stage (`index`, `serve`, `provider chain set`, `provider mode full-local`) (depends on T020)

**Checkpoint**: User Story 1 is fully functional and independently testable — a fresh install shows the disclosure once, then actually indexes and answers chat questions via the named remote defaults, with zero manual provider configuration, through every entrypoint (`cli index`/`serve`, `chat_api`'s route, and the standalone `chat_api` server).

---

## Phase 4: User Story 2 - Switch everything to fully local in one action (Priority: P2)

**Goal**: One configuration action atomically switches all three stages'
chains to the local engine only, after which no stage makes any outbound
call to a remote provider — and the disclosure for that new, all-local
configuration is shown immediately as part of the same command, not
deferred to some later, unrelated run.

**Independent Test**: Starting from default (remote) configuration, run
the one local-mode configuration action, then run indexing and confirm no
outbound network call to any remote AI provider occurs for any of the
three stages, using local equivalents successfully instead.

### Tests for User Story 2

- [X] T045 [P] [US2] Extend `tests/unit/test_cli.py`: `run_provider_mode_full_local` writes exactly `embeddingChain=("local:nomic-embed-text",)`, `summaryChain=("local:qwen2.5-coder",)`, `chatChain=("local:qwen2.5-coder",)` in a single `save_config` call
- [X] T046 [P] [US2] Extend `tests/integration/test_cli.py`: **(M1/M3 fix)** `repo-scanner provider mode full-local` itself shows and requires acknowledgment of the disclosure naming the three just-set local entries, in the same command invocation (not deferred to a later `index`/`serve` run), and updates `disclosureAcknowledgedSignature` immediately; a subsequent `index`/`serve` run with `GROQ_API_KEY`/`OPENAI_API_KEY` unset from the environment then completes without re-showing the disclosure and without contacting either remote provider

### Implementation for User Story 2

- [X] T047 [P] [US2] Create `src/cli/provider_command.py` with `run_provider_mode_full_local()`: atomically sets all three chains to their local-only defaults via one `save_config` call (spec FR-004 — a single write, not three), then **(M1 fix)** immediately calls `ensure_disclosure_acknowledged` (T044) against the freshly-saved configuration, so the disclosure shown names the new local chains right away
- [X] T048 [US2] In `src/cli/main.py`, mount a new `provider` Typer sub-app (`app.add_typer(provider_app, name="provider")`) with a `mode full-local` command wired to `run_provider_mode_full_local` (depends on T044, T047)

**Checkpoint**: User Stories 1 and 2 both work — the fully-local safety valve is one documented command away, and it discloses its own effect immediately.

---

## Phase 5: User Story 3 - Keep working automatically when a configured remote provider becomes unavailable (Priority: P2)

**Goal**: A stage's chain configured with more than one provider
automatically continues via the next provider when the current one is
confirmed unavailable, and every actual switch is both logged
(`engine_failover_log`) and visible (`generatedBy` on the chat response,
`GET /providers/failover-log`).

**Independent Test**: Configure a stage's chain with two remote providers,
simulate the first one being unavailable (network failure, rate limit, or
authentication failure), perform an operation for that stage, and confirm
it succeeds via the second provider, with a timestamped local log entry and
a clear, visible indication of the switch.

### Tests for User Story 3

- [X] T049 [P] [US3] Create `tests/integration/test_failover_chain.py`: a two-remote-provider chain with the first forced unavailable (parametrized: network error, rate limit, auth failure) → the operation succeeds via the second provider, exactly one `engine_failover_log` row is written with the matching `reason`, and a third provider absent from the chain is never attempted
- [X] T050 [P] [US3] Extend `tests/integration/test_failover_chain.py`: every provider in a configured chain unavailable → `FailoverExhaustedError` is raised and one log row is written with `result_provider IS NULL`
- [X] T051 [P] [US3] Extend `tests/integration/test_chat_api.py`: `AskQuestionResponse`/`ChatMessageView` carry the correct `generatedBy` after a failover; `GET /providers/failover-log` returns the expected entries and honors `?stage=`
- [X] T052 [P] [US3] Extend `tests/integration/test_cli.py`: **(M1/M3 fix)** `repo-scanner provider chain set chat groq:<model> local:qwen2.5-coder` persists the new two-entry chat chain and immediately shows/requires acknowledgment of the disclosure naming that exact new chain (not stale defaults), in the same command invocation

### Implementation for User Story 3

- [X] T053 [US3] In `src/chat/models.py`, add `generatedBy: str = ""` to `ChatMessage`; in `src/chat/session.py`'s `askStream()`, populate it from the chat-stage `FailoverExecutor.stream()`'s resolved `providerUsed` once the stream completes; in `src/chat/sqlite_store.py`, read/write the `generated_by` column (T015) in `append_message` and history loading (depends on T015, T040)
- [X] T054 [P] [US3] Extend `src/cli/provider_command.py` (from T047) with `run_provider_chain_set(stage, providers)`: validates `stage` against `{"embeddings", "summary", "chat"}` and each `ProviderRef`, replaces that one stage's chain via `save_config`, then **(M1 fix)** immediately calls `ensure_disclosure_acknowledged` (T044) against the freshly-saved configuration, so the disclosure shown names the newly-set chain right away
- [X] T055 [US3] In `src/cli/main.py`'s `provider` sub-app, mount a `chain set <stage> <providerRef>...` command wired to `run_provider_chain_set` (depends on T048, T054)
- [X] T056 [US3] Extend `src/chat_api/schemas.py`: add `generatedBy: str` to `ChatMessageView` and `AskQuestionResponse`; add `FailoverLogEntryView`/`FailoverLogResponse`
- [X] T057 [US3] Add `GET /providers/failover-log` (optional `stage`/`limit` query params, most-recent-first) to `src/chat_api/app.py`, backed by `provider_routing.failover_log.list_failover_events`; populate `generatedBy` in the existing `ask_question`/`get_history` route handlers (depends on T017, T053, T056)

**Checkpoint**: User Stories 1-3 all work — configured multi-provider chains fail over automatically, and every switch is both logged and visible through the chat interface and the API.

---

## Phase 6: User Story 4 - Never let mismatched embeddings corrupt a search (Priority: P3)

**Goal**: Every stored embedding vector retains which provider/model
produced it, and a similarity search never compares vectors from
different, incompatible embedding models.

**Independent Test**: Compute embeddings for a repository with one
provider, then compute more with a different provider, then run a
similarity search and confirm every returned result is drawn from one
compatible embedding space, never a blend.

### Tests for User Story 4

- [X] T058 [P] [US4] Extend `tests/unit/test_vector_index.py`: entries with different `embeddingModelId`/`dimensionality` no longer raise `ValueError` from `rank_entries` — mismatched entries are excluded from ranking instead (research.md §8's crash fix)
- [X] T059 [P] [US4] Extend `tests/integration/test_vector_index.py`: index the same repository via two different (mocked) embedding providers, then confirm a search after each provider's embed call only returns results tagged with that provider's `embeddingModelId`, never a mix of both

### Implementation for User Story 4

- [X] T060 [US4] Add `embeddingModelId: str = ""` to `CodeChunk` and `VectorEntry` (`src/vector_index/models.py`) (depends on T016)
- [X] T061 [US4] Thread `embeddingModelId` through `src/vector_index/storage.py`'s `upsert_chunk`, `load_entries`, and `load_chunks_for_file` (read/write the `embedding_model_id` column) (depends on T060)
- [X] T062 [US4] In `src/vector_index/chunking.py`'s `build_code_chunk`, set `embeddingModelId` from the `ProviderRef` the embeddings-stage `FailoverExecutor.run()` (T041) actually used (depends on T060, T041)
- [X] T063 [US4] In `src/vector_index/search.py`'s `_matches_filters`, add an `embeddingModelId` filter branch, evaluated before `rank_entries`' existing dimensionality assertion so a mismatched entry is excluded rather than reached by it (depends on T061)
- [X] T064 [US4] In `src/vector_index/index.py`'s `VectorIndex.search()`, automatically pass the query-embedding provider's `ProviderRef` (now available since T041 routed this method's own embed call through `FailoverExecutor.run()`) as the `embeddingModelId` filter (depends on T041, T063)

**Checkpoint**: All four user stories are independently functional — the complete feature described in spec.md now works end-to-end.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T065 [P] Update `docs/architecture.md`: add a "Provider chains & failover" note and update the `chat`/`chat_api`/`repository_metadata`/`vector_index` rows to mention `provider_routing`, the new tables/columns, and the new CLI surface
- [X] T066 [P] Update `docs/stack.md` to note the new `provider_routing` package (no new third-party dependency was introduced — `httpx`, already a dependency, is reused for the new OpenAI transport)
- [X] T067 [P] Update `README.md`'s configuration section: replace the `--llm-provider`/`--remote-llm-model` examples with `provider chain set`/`provider mode full-local`, and describe the new zero-config remote defaults and the blocking disclosure gate
- [X] T068 [P] Review `docs/diagrams/`, `.gitignore`, and `pyproject.toml` for any updates this feature requires (expected no-op — no new dependency, no new build artifact; update only if something is actually found)
- [X] T069 **(M2 fix)** Confirm FR-011 (stale embedding vectors remain queryable, not deleted — no delete path is added by T060-T064), FR-014 (`tests/unit/test_language.py`, parser/dependency-graph tests, and the repository-read-only guarantee are untouched by this feature), and FR-015 (existing citation-attachment tests in `tests/integration/test_chat_session.py` and `tests/integration/test_vector_index.py`) all still pass unmodified after T039-T041 and T060-T064 — none of the three has a dedicated implementation task above (each is satisfied by *not* adding code that would violate it), so this is the explicit regression check closing that gap
- [X] T070 Run `pytest tests/contract tests/unit tests/integration` to confirm the full backend suite passes with all four user stories implemented
- [ ] T071 Execute the manual scenarios in `quickstart.md` end-to-end (requires live `GROQ_API_KEY`/`OPENAI_API_KEY` and a local Ollama with `nomic-embed-text`/`qwen2.5-coder` installed)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. **Blocks every user story** — unlike a purely additive UI feature, every one of the four stories needs the new package, protocols, router, config shape, and/or schema to exist first.
- **User Stories (Phase 3-6)**: Each depends on Foundational completing. US1 and US2 have no dependency on each other. US3 depends on US1's T040 (`ChatSession`/`ensure_local_dependencies_available` already routed through a chat-stage `FailoverExecutor`) before it can add `generatedBy` on top (T053). US4 depends on US1's T041 (embeddings-stage `FailoverExecutor`, including `VectorIndex.search()`'s own embed call) before it can tag chunks/searches with the provider that answered (T062/T064). US2's T047 and US3's T054 both depend on US1's T044 (`ensure_disclosure_acknowledged` existing to call). Recommended order is priority order (P1 → P2 → P2 → P3) both because it's reviewable incrementally and because of these real cross-story dependencies.
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Depends only on Foundational.
- **User Story 2 (P2)**: Depends on Foundational and on US1's T044 (the shared disclosure function `run_provider_mode_full_local` calls into) — otherwise independent of US1's other work.
- **User Story 3 (P2)**: Depends on Foundational, US1's T040 (`generatedBy` populates from that executor's result), and US1's T044 (same reason as US2).
- **User Story 4 (P3)**: Depends on Foundational and on US1's T041 (chunks/searches can only be tagged with the provider that answered once that call goes through the executor).

### Within Each Phase

- Foundational: T002 (ProviderRef/Chain) before T019/T020, which reference it; T003/T004 (new error kinds) before T005/T010 (transports that raise them); T008 (protocol) before T009/T011 (implementations); T012/T013/T017 before T018 (router uses all three, including the new `isAvailable()` aggregate); T014 before T015 and T017 (same table); T020 before T021 (config_command.py fix needs the new fields to exist first).
- US1: T039/T040/T041 (each pipeline's own executor wiring, independent of each other) before T042 (CLI wiring that builds and injects all three, and fixes `check_ai_dependencies`); T043 (chat_api/server.py) depends only on T018/T019, not on T039-T042; T044 (disclosure) is independent of T039-T043 and can proceed in parallel.
- US3: T053 (`generatedBy` plumbing) before T057 (API exposes it); T054 before T055 (command exists before it's mounted).
- US4: T060 before T061 before T062/T063 before T064 — a strictly linear column → storage → producer/consumer → search-integration chain.

### Parallel Opportunities

- Within Foundational, T002-T004, T006, T008, T012, T013, T016 (marked `[P]`) touch disjoint files and can proceed together; all of T022-T030 (tests) can be written in parallel once their respective implementation tasks land.
- Within US1, T031-T038 (tests) can be written in parallel; T039/T040/T041/T043 (four different files' executor wiring) can proceed in parallel before T042 converges the CLI-facing three of them.
- US2 and US4's tests/implementation can each proceed in parallel with US1's, once Foundational is done — modulo US2's dependency on US1's T044 and US4's dependency on US1's T041 noted above.
- All of Phase 7's documentation tasks (T065-T068) can run in parallel.

---

## Parallel Example: Foundational

```bash
Task: "Add ProviderRef/ProviderChain to src/provider_routing/chain.py"
Task: "Add RateLimitedError to src/local_llm/errors.py"
Task: "Add RateLimitedError and MissingApiKeyError to src/embedding_engine/errors.py"
Task: "Add isAvailable() to LocalLLMEngine and GroqLLMEngine"
Task: "Create embedding_engine/protocol.py with the EmbeddingProvider Protocol"
Task: "Create provider_routing/classify.py"
Task: "Create provider_routing/errors.py with FailoverExhaustedError"
```

## Parallel Example: User Story 1

```bash
Task: "Extend tests/integration/test_cli.py for the blocking disclosure on a fresh install"
Task: "Extend tests/integration/test_cli.py for the disclosure being skipped on an unchanged re-run"
Task: "Extend tests/unit/test_code_summary_pipeline.py for FailoverExecutor-wrapped summarization"
Task: "Extend tests/integration/test_chat_session.py for FailoverExecutor-wrapped chat streaming"
Task: "Extend tests/integration/test_reindex_pipeline.py for FailoverExecutor-wrapped embedding"
Task: "Extend tests/integration/test_chat_api.py for the route's own pre-flight check with a chain"
Task: "Extend tests/unit/test_cli.py for check_ai_dependencies with a chain"
Task: "Extend tests/unit/test_chat_api_server.py for FailoverExecutor-wrapped engines"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002-T030) — the largest phase, but a one-time cost; every story after this is comparatively small
3. Complete Phase 3: User Story 1 (T031-T044)
4. **STOP and VALIDATE**: run `pytest tests/contract tests/unit tests/integration -k "provider or failover or chain or groq or embedding or availability"`, then manually run Scenario 1 in `quickstart.md`
5. This alone already delivers the feature's core value: a fresh install works out of the box with informed, blocking disclosure, on the named remote defaults, through every entrypoint

### Incremental Delivery

1. Setup + Foundational → nothing observable yet, but every stage's engine access now goes through the same abstraction
2. Add User Story 1 → validate → zero-config installs route to the disclosed remote defaults, and no existing command (`index`/`serve`/`config`) or entrypoint (`chat_api` route, standalone `chat_api` server) has regressed
3. Add User Story 2 → validate → one command reverts everything to fully local, disclosing its own effect immediately
4. Add User Story 3 → validate → a configured multi-provider chain survives a provider outage, visibly and audibly
5. Add User Story 4 → validate → switching embedding providers never corrupts search results
6. Phase 7 → documentation + regression check + full-suite + manual quickstart validation

### Parallel Team Strategy

With multiple developers: one completes Setup + Foundational alone first
(it's the one genuinely serial dependency everything else needs). Once
done, User Story 1 should land before User Story 2 or User Story 3 start
in earnest (both depend on pieces of it — T044 and T040/T041
respectively), but User Story 4 can start as soon as US1's T041 lands even
if the rest of US1 is still in progress.
