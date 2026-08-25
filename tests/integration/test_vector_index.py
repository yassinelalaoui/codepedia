from __future__ import annotations

from pathlib import Path
from time import perf_counter

from provider_routing import FailoverExecutor, ProviderRef
from vector_index import VectorIndex, build_code_chunk
from vector_index.search import encode_text


class FakeEmbeddingEngine:
    def embed(self, text: str):
        return encode_text(text)


def _create_index(tmp_path: Path) -> VectorIndex:
    return VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=FakeEmbeddingEngine())


def test_index_can_add_search_reopen_and_replace(tmp_path):
    engine = FakeEmbeddingEngine()
    index = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=engine)
    alpha = build_code_chunk("alpha handles repository metadata", source_symbol_id="symbol-alpha", source_file_path="src/alpha.py", embedding_engine=engine)
    beta = build_code_chunk("beta handles semantic retrieval", source_symbol_id="symbol-beta", source_file_path="src/beta.py", embedding_engine=engine)

    index.addChunks([alpha, beta])
    first_results = index.search("semantic retrieval", k=2)
    assert first_results[0].chunkId == beta.id
    assert first_results[0].sourceSymbolId == "symbol-beta"

    index.save().to_dict()
    index.close()

    reopened = VectorIndex.load(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=engine)
    reopened_results = reopened.search("semantic retrieval", k=2)
    assert [item.chunkId for item in reopened_results] == [item.chunkId for item in first_results]

    updated_beta = build_code_chunk("beta now handles vector search ranking", source_symbol_id="symbol-beta", source_file_path="src/beta.py", embedding_engine=engine)
    reopened.reindexFile("src/beta.py", [updated_beta])
    updated_results = reopened.search("vector search ranking", k=1)
    assert updated_results[0].chunkId == updated_beta.id


def test_index_removes_deleted_file_vectors_and_keeps_unrelated_entries(tmp_path):
    engine = FakeEmbeddingEngine()
    index = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=engine)
    alpha = build_code_chunk("alpha helper", source_symbol_id="symbol-alpha", source_file_path="src/alpha.py", embedding_engine=engine)
    beta = build_code_chunk("beta helper", source_symbol_id="symbol-beta", source_file_path="src/beta.py", embedding_engine=engine)
    index.addChunks([alpha, beta])

    removed = index.removeChunksForFile("src/alpha.py")
    assert removed == (alpha.id,)
    assert index.search("alpha helper", k=2)[0].chunkId == beta.id


def test_empty_index_returns_no_matches_and_is_fast_enough_for_interactive_use(tmp_path):
    index = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=FakeEmbeddingEngine())
    start = perf_counter()
    results = index.search("anything at all", k=5)
    duration = perf_counter() - start

    assert results == []
    assert duration < 0.25


def _executor(provider_ref: ProviderRef) -> FailoverExecutor:
    return FailoverExecutor("embeddings", ((provider_ref, FakeEmbeddingEngine()),))


def test_search_never_blends_vectors_from_different_embedding_providers(tmp_path):
    """spec User Story 4: switching embedding providers never corrupts a
    similarity search - every result comes from one internally-consistent
    embedding space, and mismatched-model vectors are silently excluded
    (not compared, not a crash) rather than raising (research.md §8's fix
    for VectorIndex.search()'s pre-existing dimensionality crash)."""
    provider_a = ProviderRef.parse("openai:text-embedding-3-small")
    provider_b = ProviderRef.parse("local:nomic-embed-text")

    index_a = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=_executor(provider_a))
    chunk_a = build_code_chunk(
        "alpha helper function", source_symbol_id="symbol-alpha", source_file_path="src/alpha.py",
        embedding_engine=_executor(provider_a),
    )
    index_a.addChunk(chunk_a)
    assert chunk_a.embeddingModelId == str(provider_a)

    index_b = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=_executor(provider_b))
    chunk_b = build_code_chunk(
        "beta helper function", source_symbol_id="symbol-beta", source_file_path="src/beta.py",
        embedding_engine=_executor(provider_b),
    )
    index_b.addChunk(chunk_b)
    assert chunk_b.embeddingModelId == str(provider_b)

    # Both chunks share the same underlying vector space (FakeEmbeddingEngine's
    # encode_text) so dimensionality never differs - proving the exclusion is
    # driven by embeddingModelId, not dimensionality, and never crashes.
    results_a = index_a.search("alpha helper function", k=5)
    assert {result.chunkId for result in results_a} == {chunk_a.id}

    results_b = index_b.search("beta helper function", k=5)
    assert {result.chunkId for result in results_b} == {chunk_b.id}


