# Implementation Plan: Remote-Default AI Provider Chains with Explicit Fallback

**Branch**: `029-provider-fallback-chains` | **Date**: 2026-08-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/029-provider-fallback-chains/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Replaces single-engine injection for all three AI-consuming stages
(embeddings, code summarization, chat) with an ordered, per-stage
`ProviderChain` resolved and executed by a new stage-agnostic
`FailoverExecutor` (new `provider_routing` package) — the deferred
implementation of constitution v3.0.0's 2.1/2.3 amendment. On a fresh
install each chain already contains one remote default
(`openai:text-embedding-3-small` for embeddings, `groq:llama-3.3-70b-versatile`
for summary and chat, reusing the model name already used throughout the
existing Groq test suite); a new `EmbeddingProvider` protocol
(parallel to the existing `local_llm.LLMEngine`) lets the local embedding
engine and a new `OpenAIEmbeddingProvider` share one interface. Automatic
failover is triggered only by a classified-unavailable error (network,
rate limit — a new error kind that doesn't exist today — or auth failure),
never by preference, and every actual switch is written to a new
`engine_failover_log` table (in the existing per-repository
`repository_metadata` SQLite file) and surfaced through a new
`GET /providers/failover-log` route plus a new `generatedBy` field on chat
messages/responses. `vector_index`'s `chunks` table gains an
`embedding_model_id` column, and similarity search now filters out
mismatched-model vectors before ranking — which also fixes a real,
previously-existing crash (`VectorIndex.search()` raises `ValueError` today
the moment stored vectors have mixed dimensionality, rather than handling
it). Two new CLI subcommands (`provider chain set`, `provider mode
full-local`) and one centrally-enforced, blocking, explicit-acknowledgment
disclosure gate (Typer app callback, re-triggered whenever the three
chains' combined signature changes) complete the CLI surface. No frontend
change is in scope — `generatedBy`/the failover log are new backend/API
surface a future UI feature can consume, following this codebase's existing
staging pattern (spec 026 similarly deferred its own frontend consumption).

## Technical Context

**Language/Version**: Python 3.11 (backend only — `local_llm`, `embedding_engine`, `vector_index`, `chat`, `chat_api`, `repository_metadata`, `cli`, and a new `provider_routing` package). No frontend (`frontend/`) file is touched by this feature.

**Primary Dependencies**: `httpx` (existing — reused for the new `OpenAIEmbeddingProvider` transport, mirroring `groq_transport.py`; no new HTTP client dependency), `typer` (existing — new `provider` sub-app), `pydantic` (existing — two new `chat_api` schema classes), stdlib `sqlite3` (existing — two additive schema changes). No new third-party package is introduced.

**Storage**: SQLite, extending two already-existing per-repository files: `repository_metadata`'s (new `engine_failover_log` table + `chat_messages.generated_by` column) and `vector_index`'s (new `chunks.embedding_model_id` column). No new database file, no migration framework — both additions follow the existing idempotent `ensure_schema()` convention, with a `PRAGMA table_info` guard for the two `ALTER TABLE ADD COLUMN` statements (the one case that convention doesn't already handle idempotently).

**Testing**: pytest (`tests/contract`, `tests/unit`, `tests/integration` — the existing layout every spec in this project follows). New contract coverage for `FailoverExecutor`/`EmbeddingProvider`; new unit coverage for `ProviderRef`/`ProviderChain` parsing, the failover log, and vector-index same-model filtering; new integration coverage for the CLI `provider` commands, the disclosure gate, and the extended `chat_api` routes/schemas.

**Target Platform**: Cross-platform local CLI + local server (Windows/Linux/macOS) — unchanged from every prior spec; no new network-exposure surface (constitution 2.2 untouched, no new server binding introduced).

**Project Type**: Existing single-repo, multi-package Python backend (Option 1-shaped: `src/<package>/`, `tests/{contract,unit,integration}/`) plus the separately-versioned `frontend/` from prior specs, which this feature does not touch.

**Performance Goals**: A chain with its first provider available incurs no additional latency over today's single-engine call (one direct call, no retry overhead). A chain that must fail over incurs at most one bounded availability/timeout wait per skipped provider before reaching a working one — existing per-engine timeouts (`AvailabilityStatus`/`checkAvailability`, already time-bounded at 5s for Groq's `/models` check) are reused unchanged, not widened. The disclosure gate blocks at most once per actual chain-configuration change, never once per operation.

**Constraints**: No new runtime dependency, no new server-exposure surface, no schema-migration framework (constitution 2.2/2.6). Pre-existing `chat_messages`/`chunks` rows must remain valid and queryable unchanged after the two `ALTER TABLE` additions (constitution 2.6's local-storage durability expectation, spec FR-011). `FailoverExecutor` must never attempt a provider absent from the stage's configured chain, and must never cross into/out of local mode unless local is itself in that chain (constitution 2.3, spec FR-006) — enforced structurally by only ever being handed the already-resolved chain, never a broader provider registry.

**Scale/Scope**: Single local operator; chains are typically 1-3 providers long. No pagination/volume concern for `engine_failover_log` beyond the existing per-repository SQLite scale already accepted for `chat_sessions`/`chat_messages`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| 2.1 Moteur distant par defaut, mode local disponible sur choix explicite | This feature **is** the deferred implementation of 2.1 (v3.0.0): fresh-install defaults become remote (OpenAI/Groq) for all three stages, full-local remains fully supported but only via explicit chain configuration, and the mandatory disclosure (FR-012/FR-013) is strengthened into a blocking, re-triggered-on-change gate exactly as amendment 2.1 requires. PASS. |
| 2.2 Zero exposition reseau par defaut | Not implicated: `GET /providers/failover-log` is registered on the same already-127.0.0.1-bound `chat_api` FastAPI app as every existing route — no new binding, no new server process. PASS. |
| 2.3 Repli automatique seulement au sein d'une chaine de moteurs explicitement configuree | This feature **is** the deferred implementation of 2.3: `FailoverExecutor` only ever iterates the exact chain it's handed (never a broader registry, never local unless local is a configured entry), triggers only on classified unavailability (never preference/round-robin), and every actual switch is both logged (`engine_failover_log`) and surfaced (`generatedBy`, `GET /providers/failover-log`) without requiring per-occurrence confirmation. PASS. |
| 2.4 Tracabilite des reponses IA | Reinforced, not altered: citation attachment (`citedSymbolIds`/`citedFilePaths`) is completely unchanged; `generatedBy` adds *provider* attribution alongside existing *source* attribution, a strict addition. PASS. |
| 2.5 Re-indexation incrementale | Not implicated: a provider/model switch does not trigger a forced full re-embed (research.md, spec Assumptions) — existing incremental reindexing (`reindex_pipeline`) is untouched; new/changed content picks up the newly-configured chain naturally as it's processed. PASS. |
| 2.6 Infrastructure minimale et stockage local | No new external service, no new dependency, no new database file — one new table and two new columns in two already-existing local SQLite files. PASS. |
| 2.7 Depot analyse en lecture seule | Not implicated: no source-repository write path is touched by this feature. PASS. |

No violations. Complexity Tracking table intentionally omitted (nothing to justify) — this feature directly implements two constitution principles rather than trading off against any of them.

**Post-Phase-1 re-check**: Phase 1 design (`data-model.md`, `contracts/`)
introduces one new package (`provider_routing`), one new SQLite table plus
two new columns (both additive, both idempotently guarded), two new CLI
subcommands plus one centrally-enforced disclosure gate, and two extended
`chat_api` schemas plus one new read-only route. None of this adds a
network-exposure surface, a new runtime dependency, a migration framework,
or a repository write. All gates above still PASS unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/029-provider-fallback-chains/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── provider-protocols.md
│   ├── cli-provider-commands.md
│   └── sqlite-schema-deltas.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── provider_routing/            # NEW package
│   ├── chain.py                 # ProviderRef, ProviderChain
│   ├── router.py                # FailoverExecutor (run/stream)
│   ├── classify.py              # exception -> "network_error"|"rate_limited"|"auth_failed"
│   ├── errors.py                # FailoverExhaustedError
│   ├── factory.py                # ProviderChain + CLIConfiguration -> resolved (ProviderRef, engine) list
│   └── failover_log.py           # engine_failover_log append/list (repository_metadata's DB)
├── local_llm/
│   ├── protocol.py               # + isAvailable() on LLMEngine
│   ├── engine.py, groq_engine.py # + isAvailable() (delegates to isAvailableLocally())
│   ├── errors.py                 # + RateLimitedError
│   └── groq_transport.py         # + HTTP 429 classified as RateLimitedError
├── embedding_engine/
│   ├── protocol.py                # NEW: EmbeddingProvider protocol
│   ├── engine.py                  # + isAvailable()
│   ├── errors.py                  # + RateLimitedError, MissingApiKeyError
│   ├── openai_provider.py         # NEW: OpenAIEmbeddingProvider
│   └── openai_transport.py        # NEW: httpx-based OpenAI embeddings transport
├── vector_index/
│   ├── models.py                  # CodeChunk/VectorEntry + embeddingModelId
│   ├── storage.py                 # chunks.embedding_model_id column + guarded ALTER TABLE
│   ├── search.py                  # _matches_filters: embeddingModelId filter before dimensionality check
│   └── index.py                   # VectorIndex.search() passes the query-embedding provider's id as a filter
├── chat/
│   ├── models.py                  # ChatMessage + generatedBy
│   ├── session.py                 # askStream() uses a chat-stage FailoverExecutor instead of a single llmEngine
│   └── sqlite_store.py            # chat_messages.generated_by column + guarded ALTER TABLE
├── repository_metadata/
│   ├── sqlite_store.py            # + engine_failover_log table (SCHEMA_STATEMENTS)
│   └── summary_pipeline.py        # CodeSummaryPipeline uses a summary-stage FailoverExecutor instead of one LocalLLMEngine
├── chat_api/
│   ├── schemas.py                 # + generatedBy on ChatMessageView/AskQuestionResponse; + FailoverLogEntryView/FailoverLogResponse
│   └── app.py                     # + GET /providers/failover-log
└── cli/
    ├── config.py                  # CLIConfiguration: + embeddingChain/summaryChain/chatChain/disclosureAcknowledgedSignature; - llmProvider/remoteLlmModel
    ├── provider_command.py        # NEW: run_provider_chain_set, run_provider_mode_full_local
    ├── main.py                    # + provider sub-app mount; + disclosure-gate callback
    └── index_command.py, serve_command.py  # build chains via provider_routing.factory instead of a single create_llm_engine/create_embedding_engine call

tests/
├── contract/
│   ├── test_provider_router_interface.py     # NEW
│   └── test_embedding_provider_interface.py  # NEW (EmbeddingProvider conformance)
├── unit/
│   ├── test_provider_chain.py         # NEW
│   ├── test_failover_log.py           # NEW
│   ├── test_openai_embedding_provider.py  # NEW
│   ├── test_groq_llm_engine.py        # extended: 429 -> RateLimitedError
│   └── test_vector_index.py           # extended: same-model filtering, mixed-dimensionality no longer crashes
└── integration/
    ├── test_cli_provider_commands.py  # NEW
    ├── test_failover_chain.py         # NEW: end-to-end chain exhaustion + successful failover
    └── test_chat_api.py               # extended: generatedBy, GET /providers/failover-log

frontend/                              # untouched by this feature
```

**Structure Decision**: Extends the existing single-repo, multi-package
Python backend (`src/<package>/`, `tests/{contract,unit,integration}/`,
established since spec 001) with one new package (`provider_routing`) that
sits alongside `local_llm`/`embedding_engine` in the dependency graph, plus
targeted extensions to the seven existing packages that currently do
single-engine injection or would otherwise be unaware of provider identity
(`local_llm`, `embedding_engine`, `vector_index`, `chat`,
`repository_metadata`, `chat_api`, `cli`). No new top-level directory
beyond `src/provider_routing/`; `frontend/` (spec 028) is untouched.

## Complexity Tracking

Not applicable — no constitution violations to justify.
