# Chat Retrieval & Session Interface Contract

## Purpose

Define the changed shape of `chat.retrieval.retrieve_evidence` and the new
`chat.session.ChatSession.askStream`, replacing `ask`.

## `retrieve_evidence`

Inputs:
- `vector_index` — unchanged.
- `question: str` — unchanged.
- `history: tuple[ChatMessage, ...]` — **new**. The session's prior
  messages, most-recent-last (the same order `ChatSession.messages` already
  keeps); may be empty.
- `k: int` (keyword, `topK`) — unchanged.
- `context_window: int` (keyword, default matching the clarified "2-3 recent
  exchanges") — how many recent user questions / recent assistant citation
  sets feed enrichment.

Expected behavior:
- When `history` is empty: behaves exactly as before this feature — search
  query is `question` alone (FR-007).
- When `history` is non-empty: builds a conversationally-enriched query
  (data-model.md) from `question` plus up to `context_window` recent user
  questions and up to `context_window` recent assistant messages' citation
  data, then searches with that enriched query instead of `question` alone.
- Returns the same `tuple[RetrievedEvidence, ...]` shape as before —
  dedup-by-`chunkId` behavior is unchanged.
- Makes no LLM call and no network request beyond what `vector_index.search`
  already made before this feature (FR-006/FR-010).

## `ChatSession.askStream`

Inputs: `question: str`.

Expected behavior (replaces `ChatSession.ask`, which no longer exists):
- `async def`, returns an `AsyncIterator[str | ChatMessage]`.
- Raises `LocalDependencyUnavailableError` before yielding anything if the
  configured embedding engine or LLM engine is unavailable — same
  pre-condition check `ask()` already performed, same exception type
  (despite the name, unchanged per research.md Decision 2's naming
  rationale).
- Persists the user's question message immediately, exactly as `ask()`
  did — before any evidence retrieval or generation begins.
- Calls `retrieve_evidence(self.vectorIndex, question, history=tuple(self.messages), k=self.topK)`.
- If no evidence is found: yields the existing "insufficient evidence" text
  as a single fragment, then the final `ChatMessage` — no engine call is
  made (matches today's `ask()` behavior for this case exactly).
- If evidence is found: calls `self.llmEngine.generateStream(envelope)`,
  re-yielding each fragment as it arrives; once the stream ends, assembles
  the complete text (identical assembly logic `ask()` used for its single
  `generate()` result), computes `citedSymbolIds`/`citedFilePaths` from the
  evidence exactly as before, builds the final `ChatMessage`, persists it
  via the same `_persist()` this session already had (025), appends it to
  `self.messages`, and yields it as the **last** item.
- If `generateStream` raises partway through: the exception propagates out
  of `askStream`'s `async for` to the caller; nothing is persisted for the
  assistant's message, and `self.messages` gains no entry for it (FR-011).
  The user's question message, already persisted before generation started,
  is unaffected.

## Non-goals

- No partial/streaming persistence of individual fragments — only the
  complete, assembled `ChatMessage` is ever written (FR-004/FR-011).
- No change to `is_insufficient_evidence`/`detect_ambiguous_evidence` — they
  keep operating on whatever `retrieve_evidence` returns, enriched or not
  (FR-009).
