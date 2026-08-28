"""A rate limit must be waited out, not treated as a dead provider
(contracts/provider-routing-backoff-delta.md).

Before `BackoffPolicy` existed, `FailoverExecutor.run` abandoned a provider on
its first HTTP 429 and moved down the chain. That was survivable while
indexing was sequential and a 429 was rare; once summarization and embedding
run from thread pools, a 429 is the expected steady state, and switching
immediately burns the whole chain in seconds over a limit that only time
clears.
"""

from __future__ import annotations

import pytest

from local_llm.errors import RateLimitedError, RemoteServiceUnavailableError
from provider_routing import BackoffPolicy, FailoverExecutor, FailoverExhaustedError, ProviderRef
from provider_routing.failover_log import PathFailoverLog, list_failover_events
from repository_metadata.sqlite_store import connect


class _RecordingSleep:
    """Stands in for `time.sleep` so the schedule is asserted, not spent."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


class _Engine:
    """Raises `failures` in order, then succeeds."""

    def __init__(self, *failures: Exception) -> None:
        self._failures = list(failures)
        self.calls = 0

    def isAvailable(self) -> bool:
        return True

    def run(self) -> str:
        self.calls += 1
        if self._failures:
            raise self._failures.pop(0)
        return "ok"


class _AlwaysRateLimited:
    def __init__(self) -> None:
        self.calls = 0

    def isAvailable(self) -> bool:
        return True

    def run(self) -> str:
        self.calls += 1
        raise _rate_limited()


def _rate_limited() -> RateLimitedError:
    return RateLimitedError("HTTP 429", endpointUrl="https://api.groq.com", modelName="m")


def _unavailable() -> RemoteServiceUnavailableError:
    return RemoteServiceUnavailableError("unreachable", endpointUrl="https://api.groq.com", modelName="m")


def test_a_rate_limit_waits_and_retries_the_same_provider_instead_of_switching(tmp_path) -> None:
    """The behaviour this whole feature depends on.

    Two 429s then success: the executor must sleep twice against the *first*
    provider and return its answer. The second provider must never be called,
    and nothing may be written to `engine_failover_log` - no switch happened.
    """
    db_path = tmp_path / "repository-metadata.sqlite"
    connection = connect(db_path)
    sleep = _RecordingSleep()
    limited = _Engine(_rate_limited(), _rate_limited())
    fallback = _Engine()

    executor = FailoverExecutor(
        "summary",
        ((ProviderRef.parse("groq:m1"), limited), (ProviderRef.parse("local:m2"), fallback)),
        failover_log=PathFailoverLog(db_path, connect),
        sleep=sleep,
    )

    result = executor.run(lambda engine: engine.run())

    assert result.value == "ok"
    assert result.providerUsed == ProviderRef.parse("groq:m1"), "a rate limit must not switch provider"
    assert fallback.calls == 0, "the next provider must not be attempted while the first is only rate limited"
    assert limited.calls == 3, "two rejected attempts plus the one that succeeded"

    assert len(sleep.delays) == 2, "each 429 must be followed by a wait"
    # Exponential (1s then 2s) with full jitter, so each delay lands anywhere
    # inside its own capped interval.
    assert 0 <= sleep.delays[0] <= 1.0
    assert 0 <= sleep.delays[1] <= 2.0

    events = list_failover_events(connection, stage="summary")
    connection.close()
    assert events == (), "a wait is not a provider switch and must not be logged as one"


def test_backoff_waits_are_reported_in_the_attempt_trail() -> None:
    sleep = _RecordingSleep()
    limited = _Engine(_rate_limited())
    executor = FailoverExecutor(
        "summary", ((ProviderRef.parse("groq:m1"), limited),), sleep=sleep
    )

    result = executor.run(lambda engine: engine.run())

    assert [attempt.outcome for attempt in result.attempts] == ["retried", "success"]
    assert result.attempts[0].reason == "rate_limited"


def test_backoff_waits_are_announced_to_the_caller() -> None:
    """Constitution 2.3 keeps switches visible; a wait has to be visible too,
    or a run slowed by a rate limit is indistinguishable from a hung one."""
    announced: list[dict[str, object]] = []
    executor = FailoverExecutor(
        "embeddings",
        ((ProviderRef.parse("openai:m1"), _Engine(_rate_limited())),),
        sleep=_RecordingSleep(),
        on_backoff=lambda **kwargs: announced.append(kwargs),
    )

    executor.run(lambda engine: engine.run())

    assert len(announced) == 1
    assert announced[0]["stage"] == "embeddings"
    assert announced[0]["provider"] == "openai:m1"
    assert announced[0]["wait_number"] == 1
    assert announced[0]["max_waits"] == BackoffPolicy().maxWaits


def test_a_provider_is_abandoned_after_the_wait_budget_and_logs_exactly_one_switch(tmp_path) -> None:
    """Waiting is bounded: a limit that never clears still reaches the next
    provider, and that switch is logged exactly once - not once per wait."""
    db_path = tmp_path / "repository-metadata.sqlite"
    connection = connect(db_path)
    sleep = _RecordingSleep()
    limited = _AlwaysRateLimited()
    fallback = _Engine()

    executor = FailoverExecutor(
        "summary",
        ((ProviderRef.parse("groq:m1"), limited), (ProviderRef.parse("local:m2"), fallback)),
        failover_log=PathFailoverLog(db_path, connect),
        backoff=BackoffPolicy(initialDelaySeconds=0.0, maxWaits=3),
        sleep=sleep,
    )

    result = executor.run(lambda engine: engine.run())

    assert result.providerUsed == ProviderRef.parse("local:m2")
    assert len(sleep.delays) == 3, "exactly maxWaits waits before giving up on the provider"
    assert limited.calls == 4, "three retried attempts plus the initial one"

    events = list_failover_events(connection, stage="summary")
    connection.close()
    assert len(events) == 1, "three waits then one switch is still one switch"
    assert events[0].attemptedProvider == "groq:m1"
    assert events[0].resultProvider == "local:m2"
    assert events[0].reason == "rate_limited"


def test_a_non_rate_limit_failure_still_switches_immediately() -> None:
    """Backoff is scoped to rate limits. An unreachable host or a rejected key
    does not repair itself within seconds of sleeping, so those keep the
    original immediate-switch behaviour."""
    sleep = _RecordingSleep()
    broken = _Engine(_unavailable())
    fallback = _Engine()

    executor = FailoverExecutor(
        "chat",
        ((ProviderRef.parse("groq:m1"), broken), (ProviderRef.parse("local:m2"), fallback)),
        sleep=sleep,
    )

    result = executor.run(lambda engine: engine.run())

    assert result.providerUsed == ProviderRef.parse("local:m2")
    assert sleep.delays == [], "a network failure must not be waited out"
    assert broken.calls == 1


def test_every_provider_rate_limited_still_exhausts_the_chain() -> None:
    first = _AlwaysRateLimited()
    second = _AlwaysRateLimited()
    executor = FailoverExecutor(
        "summary",
        ((ProviderRef.parse("groq:m1"), first), (ProviderRef.parse("groq:m2"), second)),
        backoff=BackoffPolicy(initialDelaySeconds=0.0, maxWaits=1),
        sleep=_RecordingSleep(),
    )

    with pytest.raises(FailoverExhaustedError):
        executor.run(lambda engine: engine.run())

    assert first.calls == 2 and second.calls == 2


def test_a_zero_wait_budget_reproduces_the_pre_backoff_behaviour() -> None:
    sleep = _RecordingSleep()
    limited = _AlwaysRateLimited()
    fallback = _Engine()
    executor = FailoverExecutor(
        "summary",
        ((ProviderRef.parse("groq:m1"), limited), (ProviderRef.parse("local:m2"), fallback)),
        backoff=BackoffPolicy(maxWaits=0),
        sleep=sleep,
    )

    result = executor.run(lambda engine: engine.run())

    assert result.providerUsed == ProviderRef.parse("local:m2")
    assert sleep.delays == []
    assert limited.calls == 1


def test_delays_grow_exponentially_and_stop_at_the_cap() -> None:
    policy = BackoffPolicy(initialDelaySeconds=1.0, factor=2.0, maxDelaySeconds=4.0, maxWaits=5)
    caps = [1.0, 2.0, 4.0, 4.0, 4.0]
    for index, cap in enumerate(caps):
        assert 0 <= policy.delay_for(index) <= cap
