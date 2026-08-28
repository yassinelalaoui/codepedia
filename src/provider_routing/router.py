from __future__ import annotations

import random
import time
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
    # "retried" is a wait, not a switch: the same provider is about to be
    # called again after a rate-limit backoff (see `BackoffPolicy`). Only
    # "unavailable" means this provider was actually abandoned.
    outcome: str  # "success" | "unavailable" | "retried"
    reason: Optional[str]
    timestamp: str


@dataclass(frozen=True, slots=True)
class BackoffPolicy:
    """How long to wait on a rate limit before giving up on a provider
    (contracts/provider-routing-backoff-delta.md `BackoffPolicy`).

    Indexing calls every provider from a thread pool, which makes HTTP 429 the
    expected steady state rather than an exception. Switching provider on the
    first 429 - what this executor did before this policy existed - burns the
    whole chain in seconds under concurrency, because the limit is on the key,
    not on the provider's health. Waiting is what actually clears a rate limit,
    so the same provider is retried first and only abandoned once `maxWaits`
    waits have not helped.
    """

    initialDelaySeconds: float = 1.0
    factor: float = 2.0
    maxDelaySeconds: float = 30.0
    maxWaits: int = 4

    def __post_init__(self) -> None:
        if self.initialDelaySeconds < 0:
            raise ValueError("initialDelaySeconds must not be negative")
        if self.factor < 1:
            raise ValueError("factor must be at least 1")
        if self.maxDelaySeconds < 0:
            raise ValueError("maxDelaySeconds must not be negative")
        if self.maxWaits < 0:
            raise ValueError("maxWaits must not be negative")

    def delay_for(self, wait_index: int) -> float:
        """Seconds to sleep before retry number `wait_index` (0-based).

        Exponential, capped, with full jitter - the delay is drawn uniformly
        from `[0, capped]` rather than used as-is. Without jitter, N pool
        threads that hit the same 429 would wake together and re-hit the limit
        in lockstep; drawing from the interval spreads them out.
        """
        capped = min(self.initialDelaySeconds * (self.factor**wait_index), self.maxDelaySeconds)
        return random.uniform(0.0, capped)


class BackoffNotifier(Protocol):
    def __call__(
        self, *, stage: str, provider: str, delay_seconds: float, wait_number: int, max_waits: int
    ) -> None: ...


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
        backoff: Optional[BackoffPolicy] = None,
        sleep: Callable[[float], None] = time.sleep,
        on_backoff: Optional[BackoffNotifier] = None,
    ) -> None:
        """`sleep` is injected so a caller - in practice a test - can prove the
        backoff schedule without spending it in real seconds; `on_backoff` is
        how a wait becomes visible to the user, since a wait deliberately
        writes nothing to `engine_failover_log` (that table means "a switch
        happened", and a wait is the opposite of one)."""
        if not chain:
            raise ValueError("chain must be non-empty")
        self.stage = stage
        self.chain: tuple[tuple[ProviderRef, EngineT], ...] = tuple(chain)
        self._failover_log = failover_log
        self._backoff = backoff if backoff is not None else BackoffPolicy()
        self._sleep = sleep
        self._on_backoff = on_backoff
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

    def _announce_backoff(self, *, ref: ProviderRef, delay_seconds: float, wait_number: int) -> None:
        if self._on_backoff is None:
            return
        self._on_backoff(
            stage=self.stage,
            provider=str(ref),
            delay_seconds=delay_seconds,
            wait_number=wait_number,
            max_waits=self._backoff.maxWaits,
        )

    def run(self, call: Callable[[EngineT], T]) -> FailoverResult[T]:
        """Synchronous path (embeddings' `embed`, summary's `generate`).

        A `rate_limited` failure waits and retries the *same* provider up to
        `BackoffPolicy.maxWaits` times before the chain moves on; every other
        classified failure switches immediately, exactly as before. A rate
        limit is a property of the key over time, not of the provider, so the
        next provider in the chain is no more likely to answer - only waiting
        is. `network_error` and `auth_failed` keep switching at once: neither
        repairs itself within a few seconds of sleeping.
        """
        attempts: list[FailoverAttempt] = []
        for index, (ref, engine) in enumerate(self.chain):
            waits_used = 0
            while True:
                try:
                    value = call(engine)
                except Exception as exc:  # noqa: BLE001 - classified below
                    reason = classify_failure(exc)
                    if reason == "unknown":
                        self.attempts = tuple(attempts)
                        raise
                    if reason == "rate_limited" and waits_used < self._backoff.maxWaits:
                        delay = self._backoff.delay_for(waits_used)
                        waits_used += 1
                        attempts.append(
                            FailoverAttempt(providerRef=ref, outcome="retried", reason=reason, timestamp=_utc_now())
                        )
                        self._announce_backoff(ref=ref, delay_seconds=delay, wait_number=waits_used)
                        self._sleep(delay)
                        continue
                    attempts.append(FailoverAttempt(providerRef=ref, outcome="unavailable", reason=reason, timestamp=_utc_now()))
                    next_ref = self.chain[index + 1][0] if index + 1 < len(self.chain) else None
                    self._log_switch(attempted=ref, result=next_ref, reason=reason)
                    break
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
        failure from that same stream propagates instead of retrying.

        Deliberately carries no rate-limit backoff, unlike `run`: this path
        serves an interactive answer, where sleeping seconds before the first
        token is worse than switching provider at once. Backoff exists for
        indexing's batch throughput, which is not what this path does."""
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
