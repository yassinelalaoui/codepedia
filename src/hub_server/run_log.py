"""What is remembered about a run after it ends.

`~/.codepedia/runs.sqlite`, one row per run (data-model.md §2). This is the only
durable state feature 037 adds, and it stays inside constitution 2.6: that
principle forbids an external database server, a broker or cloud storage, and
expressly permits embedded local storage - "SQLite et un index vectoriel local
sur fichier".

Deliberately a *separate* database from any repository's metadata. A run record
has to outlive the analysis it describes: a failed run leaves no state directory
at all, and spec FR-041's Remove deletes a repository's directory outright.
Storing this per repository would lose exactly the records worth keeping.

Every read here is total. A missing file, a database written by a future
version, a half-written file left by a killed process - all return empty rather
than raising (spec FR-026e). The homepage showing no history is a small loss;
the homepage failing to load because of a history file is not acceptable.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from cli import paths as cli_paths

# Spec FR-026c requires at least the 20 most recent. 50 keeps a little history
# for spotting a provider that fails repeatedly, at a few tens of kilobytes.
RETAINED_RUNS = 50

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    repository_path     TEXT NOT NULL,
    kind                TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    ended_at            TEXT,
    outcome             TEXT,
    failed_stage        TEXT,
    failure_message     TEXT
);
CREATE INDEX IF NOT EXISTS runs_started_at ON runs (started_at DESC);
"""


@dataclass(frozen=True, slots=True)
class RunRecord:
    runId: str
    repositoryPath: str
    kind: str
    startedAt: str
    endedAt: Optional[str] = None
    outcome: Optional[str] = None
    failedStage: Optional[str] = None
    failureMessage: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": self.runId,
            "repositoryPath": self.repositoryPath,
            "kind": self.kind,
            "startedAt": self.startedAt,
            "endedAt": self.endedAt,
            "outcome": self.outcome,
            "failedStage": self.failedStage,
            "failureMessage": self.failureMessage,
        }


def run_log_path() -> Path:
    return cli_paths.codepedia_home() / "runs.sqlite"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    path = run_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


class RunLog:
    """Append, close, prune, sweep, read. One instance per hub process."""

    def append(
        self, *, run_id: str, repository_path: str, kind: str, started_at: Optional[str] = None
    ) -> None:
        """Record a run as started, with no outcome yet.

        The NULL outcome is what `sweep_interrupted` later keys on, so this must
        be written when the run *starts* rather than when it ends - a hub killed
        mid-run never gets to write anything else (spec FR-026d).
        """
        with _connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO runs (run_id, repository_path, kind, started_at) VALUES (?, ?, ?, ?)",
                (run_id, repository_path, kind, started_at or now_iso()),
            )
        self.prune()

    def close(
        self,
        *,
        run_id: str,
        outcome: str,
        failed_stage: Optional[str] = None,
        failure_message: Optional[str] = None,
    ) -> None:
        """Record how a run ended, including what to tell the person about it."""
        with _connect() as connection:
            connection.execute(
                """
                UPDATE runs
                   SET ended_at = ?, outcome = ?, failed_stage = ?, failure_message = ?
                 WHERE run_id = ?
                """,
                (
                    now_iso(),
                    outcome,
                    failed_stage,
                    failure_message,
                    run_id,
                ),
            )

    def prune(self, keep: int = RETAINED_RUNS) -> None:
        """Keep the newest `keep` rows. Spec FR-026c: no manual cleanup."""
        with _connect() as connection:
            connection.execute(
                """
                DELETE FROM runs
                 WHERE run_id NOT IN (
                     SELECT run_id FROM runs ORDER BY started_at DESC, rowid DESC LIMIT ?
                 )
                """,
                (keep,),
            )

    def sweep_interrupted(self) -> int:
        """Close out runs whose hub died, at hub startup (spec FR-026d).

        A row with a NULL outcome can only belong to a run whose process is
        gone: spec FR-012 guarantees there was at most one, and the process
        reading this is a new one. So no liveness tracking is needed - the NULL
        *is* the evidence. Without this, such a run would read as still in
        progress forever and block every future analysis.
        """
        try:
            with _connect() as connection:
                cursor = connection.execute(
                    "UPDATE runs SET outcome = 'interrupted', ended_at = ? WHERE outcome IS NULL",
                    (now_iso(),),
                )
                return cursor.rowcount or 0
        except sqlite3.Error:
            return 0

    def recent(self, limit: int = RETAINED_RUNS) -> list[RunRecord]:
        """Newest first. Returns `[]` rather than raising, always.

        Spec FR-026e: a run log that is missing, unreadable, or written by an
        older version must not stop the homepage loading.
        """
        try:
            with _connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM runs ORDER BY started_at DESC, rowid DESC LIMIT ?", (limit,)
                ).fetchall()
        except (sqlite3.Error, OSError, ValueError):
            return []

        records: list[RunRecord] = []
        for row in rows:
            try:
                records.append(_record_from_row(row))
            except (KeyError, IndexError, ValueError, TypeError):
                # One unreadable row does not cost the others, mirroring how the
                # analyse history tolerates one unreadable entry (spec FR-031).
                continue
        return records


def _record_from_row(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        runId=row["run_id"],
        repositoryPath=row["repository_path"],
        kind=row["kind"],
        startedAt=row["started_at"],
        endedAt=row["ended_at"],
        outcome=row["outcome"],
        failedStage=row["failed_stage"],
        failureMessage=row["failure_message"],
    )
