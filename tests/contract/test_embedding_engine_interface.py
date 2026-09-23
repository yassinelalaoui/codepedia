from __future__ import annotations

from embedding_engine import EmbeddingEngine, EmbeddingVector, create_embedding_engine
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


def test_the_local_engine_satisfies_the_embedding_provider_protocol():
    local_engine = create_embedding_engine("nomic-embed-text", "http://localhost:11434")

    assert isinstance(local_engine, EmbeddingProvider)
    assert local_engine.isAvailable() == local_engine.isAvailableLocally()
    assert callable(local_engine.checkAvailability)
    assert callable(local_engine.embed)
    # Every stored vector records the model that produced it, so a query is
    # never scored against vectors from another one.
    assert local_engine.providerId == "local:nomic-embed-text"
