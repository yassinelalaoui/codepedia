# LLMEngine Interface Contract

## Purpose

Define the shared interface both `LocalLLMEngine` and `GroqLLMEngine` must
satisfy (`local_llm/protocol.py`, a structural `typing.Protocol` — no
inheritance required), and the guarantees the factory that builds one of
them must uphold.

## Core operations

### `isAvailableLocally`

Inputs: none.

Expected behavior:
- Returns `True` only when the currently configured engine (local service,
  or the configured remote API) is reachable and its configured model is
  usable.
- Name is unchanged from the pre-streaming interface for both engines
  (research.md Decision 2) — despite the name, this describes "the
  currently configured engine," not literally "a local one," for
  `GroqLLMEngine`.

### `checkAvailability`

Inputs: none.

Expected behavior:
- Returns an `AvailabilityStatus` (`available`, `serviceReachable`,
  `modelInstalled`, `message`) — the same shape for both engines.
- For `LocalLLMEngine`: unchanged from today (008) — service reachability,
  then whether the named model is installed.
- For `GroqLLMEngine`: `serviceReachable` reflects whether the API endpoint
  responds (including authentication with `GROQ_API_KEY`); `modelInstalled`
  reflects whether the configured model name is one Groq recognizes.
- `message` is always specific enough to guide the operator to a fix
  (missing/invalid API key, unreachable endpoint, unrecognized model),
  mirroring the existing local engine's message quality.

### `generate`

Inputs: `prompt: str | PromptEnvelope`.

Expected behavior:
- Synchronous; returns the complete generated text as a single `str`.
- Internally drains `generateStream` and concatenates — behaviorally
  identical output to calling `generateStream` and joining every yielded
  fragment, for both engines.
- Raises the same error types it always has if the engine is unavailable
  before generation starts.

### `generateStream`

Inputs: `prompt: str | PromptEnvelope`.

Expected behavior:
- `async def`, returns an `AsyncIterator[str]`.
- Raises before yielding anything if the engine is unavailable (mirrors
  `generate`'s existing pre-flight check — no engine call is attempted if
  `checkAvailability().available` is `False`).
- Yields text fragments in generation order as they arrive from the
  transport; concatenating every yielded fragment in order reconstructs the
  complete answer text.
- May raise mid-stream (e.g. a transport error, or the remote API cutting
  off) — callers must not assume every stream reaches a clean end.
- Never partially yields, then silently stops without either completing or
  raising.

## Engine selection contract (`local_llm.create_llm_engine`)

Inputs: `config: CLIConfiguration`.

Expected behavior:
- Returns exactly one engine instance: `LocalLLMEngine` when
  `config.llmProvider == "local"` (the default), `GroqLLMEngine` when
  `config.llmProvider == "groq"`.
- Never returns a composite/wrapping engine that tries one and falls back
  to the other — there is no code path in this factory, or anywhere else,
  that switches engines based on availability (constitution 2.3 v2.0.0,
  FR-014). Unavailability of the configured engine is reported via
  `checkAvailability`/`isAvailableLocally` as it always has been; it is
  never masked by silently trying the other engine.

## Non-goals

- No multi-engine "try in order" mode — explicitly forbidden by the
  constitution, not merely unimplemented.
- No engine auto-detection ("use Groq if `GROQ_API_KEY` happens to be set")
  — `llmProvider` must be explicitly configured; an unset provider always
  means `"local"`, regardless of environment variables present.
