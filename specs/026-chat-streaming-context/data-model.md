# Phase 1 Data Model: Chat Streaming & Conversational Context Retrieval

## Overview

No new persisted storage (reuses 025's `chat_sessions`/`chat_messages`
schema unchanged). This feature's "entities" are mostly in-memory/runtime
shapes: the streaming protocol surface, the enriched query, and the new
configuration fields. Existing types (`PromptEnvelope`, `GenerationResult`,
`AvailabilityStatus`, `ChatMessage`, `ChatSession`) are reused as-is.

## Entities

### LLMEngine (Protocol, `local_llm/protocol.py`)

Not a persisted entity — a structural interface both engines satisfy.

| Member | Signature | Notes |
| --- | --- | --- |
| `isAvailableLocally` | `() -> bool` | Name kept unchanged for both engines despite now also describing a remote engine's reachability — research.md Decision 2. |
| `checkAvailability` | `() -> AvailabilityStatus` | Same `AvailabilityStatus` shape (`available`, `serviceReachable`, `modelInstalled`, `message`) reused by both engines; for `GroqLLMEngine`, `modelInstalled` means "the configured model name is a recognized Groq model," not a local install. |
| `generate` | `(prompt: str \| PromptEnvelope) -> str` | Sync convenience wrapper; drains `generateStream` via `asyncio.run(...)` and concatenates (research.md Decision 1). |
| `generateStream` | `(prompt: str \| PromptEnvelope) -> AsyncIterator[str]` | The new primitive. Raises the engine's existing error types (e.g. `ServiceUnavailableError`, or a new `GroqLLMError` subtype) before yielding anything if the engine is unavailable; may raise mid-stream on a transport failure. |

### GroqLLMEngine (`local_llm/groq_engine.py`)

| Field | Type | Notes |
| --- | --- | --- |
| `modelName` | `str` | e.g. `"llama-3.3-70b-versatile"` — validated non-empty, same as `LocalLLMEngine.modelName`. |
| `endpointUrl` | `str` | Defaults to `https://api.groq.com/openai/v1`; **not** run through `local_llm.models.normalize_endpoint_url` (that validator stays local-only-only, untouched). |
| `apiKey` | `str` | Read from the `GROQ_API_KEY` environment variable at construction time by `create_groq_llm_engine()` — never a field sourced from `CLIConfiguration`/`config.json`. |
| `timeout` / `generateTimeout` | `float` | Same shape as `LocalLLMEngine`'s, independently tunable defaults suited to a remote API's latency profile. |

### Conversationally-Enriched Search Query (runtime value, `chat/retrieval.py`)

Not a class — the string ultimately passed to `VectorIndex.search(...)`,
built by a new `build_enriched_query(question, history, *, context_window)`
helper. Composition, most-recent-first within the window:

1. The current `question`, always included, always last (keeps it the most
   prominent signal for the embedding).
2. Up to `context_window` (2-3, per `/speckit-clarify`) prior **user**
   message texts from `history`.
3. The `citedSymbolIds` and `citedFilePaths` already recorded on up to
   `context_window` prior **assistant** messages from `history` — reused
   directly from already-persisted `ChatMessage` fields, no new
   summarization step.

When `history` is empty, steps 2-3 contribute nothing and the enriched
query is exactly `question` (FR-007's plain-search fallback, satisfied by
construction rather than a separate code branch).

### Streamed Answer Fragment / Completion Event (`chat_api` SSE payloads)

| Event | Shape | When |
| --- | --- | --- |
| fragment | `{"fragment": str}` | Once per piece yielded by `askStream()` before the final item. |
| done | `{"answer": str, "citedSymbolIds": [str, ...], "citedFilePaths": [str, ...]}` | Exactly once, last — the same fields `AskQuestionResponse` already has today. |
| error | `{"code": str, "message": str}` | At most once, replacing the `done` event if `askStream()` raised — same shape `ApiErrorResponse` already uses. |

### Answer-Generation Engine Configuration (`cli/config.py`)

Extends the existing `CLIConfiguration` dataclass (additive fields only, no
existing field changes):

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `llmProvider` | `str` | `"local"` | Only `"local"` or `"groq"` accepted; validated in `save_config`, same pattern as existing endpoint validation. |
| `remoteLlmModel` | `str \| None` | `None` | Required (validated) only when `llmProvider == "groq"`. |

`GROQ_API_KEY` is deliberately **not** a `CLIConfiguration` field — see
research.md Decision 5.

## Relationships

```text
CLIConfiguration.llmProvider ──selects──> create_llm_engine() ──builds exactly one──> LLMEngine
                                                                                         ├─ LocalLLMEngine
                                                                                         └─ GroqLLMEngine (opt-in)

ChatSession.askStream(question)
    ├─ retrieve_evidence(vectorIndex, question, history=self.messages, k=topK)
    │      └─ build_enriched_query(question, history) ──used by──> VectorIndex.search(...)
    ├─ llmEngine.generateStream(promptEnvelope) ──yields──> fragment, fragment, ..., ChatMessage
    └─ chat.sqlite_store.append_message(...)  # once, at completion, per FR-004/FR-011
```

## State / Lifecycle

- **No new persisted state.** `askStream()`'s only write to `chat.sqlite_store`
  is the same single `append_message` call `ask()` already made for the
  assistant's message — now triggered once the stream completes rather than
  once a blocking `generate()` call returns.
- **Engine selection is immutable per process/session construction** — a
  `ChatSession`'s `llmEngine` is whichever engine `SessionRegistry`/CLI
  wiring built at startup from `CLIConfiguration`; nothing changes it mid-session,
  which is exactly what guarantees FR-014 (no automatic switch).
- **A failed stream leaves no trace** — no `chat_messages` row, no partial
  `ChatSession.messages` entry, consistent with FR-011.
