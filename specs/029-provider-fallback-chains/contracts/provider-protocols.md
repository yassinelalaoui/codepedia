# Contract: Provider Protocols (`local_llm.LLMEngine`, `embedding_engine.EmbeddingProvider`)

**Status**: `LLMEngine` extended (one new method); `EmbeddingProvider` is new.

## `local_llm.LLMEngine` (extended)

```python
@runtime_checkable
class LLMEngine(Protocol):
    def isAvailableLocally(self) -> bool: ...   # unchanged - existing call sites keep using this
    def isAvailable(self) -> bool: ...           # NEW - delegates to isAvailableLocally() on every implementation
    def checkAvailability(self) -> AvailabilityStatus: ...
    def generate(self, prompt: str | PromptEnvelope) -> str: ...
    def generateStream(self, prompt: str | PromptEnvelope) -> AsyncIterator[str]: ...
```

Implementations: `LocalLLMEngine` (unchanged behavior, `isAvailable` new),
`GroqLLMEngine` (unchanged behavior, `isAvailable` new).

## `embedding_engine.EmbeddingProvider` (new)

```python
@runtime_checkable
class EmbeddingProvider(Protocol):
    def isAvailable(self) -> bool: ...
    def checkAvailability(self) -> EmbeddingAvailabilityStatus: ...
    def embed(self, text: str) -> Vector: ...
```

Implementations:
- `EmbeddingEngine` (existing, local/Ollama-backed) — gains `isAvailable()`
  (`return self.isAvailableLocally()`); everything else unchanged.
- `OpenAIEmbeddingProvider` (new, `embedding_engine/openai_provider.py`) —
  calls OpenAI's `/v1/embeddings` with the configured model
  (default `text-embedding-3-small`), authenticated via `OPENAI_API_KEY`.
  Raises the same `embedding_engine.errors.EmbeddingError` family
  (`ServiceUnavailableError`, a new `MissingApiKeyError`, the new
  `RateLimitedError`, `EmbeddingFailedError`) as the local engine, so callers
  needn't distinguish which implementation raised.

## `FailoverExecutor` (new, `provider_routing.router`)

```python
class FailoverExecutor(Generic[EngineT]):
    def __init__(self, stage: Literal["embeddings", "summary", "chat"], chain: Sequence[tuple[ProviderRef, EngineT]], *, failover_log: FailoverLogWriter | None = None) -> None: ...

    def isAvailable(self) -> bool:
        """Aggregate availability check: True if ANY provider in the chain
        reports `isAvailable()` True. Lets every existing pre-flight check
        that calls `.isAvailable()`/`.isAvailableLocally()` on a single
        engine keep working unchanged when handed a `FailoverExecutor`
        instead (post-analysis fix — see research.md §13; `ensure_local_dependencies_available`
        in `chat/session.py` and `check_ai_dependencies` in `cli/availability.py`
        both call this uniformly now, regardless of which they're given)."""

    def run(self, call: Callable[[EngineT], T]) -> FailoverResult[T]:
        """Synchronous path (embeddings' `embed`, summary's `generate`).
        Tries `call(engine)` against each (ref, engine) pair in order,
        classifying any raised engine error via `provider_routing.classify`.
        Raises `FailoverExhaustedError` if every entry fails. Every actual
        switch appends one `engine_failover_log` row via `failover_log`."""

    def stream(self, call: Callable[[EngineT], AsyncIterator[str]]) -> AsyncIterator[str]:
        """Streaming path (chat's `generateStream`). Fails over only if the
        underlying async generator raises before yielding its first item
        (research.md #7); once a fragment has been yielded from a given
        provider, a later failure from that same stream propagates instead
        of retrying. After the generator is exhausted (or raises
        FailoverExhaustedError before yielding anything), `.result` holds
        the `FailoverResult[None]` (providerUsed/attempts) for the caller to
        read."""
```

Both `run` and `stream` are stage-agnostic: `chain` is already resolved to
concrete `(ProviderRef, engine_instance)` pairs by
`provider_routing.factory` before `FailoverExecutor` ever sees it, so the
executor itself never imports `local_llm` or `embedding_engine` and works
identically whether `EngineT` is an `LLMEngine` or an `EmbeddingProvider`.

## `FailoverExhaustedError` (new, `provider_routing.errors`)

```python
@dataclass(frozen=True)
class FailoverExhaustedError(RuntimeError):
    kind: str = "failover_exhausted"   # slots into chat_api's existing _error_code_for(exc) unchanged
    stage: str
    attempted: tuple[str, ...]          # ProviderRef strings, in the order tried
    message: str
```

Raised by `FailoverExecutor` when every provider in a stage's chain is
unavailable for one operation (spec FR-007) — the "explicit detection and
guidance" the spec requires: `message` names every attempted provider and
the last reason, so CLI/API error output (already rendering `.message` for
every other engine error) needs no special-casing to be informative here
too.
