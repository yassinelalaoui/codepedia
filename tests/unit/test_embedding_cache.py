"""Vectors already paid for are not bought twice
(contracts/indexing-concurrency-delta.md).

A chunk id hashes `sourceSymbolId|chunkType|content` and says nothing about
which model produced the vector, so an id match alone is not licence to reuse:
two models produce vectors of different dimensionalities, and mixing them into
one index is how `search` ends up returning nothing. Every reuse here is
therefore gated on `embeddingModelId` as well.
"""

from __future__ import annotations

import threading

from provider_routing import FailoverExecutor, ProviderRef
from reindex_pipeline.embedding_cache import EmbeddingCache, expected_embedding_model_id
from vector_index import VectorEntry, build_chunk_id


class _Provider:
    def __init__(self, dimensions: int = 3) -> None:
        self.calls = 0
        self._dimensions = dimensions

    def isAvailable(self) -> bool:
        return True

    def embed(self, text: str):
        self.calls += 1
        return tuple(float(len(text) + offset) for offset in range(self._dimensions))


def _executor(ref: str = "openai:text-embedding-3-small", provider: _Provider | None = None) -> FailoverExecutor:
    return FailoverExecutor("embeddings", ((ProviderRef.parse(ref), provider or _Provider()),))


def test_the_same_chunk_and_model_is_served_from_the_cache() -> None:
    cache = EmbeddingCache()
    cache.put(source_symbol_id="sym1", content="value = 1", chunk_type="code", model_id="openai:m", vector=(1.0, 2.0))

    assert cache.get(
        source_symbol_id="sym1", content="value = 1", chunk_type="code", model_id="openai:m"
    ) == (1.0, 2.0)


def test_a_different_model_is_never_served_from_the_cache() -> None:
    """The point of the model check: the id would match, the vector would not
    even have the right number of dimensions."""
    cache = EmbeddingCache()
    cache.put(source_symbol_id="sym1", content="value = 1", chunk_type="code", model_id="openai:m", vector=(1.0, 2.0))

    assert cache.get(source_symbol_id="sym1", content="value = 1", chunk_type="code", model_id="local:other") is None


def test_identical_content_under_a_different_symbol_is_reused() -> None:
    """`build_chunk_id` seeds on the symbol id, so these two chunks have
    different ids despite identical bodies - the content key is what catches
    them."""
    cache = EmbeddingCache()
    cache.put(source_symbol_id="sym1", content="return None", chunk_type="code", model_id="openai:m", vector=(4.0,))

    assert build_chunk_id("sym1", "return None") != build_chunk_id("sym2", "return None")
    assert cache.get(
        source_symbol_id="sym2", content="return None", chunk_type="code", model_id="openai:m"
    ) == (4.0,)


def test_content_reuse_respects_the_chunk_type() -> None:
    """A code chunk and a summary chunk are separately searchable and must not
    borrow each other's vectors even when their text coincides."""
    cache = EmbeddingCache()
    cache.put(source_symbol_id="sym1", content="same text", chunk_type="code", model_id="openai:m", vector=(7.0,))

    assert cache.get(source_symbol_id="sym2", content="same text", chunk_type="summary", model_id="openai:m") is None


def test_content_matching_ignores_trailing_whitespace_like_the_chunk_id_does() -> None:
    cache = EmbeddingCache()
    cache.put(source_symbol_id="sym1", content="a = 1   \nb = 2", chunk_type="code", model_id="openai:m", vector=(1.0,))

    assert cache.get(source_symbol_id="sym1", content="a = 1\nb = 2", chunk_type="code", model_id="openai:m") == (1.0,)


def test_an_unattributed_vector_is_neither_stored_nor_served() -> None:
    """Chunks written before `embeddingModelId` existed carry an empty id;
    reusing them blindly would defeat the model check entirely."""
    cache = EmbeddingCache()
    cache.put(source_symbol_id="sym1", content="value = 1", chunk_type="code", model_id="", vector=(1.0,))

    assert len(cache) == 0
    assert cache.get(source_symbol_id="sym1", content="value = 1", chunk_type="code", model_id="") is None


def test_hits_and_misses_are_counted() -> None:
    cache = EmbeddingCache()
    cache.put(source_symbol_id="sym1", content="value = 1", chunk_type="code", model_id="openai:m", vector=(1.0,))

    cache.get(source_symbol_id="sym1", content="value = 1", chunk_type="code", model_id="openai:m")
    cache.get(source_symbol_id="sym1", content="other", chunk_type="code", model_id="openai:m")

    assert (cache.hits, cache.misses) == (1, 1)


def test_seeding_skips_entries_with_no_model_attribution() -> None:
    cache = EmbeddingCache()
    seeded = cache.seed_from_entries(
        [
            VectorEntry(
                chunkId="c1",
                vector=(1.0, 2.0),
                dimensionality=2,
                sourceFilePath="alpha.py",
                sourceSymbolId="sym1",
                chunkType="code",
                content="value = 1",
                embeddingModelId="openai:m",
            ),
            VectorEntry(
                chunkId="c2",
                vector=(3.0, 4.0),
                dimensionality=2,
                sourceFilePath="alpha.py",
                sourceSymbolId="sym2",
                chunkType="code",
                content="value = 2",
                embeddingModelId="",
            ),
        ]
    )

    assert seeded == 1
    assert cache.get(source_symbol_id="sym1", content="value = 1", chunk_type="code", model_id="openai:m") == (1.0, 2.0)


def test_the_expected_model_is_the_head_of_the_chain() -> None:
    executor = FailoverExecutor(
        "embeddings",
        ((ProviderRef.parse("openai:m1"), _Provider()), (ProviderRef.parse("local:m2"), _Provider())),
    )

    assert expected_embedding_model_id(executor) == "openai:m1"


def test_a_raw_provider_has_no_reusable_model_id() -> None:
    """A bare `EmbeddingProvider` stamps no id onto its chunks, so nothing it
    produced can be safely matched later."""
    assert expected_embedding_model_id(_Provider()) == ""


def test_concurrent_readers_and_writers_do_not_lose_entries() -> None:
    """The embedding pool shares one cache across its threads."""
    cache = EmbeddingCache()
    errors: list[BaseException] = []

    def worker(number: int) -> None:
        try:
            for repeat in range(20):
                content = f"body {number}-{repeat}"
                cache.put(
                    source_symbol_id=f"sym{number}",
                    content=content,
                    chunk_type="code",
                    model_id="openai:m",
                    vector=(float(number),),
                )
                assert cache.get(
                    source_symbol_id=f"sym{number}", content=content, chunk_type="code", model_id="openai:m"
                ) == (float(number),)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the main thread below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(number,)) for number in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(cache) == 8 * 20
