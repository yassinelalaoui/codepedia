"""Contract tests for `provider_routing.FailoverExecutor`
(contracts/provider-protocols.md)."""

from __future__ import annotations

import asyncio

import pytest

from local_llm.errors import RemoteServiceUnavailableError, MissingApiKeyError
from provider_routing import FailoverExecutor, FailoverExhaustedError, ProviderRef


class _Engine:
    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        self.calls = 0

    def isAvailable(self) -> bool:
        return self._available


class _FailingEngine(_Engine):
    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self._exc = exc

    def run(self) -> str:
        self.calls += 1
        raise self._exc


class _SucceedingEngine(_Engine):
    def run(self) -> str:
        self.calls += 1
        return "ok"


def _unavailable_error() -> RemoteServiceUnavailableError:
    return RemoteServiceUnavailableError("unreachable", endpointUrl="https://example.com", modelName="m")


def test_run_tries_each_provider_in_order_until_one_succeeds() -> None:
    failing = _FailingEngine(_unavailable_error())
    succeeding = _SucceedingEngine()
    chain = ((ProviderRef.parse("groq:m1"), failing), (ProviderRef.parse("local:m2"), succeeding))
    executor = FailoverExecutor("chat", chain)

    result = executor.run(lambda engine: engine.run())

    assert result.value == "ok"
    assert result.providerUsed == ProviderRef.parse("local:m2")
    assert failing.calls == 1
    assert succeeding.calls == 1
    assert [attempt.outcome for attempt in result.attempts] == ["unavailable", "success"]


def test_run_never_attempts_a_provider_outside_the_chain() -> None:
    only = _SucceedingEngine()
    executor = FailoverExecutor("chat", ((ProviderRef.parse("local:m1"), only),))

    result = executor.run(lambda engine: engine.run())

    assert result.providerUsed == ProviderRef.parse("local:m1")
    assert only.calls == 1


def test_run_raises_failover_exhausted_when_every_provider_fails() -> None:
    first = _FailingEngine(_unavailable_error())
    second = _FailingEngine(MissingApiKeyError("no key", endpointUrl="https://example.com", modelName="m"))
    chain = ((ProviderRef.parse("groq:m1"), first), (ProviderRef.parse("openai:m2"), second))
    executor = FailoverExecutor("embeddings", chain)

    with pytest.raises(FailoverExhaustedError) as excinfo:
        executor.run(lambda engine: engine.run())

    assert excinfo.value.stage == "embeddings"
    assert excinfo.value.attempted == ("groq:m1", "openai:m2")
    assert excinfo.value.kind == "failover_exhausted"


def test_run_does_not_retry_an_unclassified_exception() -> None:
    first = _FailingEngine(RuntimeError("boom"))
    second = _SucceedingEngine()
    chain = ((ProviderRef.parse("local:m1"), first), (ProviderRef.parse("local:m2"), second))
    executor = FailoverExecutor("chat", chain)

    with pytest.raises(RuntimeError):
        executor.run(lambda engine: engine.run())

    assert second.calls == 0


def test_is_available_true_iff_any_chain_entry_is_available() -> None:
    both_down = FailoverExecutor(
        "chat", ((ProviderRef.parse("local:m1"), _Engine(available=False)), (ProviderRef.parse("groq:m2"), _Engine(available=False)))
    )
    one_up = FailoverExecutor(
        "chat", ((ProviderRef.parse("local:m1"), _Engine(available=False)), (ProviderRef.parse("groq:m2"), _Engine(available=True)))
    )

    assert both_down.isAvailable() is False
    assert one_up.isAvailable() is True


class _StreamEngine:
    def __init__(self, fragments=None, *, fail_before_first: Exception | None = None, fail_after_first: Exception | None = None):
        self._fragments = fragments or []
        self._fail_before_first = fail_before_first
        self._fail_after_first = fail_after_first

    def isAvailable(self) -> bool:
        return True

    async def stream(self):
        if self._fail_before_first is not None:
            raise self._fail_before_first
        for index, fragment in enumerate(self._fragments):
            yield fragment
            if index == 0 and self._fail_after_first is not None:
                raise self._fail_after_first


def test_stream_fails_over_only_before_first_fragment() -> None:
    failing = _StreamEngine(fail_before_first=_unavailable_error())
    succeeding = _StreamEngine(fragments=["a", "b"])
    chain = ((ProviderRef.parse("groq:m1"), failing), (ProviderRef.parse("local:m2"), succeeding))
    executor = FailoverExecutor("chat", chain)

    async def _drain():
        return [fragment async for fragment in executor.stream(lambda engine: engine.stream())]

    fragments = asyncio.run(_drain())

    assert fragments == ["a", "b"]
    assert executor.providerUsed == ProviderRef.parse("local:m2")


def test_stream_does_not_retry_after_first_fragment_yielded() -> None:
    engine = _StreamEngine(fragments=["a"], fail_after_first=_unavailable_error())
    never_called = _StreamEngine(fragments=["never"])
    chain = ((ProviderRef.parse("local:m1"), engine), (ProviderRef.parse("local:m2"), never_called))
    executor = FailoverExecutor("chat", chain)

    async def _drain():
        fragments = []
        async for fragment in executor.stream(lambda e: e.stream()):
            fragments.append(fragment)
        return fragments

    with pytest.raises(RemoteServiceUnavailableError):
        asyncio.run(_drain())
