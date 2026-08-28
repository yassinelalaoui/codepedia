"""End-to-end provider failover: a chain with a forced-unavailable first
provider still produces an answer via the next one, with exactly one
`engine_failover_log` row per actual switch (spec User Story 3)."""

from __future__ import annotations

import pytest

from local_llm.errors import MissingApiKeyError, RateLimitedError, RemoteServiceUnavailableError
from provider_routing import (
    BackoffPolicy,
    FailoverExecutor,
    FailoverExhaustedError,
    PathFailoverLog,
    ProviderRef,
    list_failover_events,
)
from repository_metadata.sqlite_store import connect

# What this file asserts is the *logging* of a switch, not how long the
# executor is willing to wait before making one. A rate limit is now waited
# out first (`BackoffPolicy`), so without spending that budget instantly here
# the parametrized rate-limited case below would sleep for real seconds while
# proving nothing it does not already prove. The switch it does assert still
# happens - the waits are exhausted first, exactly as in production.
_NO_WAITING = BackoffPolicy(initialDelaySeconds=0.0, maxWaits=1)


class _WorkingEngine:
    def isAvailable(self) -> bool:
        return True

    def run(self) -> str:
        return "ok"


class _BrokenEngine:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def isAvailable(self) -> bool:
        return False

    def run(self):
        raise self._exc


@pytest.mark.parametrize(
    "exc, expected_reason",
    [
        (RemoteServiceUnavailableError("down", endpointUrl="https://x", modelName="m"), "network_error"),
        (RateLimitedError("rate limited", endpointUrl="https://x", modelName="m"), "rate_limited"),
        (MissingApiKeyError("no key", endpointUrl="https://x", modelName="m"), "auth_failed"),
    ],
)
def test_two_provider_chain_fails_over_and_logs_exactly_one_switch(tmp_path, exc, expected_reason):
    db_path = tmp_path / "repository-metadata.sqlite"
    connection = connect(db_path)
    failover_log = PathFailoverLog(db_path, connect)

    broken = _BrokenEngine(exc)
    working = _WorkingEngine()
    executor = FailoverExecutor(
        "chat",
        ((ProviderRef.parse("groq:m1"), broken), (ProviderRef.parse("local:m2"), working)),
        failover_log=failover_log,
        backoff=_NO_WAITING,
    )

    result = executor.run(lambda engine: engine.run())

    assert result.value == "ok"
    assert result.providerUsed == ProviderRef.parse("local:m2")

    events = list_failover_events(connection, stage="chat")
    connection.close()
    assert len(events) == 1
    assert events[0].attemptedProvider == "groq:m1"
    assert events[0].resultProvider == "local:m2"
    assert events[0].reason == expected_reason

    # A third provider absent from the chain must never be attempted.
    assert len(executor.chain) == 2


def test_every_provider_unavailable_raises_and_logs_null_result_provider(tmp_path):
    db_path = tmp_path / "repository-metadata.sqlite"
    connection = connect(db_path)
    failover_log = PathFailoverLog(db_path, connect)

    first = _BrokenEngine(RemoteServiceUnavailableError("down", endpointUrl="https://x", modelName="m"))
    second = _BrokenEngine(MissingApiKeyError("no key", endpointUrl="https://x", modelName="m"))
    executor = FailoverExecutor(
        "summary",
        ((ProviderRef.parse("groq:m1"), first), (ProviderRef.parse("openai:m2"), second)),
        failover_log=failover_log,
    )

    with pytest.raises(FailoverExhaustedError):
        executor.run(lambda engine: engine.run())

    events = list_failover_events(connection, stage="summary")
    connection.close()
    assert len(events) == 2
    assert events[0].resultProvider is None  # most-recent-first: the final, exhausting attempt
    assert events[1].resultProvider == "openai:m2"
