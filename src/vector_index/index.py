from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .chunking import build_code_chunk
from .models import CodeChunk, IndexRecord, SearchQuery, SearchResult, VectorEntry
from .matrix import VectorMatrix
from .search import _matches_filters, reciprocal_rank_fusion
from . import storage


class VectorIndex:
    # How far past k each side is sampled before fusion.
    HYBRID_OVERSAMPLE = 4

    def __init__(
        self,
        repositoryRoot: str | Path,
        metadataPath: str | Path,
        *,
        auto_load: bool = True,
        embedding_engine: Any = None,
    ) -> None:
        self.repositoryRoot = str(Path(repositoryRoot).expanduser().resolve())
        self.metadataPath = Path(metadataPath).expanduser()
        self.metadataPath.parent.mkdir(parents=True, exist_ok=True)
        # Reentrant because the public write methods nest: reindexFile ->
        # removeChunksForFile, and _store_entry -> _persist_record.
        self._lock = threading.RLock()
        self._connection = storage.connect(self.metadataPath)
        self._record = storage.ensure_index_record(
            self._connection,
            repository_root=self.repositoryRoot,
            metadata_path=self.metadataPath,
        )
        self._entries: dict[str, VectorEntry] = {}
        self._matrix: VectorMatrix | None = None
        self._file_to_chunks: dict[str, set[str]] = {}
        self._embedding_engine = embedding_engine
        self._load_if_needed(auto_load=auto_load)

    @classmethod
    def load(
        cls,
        repositoryRoot: str | Path,
        metadataPath: str | Path,
        *,
        embedding_engine: Any = None,
    ) -> "VectorIndex":
        return cls(repositoryRoot, metadataPath, auto_load=True, embedding_engine=embedding_engine)

    @property
    def record(self) -> IndexRecord:
        return self._record

    @property
    def entries(self) -> tuple[VectorEntry, ...]:
        return tuple(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)

    def _load_if_needed(self, *, auto_load: bool) -> None:
        if not auto_load:
            return
        with self._lock:
            loaded = storage.load_entries(self._connection, index_id=self._record.id, with_vectors=False)
            self._entries = {entry.chunkId: entry for entry in loaded}
            self._invalidate_matrix()
            self._rebuild_file_index()

    def _rebuild_file_index(self) -> None:
        mapping: dict[str, set[str]] = {}
        for entry in self._entries.values():
            mapping.setdefault(entry.sourceFilePath, set()).add(entry.chunkId)
        self._file_to_chunks = mapping

    def _persist_record(self) -> None:
        with self._lock:
            storage.touch_index(self._connection, self._record.id)
            self._reload_record()

    def _reload_record(self) -> None:
        """Re-read the row without writing it - for a caller whose transaction
        already touched `last_indexed_at`."""
        self._record = storage.load_index_record(self._connection, self._record.id)

    def _remember(self, entry: VectorEntry) -> None:
        self._entries[entry.chunkId] = entry
        self._file_to_chunks.setdefault(entry.sourceFilePath, set()).add(entry.chunkId)

    def _forget(self, chunk_id: str) -> None:
        entry = self._entries.pop(chunk_id, None)
        if entry is None:
            return
        bucket = self._file_to_chunks.get(entry.sourceFilePath)
        if bucket is not None:
            bucket.discard(chunk_id)
            if not bucket:
                self._file_to_chunks.pop(entry.sourceFilePath, None)

    def addChunk(self, chunk: CodeChunk, *, sourceFilePath: str | Path | None = None) -> VectorEntry:
        with self._lock:
            entry = storage.upsert_chunk(
                self._connection,
                index_id=self._record.id,
                chunk=chunk,
                source_file_path=sourceFilePath,
            )
            self._remember(entry)
            self._invalidate_matrix()
            self._persist_record()
            return entry

    def addChunks(
        self,
        chunks: Iterable[CodeChunk],
        *,
        sourceFilePath: str | Path | None = None,
    ) -> tuple[VectorEntry, ...]:
        with self._lock:
            stored = storage.upsert_chunks(
                self._connection,
                index_id=self._record.id,
                chunks=chunks,
                source_file_path=sourceFilePath,
            )
            for entry in stored:
                self._remember(entry)
            self._invalidate_matrix()
            self._persist_record()
            return stored

    def removeChunksForFile(self, path: str | Path) -> tuple[str, ...]:
        normalized = storage.normalize_path(path)
        with self._lock:
            removed_ids = storage.delete_chunks_for_file(self._connection, index_id=self._record.id, source_file_path=normalized)
            for chunk_id in removed_ids:
                self._forget(chunk_id)
            self._invalidate_matrix()
            self._persist_record()
            return removed_ids

    def reindexFile(self, path: str | Path, chunks: Iterable[CodeChunk]) -> tuple[VectorEntry, ...]:
        """Replace one file's chunks - the write path, and one commit.

        The delete, every insert and the `last_indexed_at` touch share a single
        transaction (`storage.replace_chunks_for_file`). This used to be a
        `removeChunksForFile` commit followed by two commits per chunk, on the
        path the watcher takes for every save.
        """
        normalized = storage.normalize_path(path)
        rebased = tuple(
            chunk if chunk.sourceFilePath == normalized else replace(chunk, sourceFilePath=normalized)
            for chunk in chunks
        )
        with self._lock:
            removed_ids, stored = storage.replace_chunks_for_file(
                self._connection,
                index_id=self._record.id,
                source_file_path=normalized,
                chunks=rebased,
            )
            for chunk_id in removed_ids:
                self._forget(chunk_id)
            for entry in stored:
                self._remember(entry)
            self._invalidate_matrix()
            self._reload_record()
            return stored

    def search(
        self,
        query: str | SearchQuery,
        k: int | None = None,
        *,
        filters: Mapping[str, object] | None = None,
    ) -> list[SearchResult]:
        if isinstance(query, SearchQuery):
            search_query = query
        else:
            if k is None:
                k = 5
            search_query = SearchQuery(queryText=query, k=k, filters=filters or {})
        if not self._entries:
            return []
        if self._embedding_engine is None:
            raise RuntimeError("VectorIndex.search requires an EmbeddingEngine configured on the index")
        filters = dict(search_query.filters)
        auto_filtered_model_id: str | None = None
        if hasattr(self._embedding_engine, "run"):
            query_vector, provider_used = self._embed_query_preferring_indexed_provider(search_query.queryText)
            if "embeddingModelId" not in filters:
                auto_filtered_model_id = provider_used
                filters["embeddingModelId"] = provider_used
        else:
            query_vector = self._embedding_engine.embed(search_query.queryText)
        results = self._hybrid_search(query_vector, search_query, filters)
        if not results and auto_filtered_model_id is not None:
            # `FailoverExecutor` isn't sticky - a transient failure can still
            # mean this query's embedding was answered by a provider whose
            # vectors aren't even the same length as what's indexed (e.g. a
            # rate limit that recovers only after the preferred-provider
            # check above already gave up). Rather than surface zero matches
            # when the index actually holds usable content, retry without
            # the auto-applied filter - still safe, since rank_entries' own
            # dimensionality check keeps genuinely incompatible vectors from
            # being compared.
            relaxed_filters = {key: value for key, value in filters.items() if key != "embeddingModelId"}
            results = self._hybrid_search(query_vector, search_query, relaxed_filters)
        return results

    def _hybrid_search(
        self,
        query_vector: Sequence[float],
        search_query: SearchQuery,
        filters: Mapping[str, object],
    ) -> list[SearchResult]:
        """Vector similarity fused with BM25, ordered by rank, scored by cosine.

        Both sides are over-sampled so a result the other side ranked highly can
        still surface, then Reciprocal Rank Fusion decides the final order.

        `SearchResult.score` deliberately stays the raw cosine similarity rather
        than the fused score: `chat/retrieval.py` compares it against absolute
        thresholds (below 0.15 means "not enough evidence", within 0.05 of the
        top means "ambiguous"), and an RRF score of ~0.016 would trip both on
        every single answer. Fusion changes the order, never the score.
        """
        depth = max(search_query.k * self.HYBRID_OVERSAMPLE, search_query.k)
        scores = self._matrix_scores(query_vector)
        vector_results = self._rank_from_scores(scores, depth, filters)
        vector_ranking = [result.chunkId for result in vector_results]
        scored: dict[str, SearchResult] = {result.chunkId: result for result in vector_results}

        lexical_ranking: list[str] = []
        for chunk_id in self._lexical_candidates(search_query.queryText, depth):
            if chunk_id in scored:
                lexical_ranking.append(chunk_id)
                continue
            entry = self._entries.get(chunk_id)
            if entry is None or not _matches_filters(entry, filters or {}):
                continue
            # A lexical-only hit still needs a real similarity, and it comes
            # from the same matrix pass as the vector side rather than from a
            # per-entry cosine. Absent from `scores` means the entry is of
            # another dimensionality, which the matrix excludes structurally -
            # the same rejection the old `score_entry` gate made explicitly.
            score = scores.get(chunk_id)
            if score is None:
                continue
            scored[chunk_id] = SearchResult(
                chunkId=entry.chunkId,
                content=entry.content,
                score=score,
                sourceSymbolId=entry.sourceSymbolId,
                sourceFilePath=entry.sourceFilePath,
                chunkType=entry.chunkType,
            )
            lexical_ranking.append(chunk_id)

        if not lexical_ranking:
            return vector_results[: search_query.k]
        fused = reciprocal_rank_fusion([vector_ranking, lexical_ranking])
        return [scored[chunk_id] for chunk_id in fused[: search_query.k] if chunk_id in scored]

    def _matrix_scores(self, query_vector: Sequence[float]) -> dict[str, float]:
        """Cosine score for every entry of the query's dimensionality, by id.

        One dot product, replacing a per-entry Python cosine loop that measured
        19.4 s at 50k chunks of 1536 dimensions. `VectorMatrix.score` already
        returns *every* row of the matching dimensionality rather than a head,
        so both halves of the hybrid search read their scores from this one
        pass - which is what lets the entries themselves stop carrying a second
        copy of every vector.

        An entry of another dimensionality is simply absent from the result:
        the matrix groups by length, so the exclusion is structural rather than
        a guard inside a loop.
        """
        scored_rows = self._ensure_matrix().score(query_vector)
        if len(scored_rows) == 0:
            return {}
        return {chunk_id: float(score) for chunk_id, score in zip(scored_rows.chunkIds, scored_rows.scores)}

    def _rank_from_scores(
        self, scores: Mapping[str, float], depth: int, filters: Mapping[str, object]
    ) -> list[SearchResult]:
        """Best `depth` results from an already-scored pass.

        Ordering matches `search.rank_entries` exactly, including the chunk-id
        tie-break, because that path remains reachable for callers passing
        ad-hoc chunks. Filters stay in Python, applied to the scored rows; the
        cosine, not the filtering, was the cost.
        """
        candidates: list[tuple[float, VectorEntry]] = []
        for chunk_id, score in scores.items():
            entry = self._entries.get(chunk_id)
            if entry is None or not _matches_filters(entry, filters or {}):
                continue
            candidates.append((score, entry))

        candidates.sort(key=lambda item: (-item[0], item[1].chunkId))
        return [
            SearchResult(
                chunkId=entry.chunkId,
                content=entry.content,
                score=score,
                sourceSymbolId=entry.sourceSymbolId,
                sourceFilePath=entry.sourceFilePath,
                chunkType=entry.chunkType,
            )
            for score, entry in candidates[:depth]
        ]

    def _ensure_matrix(self) -> VectorMatrix:
        """Rebuild lazily, from the database rather than from memory.

        Rebuilding on every insert would be O(n^2) across a full index run, so
        mutations only raise a flag. Reading vectors back from SQLite instead of
        keeping them in memory is what keeps the peak cost one decoded row.
        """
        with self._lock:
            if self._matrix is None:
                self._matrix = VectorMatrix.build_from_rows(
                    storage.count_vectors_by_dimensionality(self._connection, index_id=self._record.id),
                    storage.iter_vector_rows(self._connection, index_id=self._record.id),
                )
            return self._matrix

    def _invalidate_matrix(self) -> None:
        self._matrix = None

    def _lexical_candidates(self, query_text: str, limit: int) -> tuple[str, ...]:
        """BM25 matches, or nothing at all if the lexical index is unavailable.

        Failing open matters: an index written before the FTS table existed, or
        a SQLite build without FTS5, must degrade to pure vector search rather
        than break every question.
        """
        try:
            with self._lock:
                return storage.search_lexical(
                    self._connection,
                    index_id=self._record.id,
                    query_text=query_text,
                    limit=limit,
                )
        except sqlite3.Error:
            return ()

    def _dominant_embedding_model_id(self) -> str | None:
        """The one `embeddingModelId` every stored entry shares, if there is
        exactly one - `None` for an empty/mixed-model index."""
        ids = {entry.embeddingModelId for entry in self._entries.values() if entry.embeddingModelId}
        if len(ids) == 1:
            return next(iter(ids))
        return None

    def _embed_query_preferring_indexed_provider(self, query_text: str) -> tuple[Any, str]:
        """Embed `query_text`, preferring whichever provider already indexed
        this repository's content over whatever a fresh failover-chain call
        would naturally pick first.

        `FailoverExecutor` resolves each call independently - it isn't
        sticky across calls, so a transient failure at index time (answered
        by provider B) and a since-recovered provider A at query time can
        otherwise mean the query is embedded by a *different* provider than
        what's actually indexed, silently returning zero results (not just
        a mismatched tag - genuinely different vector lengths, e.g. OpenAI's
        1536-dim vs. a local model's ~768-dim, which no post-hoc filter can
        reconcile). Deliberately calling the already-indexed provider's own
        engine first - when the index is (as in the common case)
        single-model and that provider is still part of the configured
        chain - keeps a query consistent with what's stored regardless of
        transient availability elsewhere in the chain.
        """
        dominant_model_id = self._dominant_embedding_model_id()
        if dominant_model_id is not None:
            preferred_engine = next(
                (engine for ref, engine in self._embedding_engine.chain if str(ref) == dominant_model_id), None
            )
            if preferred_engine is not None:
                try:
                    return preferred_engine.embed(query_text), dominant_model_id
                except Exception:  # noqa: BLE001 - any failure here just falls through to the normal chain below
                    pass
        failover_result = self._embedding_engine.run(lambda engine: engine.embed(query_text))
        return failover_result.value, str(failover_result.providerUsed)

    def save(self) -> IndexRecord:
        self._persist_record()
        return self._record

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def refresh(self) -> None:
        with self._lock:
            loaded = storage.load_entries(self._connection, index_id=self._record.id, with_vectors=False)
            self._entries = {entry.chunkId: entry for entry in loaded}
            self._invalidate_matrix()
            self._rebuild_file_index()

    def iter_cache_seed_rows(self):
        """Stream this index's chunks for `EmbeddingCache`, one decoded row at a time.

        The cache used to be seeded from `self.entries`, which is why those
        entries had to carry their vectors. Reading them straight from SQLite
        instead keeps the peak cost one row - and it is a whole prior index
        that gets read here, on every `index` run.
        """
        with self._lock:
            yield from storage.iter_cache_seed_rows(self._connection, index_id=self._record.id)

    def chunks_for_file(self, path: str | Path) -> tuple[VectorEntry, ...]:
        normalized = storage.normalize_path(path)
        chunk_ids = self._file_to_chunks.get(normalized, set())
        return tuple(self._entries[chunk_id] for chunk_id in chunk_ids if chunk_id in self._entries)

    def get_lifecycle(self, path: str | Path | None = None) -> dict[str, str]:
        with self._lock:
            with self._connection:
                return storage.load_lifecycle_state(self._connection, source_file_path=path)
