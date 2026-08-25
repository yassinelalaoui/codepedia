from __future__ import annotations

import pytest

from provider_routing import ProviderChain, ProviderRef


@pytest.mark.parametrize(
    "value",
    ["local:nomic-embed-text", "groq:llama-3.3-70b-versatile", "openai:text-embedding-3-small"],
)
def test_provider_ref_parse_and_str_round_trip(value: str) -> None:
    ref = ProviderRef.parse(value)
    assert str(ref) == value


def test_provider_ref_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        ProviderRef(kind="anthropic", model="claude")


def test_provider_ref_rejects_empty_model() -> None:
    with pytest.raises(ValueError):
        ProviderRef(kind="local", model="")


def test_provider_ref_parse_rejects_missing_colon() -> None:
    with pytest.raises(ValueError):
        ProviderRef.parse("local-nomic-embed-text")


def test_provider_ref_parse_does_not_validate_model_installation() -> None:
    # research.md §13 L1: parsing only checks kind/non-empty model - it
    # never checks whether a named local model is actually installed. That
    # check stays at the engine's own checkAvailability(), exercised lazily.
    ref = ProviderRef.parse("local:some-model-that-may-not-exist")
    assert ref.kind == "local"
    assert ref.model == "some-model-that-may-not-exist"


def test_provider_chain_rejects_empty_providers() -> None:
    with pytest.raises(ValueError):
        ProviderChain(stage="chat", providers=())


def test_provider_chain_rejects_unknown_stage() -> None:
    with pytest.raises(ValueError):
        ProviderChain(stage="translation", providers=(ProviderRef.parse("local:x"),))


def test_provider_chain_holds_ordered_providers() -> None:
    chain = ProviderChain(
        stage="chat",
        providers=(ProviderRef.parse("groq:llama-3.3-70b-versatile"), ProviderRef.parse("local:qwen2.5-coder")),
    )
    assert [str(ref) for ref in chain.providers] == ["groq:llama-3.3-70b-versatile", "local:qwen2.5-coder"]
