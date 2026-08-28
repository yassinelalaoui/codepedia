from __future__ import annotations

import json
import re
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


def stable_index_id(repository_root: str | Path, metadata_path: str | Path) -> str:
    normalized = "|".join(
        [
            Path(repository_root).expanduser().resolve().as_posix(),
            normalize_path(metadata_path),
        ]
    )
    import hashlib

    return f"vector_index_{hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:16]}"


def connect(metadata_path: str | Path) -> sqlite3.Connection:
    path = Path(metadata_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    # `serve` opens the index on the main thread but writes from the watcher's
    # debounce timer thread, and answers chat searches from uvicorn's loop
    # thread. sqlite3's default same-thread guard rejects both. Access is
    # serialized by VectorIndex's own reentrant lock instead.
    connection = sqlite3.connect(str(path), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    for statement in SCHEMA_STATEMENTS:
        connection.execute(statement)
    _ensure_chunks_embedding_model_id_column(connection)
    _ensure_chunks_fts_index(connection)


def _ensure_chunks_embedding_model_id_column(connection: sqlite3.Connection) -> None:
    # ALTER TABLE ADD COLUMN has no IF NOT EXISTS equivalent - guarded
    # separately so re-running against an already-migrated database doesn't
    # raise sqlite3.OperationalError (contracts/sqlite-schema-deltas.md).
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(chunks)").fetchall()}
    if "embedding_model_id" not in columns:
        with connection:
            connection.execute("ALTER TABLE chunks ADD COLUMN embedding_model_id TEXT NOT NULL DEFAULT ''")


def _ensure_chunks_fts_index(connection: sqlite3.Connection) -> None:
    """Create and, for a pre-existing database, backfill the lexical index.

    A standalone FTS5 table rather than an external-content one: `chunks.id` is
    TEXT, and external content requires an INTEGER rowid that stays stable
    across a VACUUM. Duplicating `content` costs disk but keeps the two tables
    independently correct, and sync is explicit at the only two write points
    (`upsert_chunk`, `delete_chunks_for_file`).

    Additive and idempotent, matching `_ensure_chunks_embedding_model_id_column`
    and contracts/sqlite-schema-deltas.md - there is no schema-version column in
    this project, so migrations are introspection-guarded.
    """
    connection.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts "
        "USING fts5(content, chunk_id UNINDEXED, index_id UNINDEXED)"
    )
    # Backfill runs once, for a database indexed before this table existed. The
    # guard matters: ensure_schema runs on every connect(), and `serve` reopens a
    # populated index on every start.
    already = connection.execute("SELECT 1 FROM chunks_fts LIMIT 1").fetchone()
    if already is not None:
        return
    pending = connection.execute("SELECT 1 FROM chunks LIMIT 1").fetchone()
    if pending is None:
        return
    with connection:
        connection.execute(
            "INSERT INTO chunks_fts (content, chunk_id, index_id) "
            "SELECT content, id, index_id FROM chunks"
        )


def _replace_fts_row(connection: sqlite3.Connection, *, chunk_id: str, index_id: str, content: str) -> None:
    connection.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
    connection.execute(
        "INSERT INTO chunks_fts (content, chunk_id, index_id) VALUES (?, ?, ?)",
        (content, chunk_id, index_id),
    )


def build_match_expression(query_text: str) -> str:
    """Turn free text into an FTS5 MATCH expression that cannot be a syntax error.

    A raw user question reaches FTS5 with quotes, hyphens and parentheses that
    are all operators in its query grammar. Every token is extracted and quoted
    as a string literal instead, then OR-ed, so the worst case is no match rather
    than an OperationalError mid-question.
    """
    tokens = re.findall(r"[A-Za-z0-9_]+", query_text)
    if not tokens:
        return ""
    quoted = [chr(34) + token + chr(34) for token in dict.fromkeys(tokens)]
    return " OR ".join(quoted)


def search_lexical(
    connection: sqlite3.Connection, *, index_id: str, query_text: str, limit: int
) -> tuple[str, ...]:
    """Chunk ids for `query_text`, best BM25 match first."""
    expression = build_match_expression(query_text)
    if not expression or limit <= 0:
        return ()
    rows = connection.execute(
        "SELECT chunk_id FROM chunks_fts "
        "WHERE index_id = ? AND chunks_fts MATCH ? "
        "ORDER BY bm25(chunks_fts) LIMIT ?",
        (index_id, expression, limit),
    ).fetchall()
    return tuple(row["chunk_id"] for row in rows)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _existing_index_id_for_repository(connection: sqlite3.Connection, repository_root: str) -> str | None:
    """The id this file already stores for `repository_root`, if any.

    One metadata file only ever holds one repository's index, so an existing
    row for that repository *is* this index - whatever path it was created
    under.
    """
    row = connection.execute(
        "SELECT id FROM indexes WHERE repository_root = ? ORDER BY created_at LIMIT 1",
        (repository_root,),
    ).fetchone()
    return row["id"] if row is not None else None


def ensure_index_record(
    connection: sqlite3.Connection,
    *,
    repository_root: str | Path,
    metadata_path: str | Path,
    index_id: str | None = None,
) -> IndexRecord:
    """Find this repository's index in `connection`, or start one.

    `stable_index_id` derives an id from the repository root *and* the
    metadata file's path. That second half makes the id change when the file
    moves - and `cli/index_command.py` always builds into a
    `<state>.staging-<pid>` directory and renames it into place on success.
    Deriving the id unconditionally therefore orphaned every index the moment
    it was published: the chunks stayed in the file under the staging-derived
    id, while opening the same file at its final path minted a second, empty
    record and reported zero chunks. Looking the repository up first is what
    makes an index survive the rename that publishes it.
    """
    resolved_root = str(Path(repository_root).expanduser().resolve())
    resolved_id = index_id or _existing_index_id_for_repository(connection, resolved_root)
    record = IndexRecord(
        id=resolved_id or stable_index_id(repository_root, metadata_path),
        repositoryRoot=resolved_root,
        metadataPath=str(Path(metadata_path).expanduser()),
    )
    with connection:
        connection.execute(
            """
            INSERT INTO indexes (id, repository_root, metadata_path, created_at, last_indexed_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                repository_root = excluded.repository_root,
                metadata_path = excluded.metadata_path,
                last_indexed_at = excluded.last_indexed_at
            """,
            (
                record.id,
                record.repositoryRoot,
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
        "SELECT id, repository_root, metadata_path, created_at, last_indexed_at FROM indexes WHERE id = ?",
        (index_id,),
    ).fetchone()
    if row is None:
        raise KeyError(index_id)
    return IndexRecord(
        id=row["id"],
        repositoryRoot=row["repository_root"],
        metadataPath=row["metadata_path"],
        createdAt=row["created_at"],
        lastIndexedAt=row["last_indexed_at"],
    )


def load_index_record_by_repository_root(connection: sqlite3.Connection, repository_root: str | Path) -> IndexRecord | None:
    row = connection.execute(
        "SELECT id, repository_root, metadata_path, created_at, last_indexed_at FROM indexes WHERE repository_root = ? ORDER BY created_at LIMIT 1",
        (str(Path(repository_root).expanduser().resolve()),),
    ).fetchone()
    if row is None:
        return None
    return IndexRecord(
        id=row["id"],
        repositoryRoot=row["repository_root"],
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
            embeddingModelId=chunk.embeddingModelId,
        )
    )
    existing = connection.execute("SELECT 1 FROM chunks WHERE id = ?", (entry.chunkId,)).fetchone()
    state = "replaced" if existing else lifecycle_state
    timestamp = utc_now()
    with connection:
        connection.execute(
            """
            INSERT INTO chunks (id, index_id, source_file_path, source_symbol_id, chunk_type, content, embedding, dimensionality, embedding_model_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                index_id = excluded.index_id,
                source_file_path = excluded.source_file_path,
                source_symbol_id = excluded.source_symbol_id,
                chunk_type = excluded.chunk_type,
                content = excluded.content,
                embedding = excluded.embedding,
                dimensionality = excluded.dimensionality,
                embedding_model_id = excluded.embedding_model_id,
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
                entry.embeddingModelId,
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
        _replace_fts_row(
            connection, chunk_id=entry.chunkId, index_id=index_id, content=entry.content
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
        SELECT id, source_file_path, source_symbol_id, chunk_type, content, embedding, dimensionality, embedding_model_id
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
            embeddingModelId=row["embedding_model_id"],
        )
        for row in rows
    ]


def load_chunks_for_file(connection: sqlite3.Connection, *, index_id: str, source_file_path: str | Path) -> list[VectorEntry]:
    rows = connection.execute(
        """
        SELECT id, source_file_path, source_symbol_id, chunk_type, content, embedding, dimensionality, embedding_model_id
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
            embeddingModelId=row["embedding_model_id"],
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
        for chunk_id in chunk_ids:
            connection.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
    return chunk_ids


def count_vectors_by_dimensionality(connection: sqlite3.Connection, *, index_id: str) -> dict[int, int]:
    """Row count per dimensionality, so each matrix is allocated once at size."""
    rows = connection.execute(
        "SELECT dimensionality, COUNT(*) AS total FROM chunks WHERE index_id = ? GROUP BY dimensionality",
        (index_id,),
    ).fetchall()
    return {int(row["dimensionality"]): int(row["total"]) for row in rows}


def iter_vector_rows(connection: sqlite3.Connection, *, index_id: str):
    """Stream `(chunk_id, dimensionality, json_payload)` without materializing vectors.

    Deliberately not `load_entries`: that builds a full `VectorEntry` per row,
    each holding a tuple of Python floats at 24 bytes apiece. Streaming the raw
    payload keeps the peak cost one decoded row rather than the whole index.
    """
    cursor = connection.execute(
        "SELECT id, dimensionality, embedding FROM chunks WHERE index_id = ? ORDER BY id",
        (index_id,),
    )
    for row in cursor:
        yield row["id"], int(row["dimensionality"]), row["embedding"]


def load_lifecycle_state(connection: sqlite3.Connection, *, source_file_path: str | Path | None = None) -> dict[str, str]:
    if source_file_path is None:
        rows = connection.execute("SELECT chunk_id, lifecycle_state FROM chunk_lifecycle").fetchall()
    else:
        rows = connection.execute(
            "SELECT chunk_id, lifecycle_state FROM chunk_lifecycle WHERE source_file_path = ?",
            (normalize_path(source_file_path),),
        ).fetchall()
    return {row["chunk_id"]: row["lifecycle_state"] for row in rows}
