from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .chunking import build_code_chunk
from .models import CodeChunk, IndexRecord, SearchQuery, SearchResult, VectorEntry
from .search import rank_entries
from . import storage


class VectorIndex:
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
        self._connection = storage.connect(self.metadataPath)
        self._record = storage.ensure_index_record(
            self._connection,
            repository_root=self.repositoryRoot,
            metadata_path=self.metadataPath,
        )
        self._entries: dict[str, VectorEntry] = {}
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
        loaded = storage.load_entries(self._connection, index_id=self._record.id)
        self._entries = {entry.chunkId: entry for entry in loaded}
        self._rebuild_file_index()

    def _rebuild_file_index(self) -> None:
        mapping: dict[str, set[str]] = {}
        for entry in self._entries.values():
            mapping.setdefault(entry.sourceFilePath, set()).add(entry.chunkId)
        self._file_to_chunks = mapping

    def _persist_record(self) -> None:
        storage.touch_index(self._connection, self._record.id)
        self._record = storage.load_index_record(self._connection, self._record.id)

    def _store_entry(self, chunk: CodeChunk, *, source_file_path: str | Path | None = None) -> VectorEntry:
        entry = storage.upsert_chunk(
            self._connection,
            index_id=self._record.id,
            chunk=chunk,
            source_file_path=source_file_path,
        )
        self._entries[entry.chunkId] = entry
        self._file_to_chunks.setdefault(entry.sourceFilePath, set()).add(entry.chunkId)
        self._persist_record()
        return entry

    def addChunk(self, chunk: CodeChunk, *, sourceFilePath: str | Path | None = None) -> VectorEntry:
        return self._store_entry(chunk, source_file_path=sourceFilePath)

    def addChunks(
        self,
        chunks: Iterable[CodeChunk],
        *,
        sourceFilePath: str | Path | None = None,
    ) -> tuple[VectorEntry, ...]:
        stored = tuple(self._store_entry(chunk, source_file_path=sourceFilePath) for chunk in chunks)
        self._persist_record()
        return stored

    def removeChunksForFile(self, path: str | Path) -> tuple[str, ...]:
        normalized = storage.normalize_path(path)
        removed_ids = storage.delete_chunks_for_file(self._connection, index_id=self._record.id, source_file_path=normalized)
        for chunk_id in removed_ids:
            entry = self._entries.pop(chunk_id, None)
            if entry is not None:
                bucket = self._file_to_chunks.get(entry.sourceFilePath)
                if bucket is not None:
                    bucket.discard(chunk_id)
                    if not bucket:
                        self._file_to_chunks.pop(entry.sourceFilePath, None)
        self._persist_record()
        return removed_ids

    def reindexFile(self, path: str | Path, chunks: Iterable[CodeChunk]) -> tuple[VectorEntry, ...]:
        normalized = storage.normalize_path(path)
        self.removeChunksForFile(normalized)
        stored = tuple(
            self._store_entry(
                chunk if chunk.sourceFilePath == normalized else replace(chunk, sourceFilePath=normalized),
                source_file_path=normalized,
            )
            for chunk in chunks
        )
        self._persist_record()
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
        results = rank_entries(query_vector, self._entries.values(), k=search_query.k, filters=filters)
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
            results = rank_entries(query_vector, self._entries.values(), k=search_query.k, filters=relaxed_filters)
        return results

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
        self._connection.close()

    def refresh(self) -> None:
        loaded = storage.load_entries(self._connection, index_id=self._record.id)
        self._entries = {entry.chunkId: entry for entry in loaded}
        self._rebuild_file_index()

    def chunks_for_file(self, path: str | Path) -> tuple[VectorEntry, ...]:
        normalized = storage.normalize_path(path)
        chunk_ids = self._file_to_chunks.get(normalized, set())
        return tuple(self._entries[chunk_id] for chunk_id in chunk_ids if chunk_id in self._entries)

    def get_lifecycle(self, path: str | Path | None = None) -> dict[str, str]:
        with self._connection:
            return storage.load_lifecycle_state(self._connection, source_file_path=path)
