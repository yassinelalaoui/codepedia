from __future__ import annotations

from pathlib import Path
from time import perf_counter

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


def _engine(provider_id: str) -> FakeEmbeddingEngine:
    engine = FakeEmbeddingEngine()
    engine.providerId = provider_id
    return engine


def test_search_never_blends_vectors_from_different_embedding_models(tmp_path):
    """Switching the embedding model never corrupts a similarity search.

    Every result comes from one internally-consistent embedding space, and
    vectors from another model are silently excluded rather than compared or
    raising. This mattered when a chain could hold two providers; it still
    matters with one engine per index, because the operator can change the
    configured model at any time and the old vectors stay on disk until a
    re-index replaces them.
    """
    model_a = "local:nomic-embed-text"
    model_b = "local:some-other-embed"

    index_a = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=_engine(model_a))
    chunk_a = build_code_chunk(
        "alpha helper function", source_symbol_id="symbol-alpha", source_file_path="src/alpha.py",
        embedding_engine=_engine(model_a),
    )
    index_a.addChunk(chunk_a)
    assert chunk_a.embeddingModelId == model_a

    index_b = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=_engine(model_b))
    chunk_b = build_code_chunk(
        "beta helper function", source_symbol_id="symbol-beta", source_file_path="src/beta.py",
        embedding_engine=_engine(model_b),
    )
    index_b.addChunk(chunk_b)
    assert chunk_b.embeddingModelId == model_b

    # Both chunks share the same underlying vector space (FakeEmbeddingEngine's
    # encode_text) so dimensionality never differs - proving the exclusion is
    # driven by embeddingModelId, not dimensionality, and never crashes. Two
    # local models sharing a vector length is entirely ordinary, which is why
    # the model id has to be the thing that decides.
    results_a = index_a.search("alpha helper function", k=5)
    assert {result.chunkId for result in results_a} == {chunk_a.id}

    results_b = index_b.search("beta helper function", k=5)
    assert {result.chunkId for result in results_b} == {chunk_b.id}


def test_search_returns_nothing_when_the_model_changed_since_indexing(tmp_path):
    """After a model change the honest answer is no results, not wrong ones.

    The previous implementation retried without the model filter when a
    filtered search came up empty, because a failover chain could answer one
    call with a different provider than it had used at index time. Nothing is
    non-deterministic now, so an empty result means exactly one thing - the
    index was built by another model - and comparing the vectors anyway would
    produce confident nonsense. Re-indexing is the fix.
    """
    index = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=_engine("local:old-model"))
    chunk = build_code_chunk(
        "alpha helper function", source_symbol_id="symbol-alpha", source_file_path="src/alpha.py",
        embedding_engine=_engine("local:old-model"),
    )
    index.addChunk(chunk)

    reopened = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=_engine("local:new-model"))

    assert reopened.search("alpha helper function", k=5) == []


