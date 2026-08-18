from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from embedding_engine import EmbeddingEngine

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
        embedding_engine: EmbeddingEngine | None = None,
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
        embedding_engine: EmbeddingEngine | None = None,
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
        dimension = next(iter(self._entries.values())).dimensionality
        if self._embedding_engine is None:
            raise RuntimeError("VectorIndex.search requires an EmbeddingEngine configured on the index")
        query_vector = self._embedding_engine.embed(search_query.queryText)
        if len(query_vector) != dimension:
            raise ValueError("query vector dimensionality does not match indexed entries")
        return rank_entries(query_vector, self._entries.values(), k=search_query.k, filters=search_query.filters)

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
