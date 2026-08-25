from __future__ import annotations

import json
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from repository_metadata.sqlite_store import connect

from .models import ChatMessage, ChatSession


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_session(db_path: str | Path, session_id: str) -> ChatSession:
    """Persist a new `chat_sessions` row for an already-generated session id.

    Uses a plain INSERT (no upsert) so a colliding id raises rather than
    silently overwriting an existing session.
    """
    now = _utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            connection.execute(
                "INSERT INTO chat_sessions (id, created_at, last_activity_at) VALUES (?, ?, ?)",
                (session_id, now, now),
            )
    return ChatSession(id=session_id, createdAt=now, lastActivityAt=now)


def touch_session(db_path: str | Path, session_id: str) -> None:
    """Refresh `last_activity_at` for a session. `append_message` performs the
    equivalent update itself, in the same transaction as the message insert,
    for atomicity - this standalone entry point exists for the public
    contract and isn't otherwise called by `append_message`."""
    with closing(connect(db_path)) as connection:
        with connection:
            connection.execute(
                "UPDATE chat_sessions SET last_activity_at = ? WHERE id = ?",
                (_utc_now(), session_id),
            )


def append_message(db_path: str | Path, session_id: str, message: ChatMessage) -> None:
    """Insert exactly one `chat_messages` row and refresh the owning
    session's `last_activity_at`, in a single transaction.

    `sequence` is a globally monotonic tie-breaker (max existing rowid + 1)
    rather than a per-session count, so appending never requires scanning or
    aggregating the session's own prior messages - the write stays O(1)
    regardless of how long the session already is (FR-004/SC-003).
    """
    with closing(connect(db_path)) as connection:
        with connection:
            exists = connection.execute("SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            if exists is None:
                raise KeyError(session_id)
            connection.execute(
                """
                INSERT INTO chat_messages
                    (id, session_id, role, content, cited_symbol_ids, cited_file_paths, timestamp, sequence, generated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT COALESCE(MAX(rowid), 0) + 1 FROM chat_messages), ?)
                """,
                (
                    uuid.uuid4().hex,
                    session_id,
                    message.role,
                    message.content,
                    json.dumps(list(message.citedSymbolIds)),
                    json.dumps(list(message.citedFilePaths)),
                    message.timestamp,
                    message.generatedBy,
                ),
            )
            connection.execute(
                "UPDATE chat_sessions SET last_activity_at = ? WHERE id = ?",
                (_utc_now(), session_id),
            )


def load_session(db_path: str | Path, session_id: str) -> ChatSession:
    """Return the session's identity/timestamps, with an empty `messages`
    list - callers combine this with `load_messages` themselves. Raises
    `KeyError` for an unknown id, mirroring
    `repository_metadata.sqlite_store.load_repository`'s convention."""
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            "SELECT id, created_at, last_activity_at FROM chat_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return ChatSession(
            id=row["id"],
            createdAt=row["created_at"],
            lastActivityAt=row["last_activity_at"],
            messages=[],
        )


def list_sessions(db_path: str | Path) -> tuple[ChatSession, ...]:
    """Every persisted session, most-recently-active first, with an empty
    `messages` list per entry (a summary, not a history - callers use
    `load_messages`/`load_session` for a specific session's full content).
    Reads directly from SQLite rather than any in-memory cache, so a
    session created in a previous process is included."""
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT id, created_at, last_activity_at FROM chat_sessions ORDER BY last_activity_at DESC",
        ).fetchall()
    return tuple(
        ChatSession(
            id=row["id"],
            createdAt=row["created_at"],
            lastActivityAt=row["last_activity_at"],
            messages=[],
        )
        for row in rows
    )


def load_messages(db_path: str | Path, session_id: str) -> tuple[ChatMessage, ...]:
    """A session's full message history, ordered by (timestamp, sequence),
    in one query. Returns an empty tuple - never raises - for a session that
    exists but has no messages yet, or for an unknown session id (callers
    that must distinguish "unknown" use `load_session` first)."""
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT role, content, cited_symbol_ids, cited_file_paths, timestamp, generated_by
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY timestamp, sequence
            """,
            (session_id,),
        ).fetchall()
    return tuple(
        ChatMessage(
            role=row["role"],
            content=row["content"],
            citedSymbolIds=tuple(json.loads(row["cited_symbol_ids"])),
            citedFilePaths=tuple(json.loads(row["cited_file_paths"])),
            timestamp=row["timestamp"],
            generatedBy=row["generated_by"],
        )
        for row in rows
    )
