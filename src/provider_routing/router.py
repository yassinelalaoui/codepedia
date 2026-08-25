from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Generic,
    Optional,
    Protocol,
    Sequence,
    TypeVar,
)

from .chain import ProviderRef
from .classify import classify_failure
from .errors import FailoverExhaustedError

EngineT = TypeVar("EngineT")
T = TypeVar("T")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class FailoverAttempt:
    """One provider's outcome during a single `FailoverExecutor` call
    (data-model.md `FailoverAttempt`)."""

    providerRef: ProviderRef
    outcome: str  # "success" | "unavailable"
    reason: Optional[str]
    timestamp: str


@dataclass(frozen=True, slots=True)
class FailoverResult(Generic[T]):
    """Returned by `FailoverExecutor.run` (data-model.md `FailoverResult[T]`)."""

    value: T
    providerUsed: ProviderRef
    attempts: tuple[FailoverAttempt, ...]


class FailoverLogWriter(Protocol):
    def __call__(
        self, *, stage: str, attempted_provider: str, result_provider: Optional[str], reason: str
    ) -> None: ...


def _exhausted_error(stage: str, chain: Sequence[tuple[ProviderRef, Any]], attempts: Sequence[FailoverAttempt]) -> FailoverExhaustedError:
    last_reason = attempts[-1].reason if attempts else "unknown"
    attempted_refs = tuple(str(ref) for ref, _ in chain)
    return FailoverExhaustedError(
        stage=stage,
        attempted=attempted_refs,
        message=(
            f"Every provider in the '{stage}' chain is unavailable ({', '.join(attempted_refs)}); "
            f"last reason: {last_reason}."
        ),
    )


class FailoverExecutor(Generic[EngineT]):
    """Stage-agnostic retry/failover orchestrator (contracts/provider-protocols.md).

    `chain` is already resolved to concrete `(ProviderRef, engine_instance)`
    pairs by `provider_routing.factory` before this class ever sees it - it
    never imports `local_llm`/`embedding_engine` itself and works
    identically whether `EngineT` is an `LLMEngine` or an `EmbeddingProvider`.
    """

    def __init__(
        self,
        stage: str,
        chain: Sequence[tuple[ProviderRef, EngineT]],
        *,
        failover_log: Optional[FailoverLogWriter] = None,
    ) -> None:
        if not chain:
            raise ValueError("chain must be non-empty")
        self.stage = stage
        self.chain: tuple[tuple[ProviderRef, EngineT], ...] = tuple(chain)
        self._failover_log = failover_log
        self.providerUsed: Optional[ProviderRef] = None
        self.attempts: tuple[FailoverAttempt, ...] = ()

    def isAvailable(self) -> bool:
        """Aggregate availability check: True if any chain entry reports
        `isAvailable()` True (research.md §13 - lets every existing
        pre-flight check keep working unchanged once handed a
        `FailoverExecutor` instead of a raw engine)."""
        return any(engine.isAvailable() for _, engine in self.chain)

    @property
    def result(self) -> FailoverResult[None]:
        return FailoverResult(value=None, providerUsed=self.providerUsed, attempts=self.attempts)

    def _log_switch(self, *, attempted: ProviderRef, result: Optional[ProviderRef], reason: str) -> None:
        if self._failover_log is None:
            return
        self._failover_log(
            stage=self.stage,
            attempted_provider=str(attempted),
            result_provider=str(result) if result is not None else None,
            reason=reason,
        )

    def run(self, call: Callable[[EngineT], T]) -> FailoverResult[T]:
        """Synchronous path (embeddings' `embed`, summary's `generate`)."""
        attempts: list[FailoverAttempt] = []
        for index, (ref, engine) in enumerate(self.chain):
            try:
                value = call(engine)
            except Exception as exc:  # noqa: BLE001 - classified below
                reason = classify_failure(exc)
                if reason == "unknown":
                    self.attempts = tuple(attempts)
                    raise
                attempts.append(FailoverAttempt(providerRef=ref, outcome="unavailable", reason=reason, timestamp=_utc_now()))
                next_ref = self.chain[index + 1][0] if index + 1 < len(self.chain) else None
                self._log_switch(attempted=ref, result=next_ref, reason=reason)
                continue
            attempts.append(FailoverAttempt(providerRef=ref, outcome="success", reason=None, timestamp=_utc_now()))
            self.attempts = tuple(attempts)
            self.providerUsed = ref
            return FailoverResult(value=value, providerUsed=ref, attempts=self.attempts)
        self.attempts = tuple(attempts)
        raise _exhausted_error(self.stage, self.chain, attempts)

    async def stream(self, call: Callable[[EngineT], AsyncIterator[str]]) -> AsyncIterator[str]:
        """Streaming path (chat's `generateStream`). Only fails over if the
        underlying async generator raises before yielding its first
        fragment (research.md §7); once a fragment has been yielded, a later
        failure from that same stream propagates instead of retrying."""
        attempts: list[FailoverAttempt] = []
        for index, (ref, engine) in enumerate(self.chain):
            generator = call(engine)
            try:
                first_fragment = await generator.__anext__()
            except StopAsyncIteration:
                attempts.append(FailoverAttempt(providerRef=ref, outcome="success", reason=None, timestamp=_utc_now()))
                self.attempts = tuple(attempts)
                self.providerUsed = ref
                return
            except Exception as exc:  # noqa: BLE001 - classified below
                reason = classify_failure(exc)
                if reason == "unknown":
                    self.attempts = tuple(attempts)
                    raise
                attempts.append(FailoverAttempt(providerRef=ref, outcome="unavailable", reason=reason, timestamp=_utc_now()))
                next_ref = self.chain[index + 1][0] if index + 1 < len(self.chain) else None
                self._log_switch(attempted=ref, result=next_ref, reason=reason)
                continue

            attempts.append(FailoverAttempt(providerRef=ref, outcome="success", reason=None, timestamp=_utc_now()))
            self.attempts = tuple(attempts)
            self.providerUsed = ref
            yield first_fragment
            # Once the first fragment shipped, a later failure propagates
            # exactly as it does today - no retry against the next provider.
            async for fragment in generator:
                yield fragment
            return
        self.attempts = tuple(attempts)
        raise _exhausted_error(self.stage, self.chain, attempts)
