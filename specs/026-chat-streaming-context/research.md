# Phase 0 Research: Chat Streaming & Conversational Context Retrieval

## Decision 1 — `generateStream` is a real `async def` generator, not a sync one

**Decision**: `LLMEngine.generateStream(prompt) -> AsyncIterator[str]` is a
genuine `async def` async generator, backed by `httpx.AsyncClient` for both
`LocalLLMEngine` (Ollama, `"stream": true`) and the new `GroqLLMEngine`
(Groq's OpenAI-compatible streaming chat-completions endpoint). `generate()`
stays a plain synchronous method (unchanged signature) that internally drains
`generateStream()` via `asyncio.run(...)` and concatenates.

**Rationale**: The request explicitly typed this as `AsyncIterator<String>`,
and `httpx` — already a direct dependency (`pyproject.toml`, `>=0.27`) used
elsewhere in this codebase — supports real async streaming HTTP requests out
of the box, so honoring that typing costs no new dependency. FastAPI's
`StreamingResponse` is natively async-generator-friendly, which is exactly
what the new `POST /sessions/{id}/messages` route needs (Decision 6). All
existing sync callers of `generate()` (`repository_metadata.summary_pipeline`
for module/function summaries — a fully synchronous batch pipeline with no
asyncio anywhere) keep working unchanged, since `generate()`'s signature and
behavior are unchanged from the caller's perspective; only its internal
implementation now drains a stream instead of making one blocking call.
`asyncio.run()` is safe here specifically because none of `generate()`'s
remaining callers are themselves inside a running event loop — the one
caller that *is* async (`ChatSession.askStream()`) calls `generateStream()`
directly, never `generate()`, avoiding the "asyncio.run() inside a running
loop" trap entirely.

**Alternatives considered**:
- A plain sync generator (`Iterator[str]`), reading `urlopen()`'s response
  incrementally line-by-line — technically sufficient to achieve real
  streaming (HTTP chunked delivery doesn't require asyncio), and would have
  kept the whole codebase synchronous. Rejected because the request
  explicitly specified `AsyncIterator`, and because FastAPI's streaming
  route (Decision 6) is more naturally async-native given `httpx` is already
  present — going sync-only would mean either wrapping a sync generator in
  a thread for the FastAPI route (extra indirection) or blocking the event
  loop during generation (defeats the purpose of an ASGI server).
- `aiohttp` instead of `httpx` for the async client — rejected, `httpx` is
  already the project's HTTP client dependency (used by FastAPI's own
  `TestClient`); adding a second HTTP library for no functional gain
  contradicts constitution 2.6 (infrastructure minimale).

## Decision 2 — One `LLMEngine` Protocol, one factory, zero fallback code

**Decision**: `local_llm/protocol.py` defines `LLMEngine` as a
`typing.Protocol` (structural typing — `LocalLLMEngine` and `GroqLLMEngine`
satisfy it without inheriting from it, matching how the codebase already
duck-types `llm_engine: Any` everywhere): `isAvailableLocally() -> bool`,
`checkAvailability() -> AvailabilityStatus`, `generate(prompt) -> str`,
`generateStream(prompt) -> AsyncIterator[str]`. A single factory,
`local_llm.create_llm_engine(config: CLIConfiguration) -> LLMEngine`, builds
*exactly one* engine — `create_local_llm_engine(...)` when
`config.llmProvider == "local"` (the default), `create_groq_llm_engine(...)`
when `config.llmProvider == "groq"`. No code path anywhere tries the other
engine when the configured one is unavailable.

**Rationale**: Constitution 2.3 (v2.0.0) requires that the system "ne bascule
jamais automatiquement d'un moteur configuré vers un autre." The simplest,
most auditable way to guarantee that is to never write the code that could
do it — a single factory returning one concrete engine per call, with no
try/except-and-retry-on-the-other-engine logic anywhere, makes "no silent
fallback" true by construction rather than by discipline. Keeping
`isAvailableLocally()`'s name unchanged (even though it now also describes a
remote engine's reachability) avoids renaming a method referenced across
`chat/session.py`, `cli/availability.py`, and every existing test — a
cosmetic rename with a large blast radius for no behavioral benefit.

**Alternatives considered**:
- A `CompositeLLMEngine` that tries local first, then remote, on failure —
  this is precisely the "repli automatique" constitution 2.3 forbids;
  rejected outright, not just as a style preference.
- Renaming `isAvailableLocally()` to something engine-neutral (e.g.
  `isAvailable()`) — rejected for this feature; the rename touches many
  unrelated call sites for a naming nicety and isn't required by any FR.

## Decision 3 — Conversational-context enrichment: local concatenation, not an LLM rewrite

**Decision**: `retrieve_evidence(vector_index, question, history, *, k, context_window=3)`
builds its enriched query by locally concatenating: the current question,
the text of up to `context_window` recent **user** questions from `history`,
and the `citedSymbolIds`/`citedFilePaths` already recorded on up to
`context_window` recent **assistant** messages (already-persisted, compact
strings — no re-summarization needed). No LLM call is made to build the
query.

**Rationale**: The request offered two options — "concaténation
contextuelle" or "courte réécriture via le même LLMEngine" — and explicitly
left the choice to planning (spec.md Assumptions). Using "le même LLMEngine"
for query rewriting is the wrong choice now that the same engine can be a
*remote* one (this feature's other half): rewriting a follow-up through a
configured `GroqLLMEngine` would send recent conversation content to Groq
just to build a search query, which is a real, separate privacy exposure
beyond what generating the final answer already requires — squarely what
FR-006/FR-010 rule out ("no new outbound network dependency for
enrichment... regardless of which engine is configured"). Local
concatenation sidesteps this entirely: it works identically no matter which
engine is configured for answers, adds no extra network round-trip or LLM
generation cost, and is deterministic (a real advantage for testing FR-008's
acceptance scenarios, where an LLM-rewritten query's exact wording would
vary run to run). Using structured citation data (`citedSymbolIds`/
`citedFilePaths`) rather than raw assistant prose is the key trick that
makes elliptical follow-ups work well: for "what about the other one?"
after an answer that named `oauth.py` alongside the main answer's subject,
the *citations* carry that name compactly — raw prose would be noisier and
more expensive to embed for the same signal.

**Alternatives considered**:
- LLM-based query condensation via the configured engine — rejected per the
  privacy/determinism reasoning above; also adds latency ahead of retrieval,
  working against SC-002's "time-to-first-fragment stays flat" goal for a
  step that happens before generation even starts.
- Using only recent user-question text (no citation data) — considered and
  rejected: the acceptance scenario's own example ("what about the other
  one?") typically refers to something the *assistant's answer* named, not
  the user's own prior question wording; omitting citation data would leave
  exactly the elliptical case (User Story 2's core scenario) under-served.
- Using the full session history rather than a bounded window — rejected,
  already resolved via `/speckit-clarify` (spec.md Clarifications: a small,
  fixed window of 2-3 recent exchanges).

## Decision 4 — `ChatSession.askStream()` replaces `ask()`; persistence happens once, at completion

**Decision**: `ChatSession.ask()` is removed; `ChatSession.askStream(question)`
is an `async def` generator. It: persists the user message immediately (as
`ask()` already did); performs the same evidence-sufficiency/ambiguity
checks as today, now against `retrieve_evidence(..., history=...)`'s
possibly-enriched results; if evidence exists, calls
`self.llmEngine.generateStream(envelope)` and re-yields each fragment as it
arrives while accumulating it in memory; once the underlying stream ends
(or immediately, for the insufficient-evidence case, which never streams),
assembles the complete answer text, computes citations exactly as `ask()`
did, builds the final `ChatMessage`, persists it via the same
`chat.sqlite_store.append_message` call `_persist()` already used, appends
it to `self.messages`, and yields it last. If `generateStream()` raises
partway through, the exception propagates out of the `async for` consuming
`askStream()` and nothing is persisted for that attempt (FR-011) — the
partially-accumulated text is simply discarded, never written.

**Rationale**: Directly implements the request's "`ChatSession.ask()` devient
`ChatSession.askStream()`, retournant un générateur asynchrone de tokens
partiels puis le `ChatMessage` final... persisté via [025] au fil de l'eau."
Persisting only once, at completion (not per-fragment), is what FR-004
("citations attached to the complete, assembled answer only") and FR-011
("no history side effect on a failed stream") already committed to in
spec.md — persisting partial fragments individually would make FR-011
impossible to satisfy cleanly (there would be partial rows to roll back).
"Persisted... au fil de l'eau" (progressively) describes the overall flow
being incremental compared to today's fully-blocking model (the user
message is still persisted immediately, exactly as in 025), not that every
individual token gets its own database write.

**Alternatives considered**:
- Keep `ask()` alongside a new `askStream()` — rejected: the request says
  `ask()` "becomes" `askStream()` (a replacement), and spec.md's own
  Assumption ("today's ability to get a complete answer is preserved") is
  satisfied by consuming `askStream()` to completion, not by keeping two
  parallel methods with duplicated logic to maintain.
- Persist each fragment as its own row — rejected per FR-004/FR-011 above.

## Decision 5 — `GroqLLMEngine`: opt-in configuration, key never touches disk

**Decision**: `CLIConfiguration` gains `llmProvider: str = "local"` and
`remoteLlmModel: str | None = None` (persisted in `~/.codepedia/config.json`,
like every other config field). The Groq API key is read only from the
`GROQ_API_KEY` environment variable at the moment `GroqLLMEngine` is
constructed — never written to `config.json`, never logged. `codepedia
config --llm-provider groq --remote-llm-model <name>` prints an explicit
disclosure (FR-013) before saving: that questions and cited code context
will be sent to Groq's API. `codepedia config --llm-provider local`
switches back, and this is the *only* way the provider changes — there is
no automatic reversion.

**Rationale**: `local_llm.models.normalize_endpoint_url` already hard-rejects
any non-`localhost`/`127.0.0.1`/`::1` hostname — a real enforcement
mechanism for the local engine's "always local" guarantee. That validation
stays completely untouched for `LocalLLMEngine`; `GroqLLMEngine` uses its
own, separate endpoint handling (a fixed default base URL,
`https://api.groq.com/openai/v1`, not run through
`normalize_llm_endpoint_url`) so the local engine's guarantee is never
weakened by this change. Keeping the API key out of `config.json` follows
standard practice for CLI tools handling cloud credentials, and reduces the
chance of a key leaking via a committed or backed-up config file — a
meaningfully worse outcome than a locally-scoped code-privacy trade-off the
user explicitly opted into.

**Alternatives considered**:
- Store the API key in `config.json` — rejected: `config.json` is a plain,
  unencrypted file with no access-control story beyond the filesystem's
  own; secrets don't belong there when an environment variable achieves the
  same UX with materially better security hygiene.
- A generic `remoteLlmApiKeyEnvVar` config field letting the operator name
  their own env var — considered, but adds configuration surface for a
  single supported provider; deferred as unnecessary until a second remote
  provider is ever added.

## Decision 6 — `POST /sessions/{id}/messages` becomes a Server-Sent-Events stream

**Decision**: The existing endpoint's handler becomes `async def`, returning
a `StreamingResponse` with media type `text/event-stream`. Each answer
fragment is sent as one SSE event (`data: {"fragment": "..."}\n\n`); the
final event carries the complete result
(`data: {"answer": ..., "citedSymbolIds": [...], "citedFilePaths": [...]}\n\n`,
distinguished by an `event: done` line) — the same fields
`AskQuestionResponse` already exposes today, so a caller that only reads the
last event gets exactly what today's single-block response gave it. On a
mid-stream failure, the connection ends with an `event: error` SSE event
carrying the same `{code, message}` shape `ApiErrorResponse` already uses.
`GET /sessions/{id}/messages` (history) is unaffected — it already returns
complete, persisted messages and has nothing to stream.

**Rationale**: FR-001/FR-002 make streaming the way generation works, not an
optional mode — consistent with "ne doit plus être bloquante de bout en
bout" (must no longer be blocking end-to-end), this changes the existing
endpoint rather than adding a parallel one. SSE (not WebSockets or raw
chunked JSON) is the standard fit for a one-way, request-triggered stream of
text over plain HTTP, needs no extra dependency (`StreamingResponse` is
already part of Starlette/FastAPI), and degrades gracefully — a client that
just waits for the connection to close and reads the last event effectively
gets today's synchronous behavior back, satisfying spec.md's Assumption
that a complete-answer caller isn't left without a path to one. This is a
**breaking change** to the 014/025 HTTP contract's response shape for this
one endpoint — documented explicitly in `contracts/chat-streaming-api-delta.md`
rather than silently reinterpreted.

**Alternatives considered**:
- A second, new endpoint (e.g. `POST .../messages/stream`) alongside the
  unchanged original — rejected: leaves two code paths (streamed and
  blocking) to keep behaviorally identical forever, and contradicts the
  request's "ne doit plus être bloquante" framing, which describes a change
  to the existing behavior, not an added alternative.
- WebSockets — rejected as unnecessary complexity for a one-directional,
  single-request/single-response-stream interaction; SSE is simpler and
  sufficient.

## Decision 7 — Test-only `pytest-asyncio`, no runtime asyncio test framework needed

**Decision**: Add `pytest-asyncio` to `[project.optional-dependencies].test`
in `pyproject.toml`. Unit tests exercising `generateStream`/`askStream`
directly use `@pytest.mark.asyncio`; HTTP-contract tests continue using
FastAPI's `TestClient`, which already drives async route handlers and
consumes `StreamingResponse` bodies synchronously from the test's
perspective — no `pytest-asyncio` needed at that layer.

**Rationale**: `anyio` is already installed (transitively, via
httpx/starlette) and could offer similar pytest support, but it isn't a
*direct*, pinned dependency of this project — relying on it for test
infrastructure would be relying on an unpinned transitive package that a
future httpx/starlette upgrade could change or drop. `pytest-asyncio` is the
standard, explicit, well-documented choice; adding it as a test-only
dependency (alongside the existing test-only `pytest`) doesn't touch runtime
dependencies at all, so it doesn't implicate constitution 2.6.

**Alternatives considered**:
- Rely on the already-installed `anyio` pytest plugin — rejected per the
  unpinned-transitive-dependency risk above.
- Hand-roll `asyncio.run()` inside each test to collect a generator's
  output into a list — rejected as unnecessarily awkward for tests that
  need to assert something *between* yields (e.g. "the first fragment
  arrives before the rest," directly relevant to SC-002's own testing
  needs), which a flattening collect-everything approach can't express.
