from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .models import CodeChunk, IndexRecord, VectorEntry


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS indexes (
        id TEXT PRIMARY KEY,
        repository_root TEXT NOT NULL,
        index_path TEXT NOT NULL,
        metadata_path TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_indexed_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        id TEXT PRIMARY KEY,
        index_id TEXT NOT NULL,
        source_file_path TEXT NOT NULL,
        source_symbol_id TEXT NOT NULL,
        chunk_type TEXT NOT NULL,
        content TEXT NOT NULL,
        embedding TEXT NOT NULL,
        dimensionality INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(index_id) REFERENCES indexes(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunk_lifecycle (
        chunk_id TEXT PRIMARY KEY,
        source_file_path TEXT NOT NULL,
        lifecycle_state TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chunks_index_id ON chunks(index_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_source_file_path ON chunks(index_id, source_file_path)",
    "CREATE INDEX IF NOT EXISTS idx_chunk_lifecycle_source_file_path ON chunk_lifecycle(source_file_path)",
)


def normalize_path(path: str | Path) -> str:
    return Path(path).expanduser().as_posix().replace("\\", "/")


def stable_index_id(repository_root: str | Path, index_path: str | Path, metadata_path: str | Path) -> str:
    normalized = "|".join(
        [
            Path(repository_root).expanduser().resolve().as_posix(),
            normalize_path(index_path),
            normalize_path(metadata_path),
        ]
    )
    import hashlib

    return f"vector_index_{hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:16]}"


def connect(metadata_path: str | Path) -> sqlite3.Connection:
    path = Path(metadata_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    for statement in SCHEMA_STATEMENTS:
        connection.execute(statement)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_index_record(
    connection: sqlite3.Connection,
    *,
    repository_root: str | Path,
    index_path: str | Path,
    metadata_path: str | Path,
    index_id: str | None = None,
) -> IndexRecord:
    record = IndexRecord(
        id=index_id or stable_index_id(repository_root, index_path, metadata_path),
        repositoryRoot=str(Path(repository_root).expanduser().resolve()),
        indexPath=str(Path(index_path).expanduser()),
        metadataPath=str(Path(metadata_path).expanduser()),
    )
    with connection:
        connection.execute(
            """
            INSERT INTO indexes (id, repository_root, index_path, metadata_path, created_at, last_indexed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                repository_root = excluded.repository_root,
                index_path = excluded.index_path,
                metadata_path = excluded.metadata_path,
                last_indexed_at = excluded.last_indexed_at
            """,
            (
                record.id,
                record.repositoryRoot,
                record.indexPath,
                record.metadataPath,
                record.createdAt,
                record.lastIndexedAt,
            ),
        )
    return record


def touch_index(connection: sqlite3.Connection, index_id: str, *, last_indexed_at: str | None = None) -> None:
    with connection:
        connection.execute(
            "UPDATE indexes SET last_indexed_at = ? WHERE id = ?",
            (last_indexed_at or utc_now(), index_id),
        )


def load_index_record(connection: sqlite3.Connection, index_id: str) -> IndexRecord:
    row = connection.execute(
        "SELECT id, repository_root, index_path, metadata_path, created_at, last_indexed_at FROM indexes WHERE id = ?",
        (index_id,),
    ).fetchone()
    if row is None:
        raise KeyError(index_id)
    return IndexRecord(
        id=row["id"],
        repositoryRoot=row["repository_root"],
        indexPath=row["index_path"],
        metadataPath=row["metadata_path"],
        createdAt=row["created_at"],
        lastIndexedAt=row["last_indexed_at"],
    )


def load_index_record_by_repository_root(connection: sqlite3.Connection, repository_root: str | Path) -> IndexRecord | None:
    row = connection.execute(
        "SELECT id, repository_root, index_path, metadata_path, created_at, last_indexed_at FROM indexes WHERE repository_root = ? ORDER BY created_at LIMIT 1",
        (str(Path(repository_root).expanduser().resolve()),),
    ).fetchone()
    if row is None:
        return None
    return IndexRecord(
        id=row["id"],
        repositoryRoot=row["repository_root"],
        indexPath=row["index_path"],
        metadataPath=row["metadata_path"],
        createdAt=row["created_at"],
        lastIndexedAt=row["last_indexed_at"],
    )


def _encode_vector(vector: Sequence[float]) -> str:
    return json.dumps([float(value) for value in vector], separators=(",", ":"))


def _decode_vector(payload: str) -> tuple[float, ...]:
    return tuple(float(value) for value in json.loads(payload))


def upsert_chunk(
    connection: sqlite3.Connection,
    *,
    index_id: str,
    chunk: CodeChunk,
    source_file_path: str | Path | None = None,
    lifecycle_state: str = "added",
) -> VectorEntry:
    source_file = normalize_path(source_file_path or chunk.sourceFilePath)
    entry = VectorEntry.from_chunk(
        CodeChunk(
            id=chunk.id,
            content=chunk.content,
            embedding=chunk.embedding,
            sourceSymbolId=chunk.sourceSymbolId,
            sourceFilePath=source_file,
            chunkType=chunk.chunkType,
            metadata=dict(chunk.metadata),
        )
    )
    existing = connection.execute("SELECT 1 FROM chunks WHERE id = ?", (entry.chunkId,)).fetchone()
    state = "replaced" if existing else lifecycle_state
    timestamp = utc_now()
    with connection:
        connection.execute(
            """
            INSERT INTO chunks (id, index_id, source_file_path, source_symbol_id, chunk_type, content, embedding, dimensionality, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                index_id = excluded.index_id,
                source_file_path = excluded.source_file_path,
                source_symbol_id = excluded.source_symbol_id,
                chunk_type = excluded.chunk_type,
                content = excluded.content,
                embedding = excluded.embedding,
                dimensionality = excluded.dimensionality,
                updated_at = excluded.updated_at
            """,
            (
                entry.chunkId,
                index_id,
                entry.sourceFilePath,
                entry.sourceSymbolId,
                entry.chunkType,
                entry.content,
                _encode_vector(entry.vector),
                entry.dimensionality,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO chunk_lifecycle (chunk_id, source_file_path, lifecycle_state, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                source_file_path = excluded.source_file_path,
                lifecycle_state = excluded.lifecycle_state,
                updated_at = excluded.updated_at
            """,
            (entry.chunkId, entry.sourceFilePath, state, timestamp),
        )
    return entry


def upsert_chunks(
    connection: sqlite3.Connection,
    *,
    index_id: str,
    chunks: Iterable[CodeChunk],
    source_file_path: str | Path | None = None,
) -> tuple[VectorEntry, ...]:
    return tuple(
        upsert_chunk(
            connection,
            index_id=index_id,
            chunk=chunk,
            source_file_path=source_file_path,
        )
        for chunk in chunks
    )


def load_entries(connection: sqlite3.Connection, *, index_id: str) -> list[VectorEntry]:
    rows = connection.execute(
        """
        SELECT id, source_file_path, source_symbol_id, chunk_type, content, embedding, dimensionality
        FROM chunks
        WHERE index_id = ?
        ORDER BY source_file_path, source_symbol_id, id
        """,
        (index_id,),
    ).fetchall()
    return [
        VectorEntry(
            chunkId=row["id"],
            vector=_decode_vector(row["embedding"]),
            dimensionality=row["dimensionality"],
            sourceFilePath=row["source_file_path"],
            sourceSymbolId=row["source_symbol_id"],
            chunkType=row["chunk_type"],
            content=row["content"],
        )
        for row in rows
    ]


def load_chunks_for_file(connection: sqlite3.Connection, *, index_id: str, source_file_path: str | Path) -> list[VectorEntry]:
    rows = connection.execute(
        """
        SELECT id, source_file_path, source_symbol_id, chunk_type, content, embedding, dimensionality
        FROM chunks
        WHERE index_id = ? AND source_file_path = ?
        ORDER BY id
        """,
        (index_id, normalize_path(source_file_path)),
    ).fetchall()
    return [
        VectorEntry(
            chunkId=row["id"],
            vector=_decode_vector(row["embedding"]),
            dimensionality=row["dimensionality"],
            sourceFilePath=row["source_file_path"],
            sourceSymbolId=row["source_symbol_id"],
            chunkType=row["chunk_type"],
            content=row["content"],
        )
        for row in rows
    ]


def delete_chunks_for_file(connection: sqlite3.Connection, *, index_id: str, source_file_path: str | Path) -> tuple[str, ...]:
    normalized = normalize_path(source_file_path)
    rows = connection.execute(
        "SELECT id FROM chunks WHERE index_id = ? AND source_file_path = ?",
        (index_id, normalized),
    ).fetchall()
    chunk_ids = tuple(row["id"] for row in rows)
    timestamp = utc_now()
    with connection:
        for chunk_id in chunk_ids:
            connection.execute(
                """
                INSERT INTO chunk_lifecycle (chunk_id, source_file_path, lifecycle_state, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    source_file_path = excluded.source_file_path,
                    lifecycle_state = excluded.lifecycle_state,
                    updated_at = excluded.updated_at
                """,
                (chunk_id, normalized, "removed", timestamp),
            )
        connection.execute(
            "DELETE FROM chunks WHERE index_id = ? AND source_file_path = ?",
            (index_id, normalized),
        )
    return chunk_ids


def load_lifecycle_state(connection: sqlite3.Connection, *, source_file_path: str | Path | None = None) -> dict[str, str]:
    if source_file_path is None:
        rows = connection.execute("SELECT chunk_id, lifecycle_state FROM chunk_lifecycle").fetchall()
    else:
        rows = connection.execute(
            "SELECT chunk_id, lifecycle_state FROM chunk_lifecycle WHERE source_file_path = ?",
            (normalize_path(source_file_path),),
        ).fetchall()
    return {row["chunk_id"]: row["lifecycle_state"] for row in rows}
