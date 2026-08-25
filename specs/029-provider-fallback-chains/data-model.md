# Phase 1 Data Model: Remote-Default AI Provider Chains with Explicit Fallback

## ProviderRef

A single provider entry within a chain. Immutable value type.

| Field | Type | Notes |
|---|---|---|
| `kind` | `"local" \| "groq" \| "openai"` | Which engine family this entry resolves to. |
| `model` | `str` | The model name to use with that provider (e.g. `nomic-embed-text`, `llama-3.3-70b-versatile`, `text-embedding-3-small`). |

**Serialization**: `str(ref)` → `"<kind>:<model>"`; `ProviderRef.parse("groq:llama-3.3-70b-versatile")` round-trips it. This string form is what's persisted in `CLIConfiguration`'s chain fields, what the CLI accepts as a chain-entry argument, and what's stored as `attempted_provider`/`result_provider`/`generated_by` values.

**Validation**: `kind` must be one of the three known values; `model` must be non-empty. `kind="local"` is only valid for a stage whose local engine actually exists for that capability (embeddings and LLM both have one; there is no separate "local chat" vs "local summary" engine — both resolve through the same local LLM engine machinery, just with the model/prompt each pipeline already builds).

## ProviderChain

| Field | Type | Notes |
|---|---|---|
| `stage` | `"embeddings" \| "summary" \| "chat"` | Which AI-consuming stage this chain governs (spec.md Key Entities: Provider Chain). |
| `providers` | `tuple[ProviderRef, ...]` | Ordered; non-empty (an empty chain is an invalid configuration state — spec.md Edge Cases). |

**Defaults** (fresh install, no configuration — spec FR-002):

| Stage | Default chain |
|---|---|
| `embeddings` | `(ProviderRef("openai", "text-embedding-3-small"),)` |
| `summary` | `(ProviderRef("groq", "llama-3.3-70b-versatile"),)` |
| `chat` | `(ProviderRef("groq", "llama-3.3-70b-versatile"),)` |

**`provider mode full-local` result** (spec FR-004): all three become a
single `local:` entry — `(ProviderRef("local", "nomic-embed-text"),)` for
embeddings, `(ProviderRef("local", "qwen2.5-coder"),)` for summary and chat.

## FailoverAttempt (in-memory, not persisted directly)

One provider's outcome during a single `FailoverExecutor` call — the
building block `FailoverResult` and `engine_failover_log` rows are both
derived from.

| Field | Type | Notes |
|---|---|---|
| `providerRef` | `ProviderRef` | Which provider this attempt was against. |
| `outcome` | `"success" \| "unavailable"` | `unavailable` covers every retryable failure class (network, rate limit, auth) — FailoverExecutor doesn't distinguish "should I retry" by reason, only "did it work." |
| `reason` | `"network_error" \| "rate_limited" \| "auth_failed" \| None` | `None` when `outcome="success"`; otherwise the classified cause (research.md §6), used for both the failover log's `reason` column and any user-facing indication. |
| `timestamp` | `str` (ISO 8601 UTC) | When this specific attempt was made. |

## FailoverResult\[T\] (in-memory, returned by `FailoverExecutor`)

| Field | Type | Notes |
|---|---|---|
| `value` | `T` | The operation's successful result (a generated string, an embedding vector, or — for the streaming chat case — nothing; see below). |
| `providerUsed` | `ProviderRef` | Whichever provider in the chain actually produced `value`. Becomes `ChatMessage.generatedBy` / the embedding's `embeddingModelId`. |
| `attempts` | `tuple[FailoverAttempt, ...]` | Every provider tried, in order, including the final successful one. Length 1 for the common "first provider worked" case. |

For the streaming chat case, `FailoverExecutor.stream(...)` is an async
generator yielding fragments directly (so `ChatSession.askStream` keeps
yielding fragments as they arrive, unchanged from the caller's point of
view); `providerUsed`/`attempts` become available as attributes on the
executor instance once the stream is exhausted, read by the caller
afterward to build the persisted `ChatMessage` and any failover-log entry —
mirroring how `askStream` already assembles its final `ChatMessage` only
after the fragment loop completes.

## Fallback Event / `engine_failover_log` (persisted — repository_metadata's SQLite file)

One row per **actual switch** from one provider to the next (not one row
per operation, and not one row per provider in a chain that succeeded on
its first try — a chain that never needed to fail over produces zero rows).

