from __future__ import annotations

from embedding_engine import EmbeddingEngine, EmbeddingVector, create_embedding_engine


def test_public_api_exposes_core_types():
    assert EmbeddingEngine.__name__ == "EmbeddingEngine"
    assert EmbeddingVector.__name__ == "EmbeddingVector"
    assert callable(create_embedding_engine)


def test_embedding_engine_supports_expected_methods():
    engine = EmbeddingEngine("nomic-embed-text", "http://localhost:11434")

    assert hasattr(engine, "embed")
    assert hasattr(engine, "isAvailableLocally")
    assert hasattr(engine, "checkAvailability")