class _UnavailableEmbeddingEngine:
    """Always raises a classified, retryable error - simulates a provider
    that answered during indexing but is transiently down at query time."""

    def isAvailable(self) -> bool:
        return False

    def embed(self, text: str):
        from embedding_engine.errors import ServiceUnavailableError

        raise ServiceUnavailableError("down", endpointUrl="https://x", modelName="m")


def test_search_falls_back_to_unfiltered_when_the_querying_provider_differs_from_the_indexed_one(tmp_path):
    """Regression: FailoverExecutor isn't sticky across calls - a provider
    that answered while indexing can differ from whichever one answers a
    later query (e.g. a rate limit that recovers, or one that newly
    appears). The auto-applied embeddingModelId filter must not silently
    return zero results just because *this* query happened to be answered
    by a different provider than what's actually indexed."""
    index_time_provider = ProviderRef.parse("local:model-a")
    query_time_provider = ProviderRef.parse("local:model-b")

    indexing_executor = FailoverExecutor("embeddings", ((index_time_provider, FakeEmbeddingEngine()),))
    index = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=indexing_executor)
    chunk = build_code_chunk(
        "alpha helper function", source_symbol_id="symbol-alpha", source_file_path="src/alpha.py",
        embedding_engine=indexing_executor,
    )
    index.addChunk(chunk)
    assert chunk.embeddingModelId == str(index_time_provider)

    # Simulate a later query where the *first* provider in the chain (the
    # one that indexed the content) is down, and a *different* provider
    # answers this specific call.
    query_executor = FailoverExecutor(
        "embeddings",
        ((ProviderRef.parse("local:model-down"), _UnavailableEmbeddingEngine()), (query_time_provider, FakeEmbeddingEngine())),
    )
    index_for_query = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=query_executor)

    results = index_for_query.search("alpha helper function", k=5)

    assert [result.chunkId for result in results] == [chunk.id]


def test_search_prefers_the_already_indexed_provider_over_chain_order(tmp_path):
    """Regression: when the index is single-model and that provider is
    still part of the query-time chain, it must be used directly for the
    query embedding - even if a *different*, currently-available provider
    would otherwise win by being first in chain order. Confirms the fix
    works at the vector-length level, not just via the relaxed-filter
    last resort (which can't help when dimensions genuinely differ)."""
    index_time_provider = ProviderRef.parse("local:model-a")

    indexing_executor = FailoverExecutor("embeddings", ((index_time_provider, FakeEmbeddingEngine()),))
    index = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=indexing_executor)
    chunk = build_code_chunk(
        "alpha helper function", source_symbol_id="symbol-alpha", source_file_path="src/alpha.py",
        embedding_engine=indexing_executor,
    )
    index.addChunk(chunk)

    class _TrackedEngine(FakeEmbeddingEngine):
        def __init__(self) -> None:
            self.calls = 0

        def embed(self, text: str):
            self.calls += 1
            return super().embed(text)

    other_available_provider_engine = _TrackedEngine()
    same_model_different_instance = _TrackedEngine()
    # "other_available" is listed FIRST and is fully available - normal
    # failover ordering would pick it, which is exactly the bug: it isn't
    # the provider that indexed this content.
    query_executor = FailoverExecutor(
        "embeddings",
        (
            (ProviderRef.parse("local:model-other"), other_available_provider_engine),
            (index_time_provider, same_model_different_instance),
        ),
    )
    index_for_query = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=query_executor)

    results = index_for_query.search("alpha helper function", k=5)

    assert [result.chunkId for result in results] == [chunk.id]
    assert other_available_provider_engine.calls == 0
    assert same_model_different_instance.calls == 1