| Column | Type | Notes |
|---|---|---|
| `id` | `TEXT PRIMARY KEY` | `stable_*_id`-style deterministic hash, following existing `repository_metadata` convention. |
| `timestamp` | `TEXT NOT NULL` | ISO 8601 UTC, when the switch was detected. |
| `stage` | `TEXT NOT NULL` | `"embeddings" \| "summary" \| "chat"`. |
| `attempted_provider` | `TEXT NOT NULL` | The `ProviderRef` string that failed, triggering this switch. |
| `result_provider` | `TEXT` (nullable) | The `ProviderRef` string switched to. `NULL` specifically represents the FailoverExhausted case (spec FR-007) — every provider in the chain was attempted and none worked, so there is no "switched to." |
| `reason` | `TEXT NOT NULL` | `"network_error" \| "rate_limited" \| "auth_failed"` — why `attempted_provider` was judged unavailable. |

Indexed on `timestamp` for the `GET /providers/failover-log` route's default
most-recent-first ordering.

## Embedding Vector Record (extended — `vector_index`'s `chunks` table)

Existing `CodeChunk`/`VectorEntry` (`vector_index/models.py`) and the
`chunks` table (`vector_index/storage.py`) gain one field/column:

| Field/Column | Type | Notes |
|---|---|---|
| `embeddingModelId` / `embedding_model_id` | `str` / `TEXT NOT NULL DEFAULT ''` | The `ProviderRef` string of whichever provider/model actually computed this vector (spec FR-009). Empty string for any row written before this feature shipped — treated as "unknown legacy model," never matched against a specific current provider's filter, so old rows remain visible in isolation but are correctly excluded from a same-model search comparison against a *named* current provider (spec Edge Cases: pre-existing embeddings "remain valid, retrievable local data" rather than deleted or crashing). |

**Relationship / validation rule (spec FR-010)**: `VectorIndex.search()`'s
similarity ranking (`vector_index/search.py` `rank_entries`/`_matches_filters`)
excludes every entry whose `embeddingModelId` doesn't match the id of the
provider that produced the current query's embedding, **before** the
existing dimensionality check runs — so mismatched vectors are filtered out
by construction, never compared, and never reach the dimensionality
assertion (which today raises `ValueError` on a mismatch it currently has
no better way to handle — research.md §8).

## CLIConfiguration (extended — `cli/config.py`)

| Field | Type | Notes |
|---|---|---|
| `embeddingChain` | `tuple[str, ...]` | Default `("openai:text-embedding-3-small",)`. |
| `summaryChain` | `tuple[str, ...]` | Default `("groq:llama-3.3-70b-versatile",)`. |
| `chatChain` | `tuple[str, ...]` | Default `("groq:llama-3.3-70b-versatile",)`. |
| `disclosureAcknowledgedSignature` | `str` | Default `""` (never acknowledged). A hash of the three chains above as they stood at the last explicit acknowledgment (FR-013). |
| `llmModel`, `llmEndpointUrl`, `llmGenerateTimeout` | *(existing, unchanged types)* | Now scoped to "connection settings for any `local:` chain entry in `summaryChain`/`chatChain`" rather than "the LLM in use" — the model name itself now lives in each chain entry. |
| `embeddingModel`, `embeddingEndpointUrl`, `embeddingGenerateTimeout` | *(existing, unchanged types)* | Same narrowing, for `embeddingChain`'s `local:` entries. |

**Removed**: `llmProvider`, `remoteLlmModel` — fully superseded by
`chatChain`/`summaryChain` (research.md §10); no dual-write/back-compat
shim, since a config file predating this feature simply won't have the new
chain keys and `load_config`'s existing `data.get(key, default)` pattern
already falls back to the new remote defaults for it, which *is* the
intended one-time transition (spec.md Assumptions).

## State transitions

```text
Fresh install (no config file)
  → CLIConfiguration() defaults: 3 remote chains, disclosureAcknowledgedSignature=""
  → first command touching a chain-consuming stage: signature mismatch ("" != current)
    → blocking disclosure shown, typer.confirm() required
    → on acknowledgment: disclosureAcknowledgedSignature = sign(current 3 chains); command proceeds
    → on decline: command aborts, nothing is written, nothing is called remotely

`provider chain set <stage> ...` / `provider mode full-local`
  → validates + save_config()'s new chain fields (+ signature left AS-IS, now stale)
  → next command run: signature mismatch (old sign != new current)
    → blocking disclosure shown again, must be re-acknowledged before proceeding

Per AI-consuming operation (embed / summarize / ask):
  FailoverExecutor built from the stage's chain + CLIConfiguration
  → try providers[0]
    success → FailoverResult(providerUsed=providers[0], attempts=[success]) — no log row
    unavailable → classify reason; log one engine_failover_log row
      (attempted=providers[0], result=providers[1] if it exists else NULL, reason=...)
      → try providers[1] (if present) ... repeat
  → every provider unavailable → FailoverExhaustedError raised (spec FR-007),
    last log row for this call has result_provider = NULL
```
