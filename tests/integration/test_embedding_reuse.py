"""An unchanged fragment must not be embedded twice
(contracts/indexing-concurrency-delta.md).

`EmbeddingCache` is unit-tested in isolation; what these exercise is the whole
path through `update_embeddings` - that the cache is actually consulted before
the provider is called, that a reused vector is stored under the model that
produced it, and that reuse across two indexing runs is what makes the cache
worth having at all.
"""

from __future__ import annotations

from provider_routing import FailoverExecutor, ProviderRef
from reindex_pipeline.embedding_cache import EmbeddingCache
from reindex_pipeline.embeddings import update_embeddings
from vector_index import VectorIndex
from vector_index.search import encode_text

from ._doc_generator_support import build_indexed_repo

_MODEL = "openai:text-embedding-3-small"


class CountingEmbeddingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def isAvailable(self) -> bool:
        return True

    def embed(self, text: str):
        self.calls += 1
        return encode_text(text)


def _executor(provider: CountingEmbeddingProvider) -> FailoverExecutor:
    return FailoverExecutor("embeddings", ((ProviderRef.parse(_MODEL), provider),))


def _embed(tmp_path, root, store, relative_path, *, engine, cache, index_name="vectors.sqlite"):
    index = VectorIndex(root, tmp_path / index_name, embedding_engine=engine)
    try:
        return update_embeddings(
            repository_root=root,
            relative_path=relative_path,
            metadata_store=store,
            vector_index=index,
            embedding_engine=engine,
            embedding_cache=cache,
        )
    finally:
        index.close()


def test_a_second_run_over_unchanged_content_costs_no_embedding_calls(tmp_path):
    root, store, _graph = build_indexed_repo(tmp_path)
    provider = CountingEmbeddingProvider()
    engine = _executor(provider)
    cache = EmbeddingCache()

    first = _embed(tmp_path, root, store, "beta.py", engine=engine, cache=cache)
    calls_after_first = provider.calls
    assert calls_after_first == len(first) > 0

    second = _embed(tmp_path, root, store, "beta.py", engine=engine, cache=cache, index_name="vectors2.sqlite")

    assert provider.calls == calls_after_first, "an unchanged file must not be re-embedded"
    assert [chunk.id for chunk in second] == [chunk.id for chunk in first]
    assert [chunk.embedding for chunk in second] == [chunk.embedding for chunk in first]


def test_a_reused_vector_keeps_its_producing_model_id(tmp_path):
    """Without this, a cached chunk is stored with an empty `embeddingModelId`
    and stops matching the filter `search` applies by default - it would be
    indexed but unfindable."""
    root, store, _graph = build_indexed_repo(tmp_path)
    engine = _executor(CountingEmbeddingProvider())
    cache = EmbeddingCache()

    _embed(tmp_path, root, store, "beta.py", engine=engine, cache=cache)
    reused = _embed(tmp_path, root, store, "beta.py", engine=engine, cache=cache, index_name="vectors2.sqlite")

    assert {chunk.embeddingModelId for chunk in reused} == {_MODEL}


def test_a_cache_seeded_from_a_previous_index_serves_a_fresh_one(tmp_path):
    """The case that matters for `codepedia index`: it builds into an empty
    staging directory, so without seeding from the previous run's index the
    cache would have nothing to hit."""
    root, store, _graph = build_indexed_repo(tmp_path)
    provider = CountingEmbeddingProvider()
    engine = _executor(provider)

    previous = VectorIndex(root, tmp_path / "previous.sqlite", embedding_engine=engine)
    try:
        update_embeddings(
            repository_root=root,
            relative_path="beta.py",
            metadata_store=store,
            vector_index=previous,
            embedding_engine=engine,
        )
        seeded_from = previous.entries
    finally:
        previous.close()
    calls_after_first_run = provider.calls
    assert calls_after_first_run > 0

    warm = EmbeddingCache()
    assert warm.seed_from_entries(seeded_from) == len(seeded_from)

    _embed(tmp_path, root, store, "beta.py", engine=engine, cache=warm, index_name="fresh.sqlite")

    assert provider.calls == calls_after_first_run, "a seeded cache must serve the fresh index"


def test_changed_content_is_still_embedded_for_real(tmp_path):
    root, store, _graph = build_indexed_repo(tmp_path)
    provider = CountingEmbeddingProvider()
    engine = _executor(provider)
    cache = EmbeddingCache()

    _embed(tmp_path, root, store, "beta.py", engine=engine, cache=cache)
    calls_after_first = provider.calls

    # A new summary produces genuinely new text for the summary chunk.
    target = store.load_source_file(repository_root=root, path=root / "beta.py").classes[0]
    store.update_symbol_generated_summary(target.id, "A brand new summary nobody has embedded before.")

    _embed(tmp_path, root, store, "beta.py", engine=engine, cache=cache, index_name="vectors2.sqlite")

    assert provider.calls > calls_after_first, "new content must reach the provider"


def test_omitting_the_cache_leaves_the_previous_behaviour_untouched(tmp_path):
    root, store, _graph = build_indexed_repo(tmp_path)
    provider = CountingEmbeddingProvider()
    engine = _executor(provider)

    first = _embed(tmp_path, root, store, "beta.py", engine=engine, cache=None)
    calls_after_first = provider.calls
    _embed(tmp_path, root, store, "beta.py", engine=engine, cache=None, index_name="vectors2.sqlite")

    assert provider.calls == 2 * calls_after_first == 2 * len(first)
