from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Union
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_event_id(*, stage: str, attempted_provider: str, timestamp: str) -> str:
    seed = f"{stage}|{attempted_provider}|{timestamp}"
    return f"failover_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"


@dataclass(frozen=True, slots=True)
class FailoverLogEntry:
    id: str
    timestamp: str
    stage: str
    attemptedProvider: str
    resultProvider: Optional[str]
    reason: str


def append_failover_event(
    connection: sqlite3.Connection,
    *,
    stage: str,
    attempted_provider: str,
    result_provider: Optional[str],
    reason: str,
) -> None:
    """Append one row to `engine_failover_log` (contracts/sqlite-schema-deltas.md).

    `connection` is an already-open connection to the `repository_metadata`
    SQLite file - this module never opens its own connection, keeping it
    decoupled from `repository_metadata` (research.md §1's layering).
    """
    timestamp = _utc_now()
    event_id = _stable_event_id(stage=stage, attempted_provider=attempted_provider, timestamp=timestamp)
    with connection:
        connection.execute(
            """
            INSERT INTO engine_failover_log (id, timestamp, stage, attempted_provider, result_provider, reason)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, timestamp, stage, attempted_provider, result_provider, reason),
        )


def list_failover_events(
    connection: sqlite3.Connection, *, stage: Optional[str] = None, limit: int = 100
) -> tuple[FailoverLogEntry, ...]:
    if stage is not None:
        rows = connection.execute(
            """
            SELECT id, timestamp, stage, attempted_provider, result_provider, reason
            FROM engine_failover_log WHERE stage = ? ORDER BY timestamp DESC LIMIT ?
            """,
            (stage, limit),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT id, timestamp, stage, attempted_provider, result_provider, reason
            FROM engine_failover_log ORDER BY timestamp DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return tuple(
        FailoverLogEntry(
            id=row["id"],
            timestamp=row["timestamp"],
            stage=row["stage"],
            attemptedProvider=row["attempted_provider"],
            resultProvider=row["result_provider"],
            reason=row["reason"],
        )
        for row in rows
    )


@dataclass(slots=True)
class SqliteFailoverLog:
    """Binds `append_failover_event`/`list_failover_events` to one open
    connection, so it can be handed directly to `FailoverExecutor` as its
    `failover_log` callback (matches `FailoverLogWriter`'s call signature).

    Prefer `PathFailoverLog` for anything longer-lived than a single
    request/command - this class's connection stays open for as long as
    something holds a reference to it, same as any other open
    `sqlite3.Connection`."""

    connection: sqlite3.Connection

    def __call__(
        self, *, stage: str, attempted_provider: str, result_provider: Optional[str], reason: str
    ) -> None:
        append_failover_event(
            self.connection,
            stage=stage,
            attempted_provider=attempted_provider,
            result_provider=result_provider,
            reason=reason,
        )

    def list(self, *, stage: Optional[str] = None, limit: int = 100) -> tuple[FailoverLogEntry, ...]:
        return list_failover_events(self.connection, stage=stage, limit=limit)


@dataclass(slots=True)
class PathFailoverLog:
    """Opens a fresh connection per call rather than holding one open for its
    own lifetime - mirrors this codebase's existing per-operation-connect
    convention (`repository_metadata.store`, `chat.sqlite_store`).

    An actual provider switch is rare, so paying one connect/close per event
    is negligible - and avoids an otherwise-open `sqlite3.Connection` on the
    metadata db outliving whatever built the `FailoverExecutor`, which can
    block a later rename/replace of that file on Windows (`SqliteFailoverLog`
    doesn't have this problem only because *something* remembers to close
    it - this class needs nothing to).

    `connect` is injected (rather than imported here) so this module stays
    decoupled from `repository_metadata` (research.md §1's layering) -
    callers pass `repository_metadata.sqlite_store.connect`.
    """

    metadata_db_path: Union[str, Path]
    connect: Callable[[Union[str, Path]], sqlite3.Connection]

    def __call__(
        self, *, stage: str, attempted_provider: str, result_provider: Optional[str], reason: str
    ) -> None:
        connection = self.connect(self.metadata_db_path)
        try:
            append_failover_event(
                connection,
                stage=stage,
                attempted_provider=attempted_provider,
                result_provider=result_provider,
                reason=reason,
            )
        finally:
            connection.close()
