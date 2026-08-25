from __future__ import annotations

from embedding_engine import EmbeddingEngine, EmbeddingVector, OpenAIEmbeddingProvider, create_embedding_engine
from embedding_engine.openai_provider import create_openai_embedding_provider
from embedding_engine.protocol import EmbeddingProvider


def test_public_api_exposes_core_types():
    assert EmbeddingEngine.__name__ == "EmbeddingEngine"
    assert EmbeddingVector.__name__ == "EmbeddingVector"
    assert callable(create_embedding_engine)


def test_embedding_engine_supports_expected_methods():
    engine = EmbeddingEngine("nomic-embed-text", "http://localhost:11434")

    assert hasattr(engine, "embed")
    assert hasattr(engine, "isAvailableLocally")
    assert hasattr(engine, "checkAvailability")


def test_local_and_openai_providers_both_satisfy_embedding_provider_protocol():
    local_engine = create_embedding_engine("nomic-embed-text", "http://localhost:11434")
    remote_provider = create_openai_embedding_provider()

    assert isinstance(local_engine, EmbeddingProvider)
    assert isinstance(remote_provider, EmbeddingProvider)
    assert isinstance(remote_provider, OpenAIEmbeddingProvider)
    assert local_engine.isAvailable() == local_engine.isAvailableLocally()
    assert callable(remote_provider.isAvailable)
    assert callable(remote_provider.checkAvailability)
    assert callable(remote_provider.embed)
