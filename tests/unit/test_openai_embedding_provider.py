from __future__ import annotations

import httpx
import pytest

from embedding_engine.errors import MissingApiKeyError, RateLimitedError, ServiceUnavailableError
from embedding_engine.openai_provider import create_openai_embedding_provider


def _provider(monkeypatch, api_key: str | None = "sk-test") -> object:
    if api_key is None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENAI_API_KEY", api_key)
    return create_openai_embedding_provider()


def test_embed_success(monkeypatch) -> None:
    provider = _provider(monkeypatch)

    def fake_post(url, *, json, headers, timeout):
        assert headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    vector = provider.embed("hello world")

    assert vector == (0.1, 0.2, 0.3)


@pytest.mark.parametrize("status_code", [401, 403])
def test_embed_auth_error_maps_to_missing_api_key(monkeypatch, status_code) -> None:
    provider = _provider(monkeypatch)
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: httpx.Response(status_code, json={}, request=httpx.Request("POST", url))
    )

    with pytest.raises(MissingApiKeyError):
        provider.embed("hello world")


def test_embed_rate_limited_maps_to_rate_limited_error(monkeypatch) -> None:
    provider = _provider(monkeypatch)
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: httpx.Response(429, json={}, request=httpx.Request("POST", url))
    )

    with pytest.raises(RateLimitedError):
        provider.embed("hello world")


def test_embed_unreachable_host_maps_to_service_unavailable(monkeypatch) -> None:
    provider = _provider(monkeypatch)

    def fake_post(url, **kw):
        raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(ServiceUnavailableError):
        provider.embed("hello world")


def test_embed_missing_api_key_raises_without_a_network_call(monkeypatch) -> None:
    provider = _provider(monkeypatch, api_key=None)
    calls: list[object] = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: calls.append(1))

    with pytest.raises(MissingApiKeyError):
        provider.embed("hello world")

    assert calls == []
