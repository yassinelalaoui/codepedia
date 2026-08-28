from __future__ import annotations

import threading
from typing import Any, Iterable, Optional, Sequence

from vector_index import VectorEntry, build_chunk_id, normalize_chunk_content

Vector = tuple[float, ...]


def expected_embedding_model_id(embedding_engine: Any) -> str:
    """The provider id a cached vector must carry to be reusable.

    A chunk id is a hash of `sourceSymbolId|chunkType|content` - it says
    nothing about which model produced the vector, so an id match alone is not
    enough: reusing a vector from a different model mixes dimensionalities into
    one index, which `search` can only respond to by returning nothing.

    For a `FailoverExecutor` the answer is the head of its chain, which is the
    provider a call resolves to in every case except an active failure. This
    mirrors `VectorIndex._embed_query_preferring_indexed_provider`, which
    already prefers the indexed provider over whatever the chain would pick
    fresh. A raw provider has no chain and no stamped id, so nothing is
    reusable and this returns "".
    """
    chain = getattr(embedding_engine, "chain", None)
    if not chain:
        return ""
    return str(chain[0][0])


class EmbeddingCache:
    """Vectors already computed, looked up before an embedding call is paid for.

    Two keys, because neither alone covers what an indexing run actually
    repeats:

    - the chunk id, which catches the same symbol re-embedded with unchanged
      content (the common case across two runs of a repository);
    - `(chunkType, normalized content)`, which catches identical bodies under
      *different* symbols - a re-exported wrapper, a boilerplate `__init__`,
      the same short function in two modules. The chunk id is seeded on the
      symbol id and so is blind to these by construction.

    Every entry carries the model that produced it, and `get` refuses to serve
    a vector produced by any other one.

    Safe to share across the embedding pool's threads: every mutation is under
    one lock, and the values are immutable tuples.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_chunk_id: dict[str, tuple[Vector, str]] = {}
        self._by_content: dict[tuple[str, str], tuple[Vector, str]] = {}
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_chunk_id)

    def get(self, *, source_symbol_id: str, content: str, chunk_type: str, model_id: str) -> Optional[Vector]:
        """The cached vector for this fragment, or None to embed it for real.

        Counts its own hits/misses so the CLI can report how much of a run the
        cache actually paid for.
        """
        if not model_id:
            with self._lock:
                self.misses += 1
            return None
        chunk_id = build_chunk_id(source_symbol_id, content, chunk_type=chunk_type)
        content_key = (chunk_type, normalize_chunk_content(content))
        with self._lock:
            for cached in (self._by_chunk_id.get(chunk_id), self._by_content.get(content_key)):
                if cached is not None and cached[1] == model_id:
                    self.hits += 1
                    return cached[0]
            self.misses += 1
            return None

    def put(self, *, source_symbol_id: str, content: str, chunk_type: str, model_id: str, vector: Sequence[float]) -> None:
        if not model_id:
            # An unattributed vector can never satisfy `get`'s model check, so
            # storing it would only grow the cache.
            return
        chunk_id = build_chunk_id(source_symbol_id, content, chunk_type=chunk_type)
        entry = (tuple(float(value) for value in vector), model_id)
        with self._lock:
            self._by_chunk_id[chunk_id] = entry
            self._by_content[(chunk_type, normalize_chunk_content(content))] = entry

    def seed_from_entries(self, entries: Iterable[VectorEntry]) -> int:
        """Warm the cache from an index that already exists.

        This is what makes the cache worth anything on a full `index` run:
        that run builds into an empty staging directory, so without seeding
        there is nothing to hit. Entries written before `embeddingModelId`
        existed carry an empty id and are skipped rather than reused blindly.
        """
        seeded = 0
        for entry in entries:
            if not entry.embeddingModelId or not entry.content:
                continue
            self.put(
                source_symbol_id=entry.sourceSymbolId,
                content=entry.content,
                chunk_type=entry.chunkType,
                model_id=entry.embeddingModelId,
                vector=entry.vector,
            )
            seeded += 1
        return seeded
