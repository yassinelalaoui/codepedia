from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlite_support import apply_write_pragmas

from .models import PageManifestEntry

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS doc_pages (
        page_id TEXT PRIMARY KEY,
        repository_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        source_symbol_ids TEXT NOT NULL,
        linked_page_ids TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        output_path_markdown TEXT NOT NULL,
        output_path_html TEXT NOT NULL,
        last_generated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_doc_pages_repository ON doc_pages(repository_id)",
    # Section titles/descriptions are the one part of a section page that costs
    # a model call, so they are cached against the membership that produced
    # them: an unchanged section is never re-narrated, and a section whose
    # members changed is narrated exactly once more.
    """
    CREATE TABLE IF NOT EXISTS doc_section_narrations (
        repository_id TEXT NOT NULL,
        section_key TEXT NOT NULL,
        membership_hash TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        PRIMARY KEY (repository_id, section_key)
    )
    """,
)


def _connect(db_path: str | Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open the manifest database, schema ensured.

    `check_same_thread=False` is for `DocPageManifestStore.session`, which hands
    one connection to a whole generation pass - `serve` regenerates from the
    watcher's thread while the main thread may still hold the store.
    """
    connection = sqlite3.connect(str(db_path), check_same_thread=check_same_thread)
    connection.row_factory = sqlite3.Row
    apply_write_pragmas(connection)
    for statement in SCHEMA_STATEMENTS:
        connection.execute(statement)
    return connection


def _row_to_entry(row: sqlite3.Row) -> PageManifestEntry:
    return PageManifestEntry(
        pageId=row["page_id"],
        kind=row["kind"],
        sourceSymbolIds=tuple(json.loads(row["source_symbol_ids"])),
        contentHash=row["content_hash"],
        outputPathMarkdown=row["output_path_markdown"],
        outputPathHtml=row["output_path_html"],
        lastGeneratedAt=row["last_generated_at"],
        linkedPageIds=tuple(json.loads(row["linked_page_ids"])),
    )


@dataclass(slots=True)
class DocPageManifestStore:
    db_path: Path
    # Set only while a `session()` is open; see that method for why.
    _session_connection: sqlite3.Connection | None = field(default=None, repr=False, compare=False)
    _session_depth: int = field(default=0, repr=False, compare=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def session(self) -> "_ManifestSession":
        """Hold one connection open for a whole generation pass.

        The third instance of the defect the vector index and the metadata
        store were both carrying: every method below opened its own connection,
        replayed the schema, wrote one row, committed and closed - once per page
        written, on a loop that writes every page of the wiki. Same shape, same
        cost, same fix.

        Re-entrant and safe across threads for the same reasons as
        `RepositoryMetadataStore.session`, which this mirrors deliberately: two
        stores solving one problem two different ways is how the next reader
        ends up believing they are solving two problems.
        """
        return _ManifestSession(self)

    def _connection(self) -> "_ManifestConnection":
        """The session's connection when there is one, a fresh one otherwise."""
        return _ManifestConnection(self)

    def save_entry(self, repository_id: str, entry: PageManifestEntry) -> None:
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO doc_pages (
                        page_id, repository_id, kind, source_symbol_ids, linked_page_ids,
                        content_hash, output_path_markdown, output_path_html, last_generated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(page_id) DO UPDATE SET
                        repository_id = excluded.repository_id,
                        kind = excluded.kind,
                        source_symbol_ids = excluded.source_symbol_ids,
                        linked_page_ids = excluded.linked_page_ids,
                        content_hash = excluded.content_hash,
                        output_path_markdown = excluded.output_path_markdown,
                        output_path_html = excluded.output_path_html,
                        last_generated_at = excluded.last_generated_at
                    """,
                    (
                        entry.pageId,
                        repository_id,
                        entry.kind,
                        json.dumps(list(entry.sourceSymbolIds)),
                        json.dumps(list(entry.linkedPageIds)),
                        entry.contentHash,
                        entry.outputPathMarkdown,
                        entry.outputPathHtml,
                        entry.lastGeneratedAt,
                    ),
                )

    def load_entry(self, page_id: str) -> PageManifestEntry | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM doc_pages WHERE page_id = ?", (page_id,)).fetchone()
            return _row_to_entry(row) if row is not None else None

    def list_entries(self, repository_id: str) -> tuple[PageManifestEntry, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM doc_pages WHERE repository_id = ? ORDER BY page_id",
                (repository_id,),
            ).fetchall()
            return tuple(_row_to_entry(row) for row in rows)

    def delete_entry(self, page_id: str) -> None:
        with self._connection() as connection:
            with connection:
                connection.execute("DELETE FROM doc_pages WHERE page_id = ?", (page_id,))

    def load_section_narration(
        self, repository_id: str, section_key: str, membership_hash: str
    ) -> tuple[str, str] | None:
        """The cached (title, description) for this exact membership, if any.

        A row whose `membership_hash` no longer matches is treated as absent
        rather than returned stale - the section it described is not the section
        being rendered.
        """
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT title, description FROM doc_section_narrations
                WHERE repository_id = ? AND section_key = ? AND membership_hash = ?
                """,
                (repository_id, section_key, membership_hash),
            ).fetchone()
            return (row["title"], row["description"]) if row is not None else None

    def list_section_titles(self, repository_id: str) -> dict[str, str]:
        """Every section's currently stored title, keyed by section key.

        Unlike `load_section_narration` this ignores `membership_hash`: the
        caller is asking what the sidebar *says today*, not whether a cached
        narration may be reused. The two questions diverge exactly when a
        section's membership changed, which is one of the cases the navigation
        has to notice.
        """
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT section_key, title FROM doc_section_narrations WHERE repository_id = ?",
                (repository_id,),
            ).fetchall()
            return {row["section_key"]: row["title"] for row in rows}

    def save_section_narration(
        self, repository_id: str, section_key: str, membership_hash: str, *, title: str, description: str
    ) -> None:
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO doc_section_narrations (
                        repository_id, section_key, membership_hash, title, description, generated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(repository_id, section_key) DO UPDATE SET
                        membership_hash = excluded.membership_hash,
                        title = excluded.title,
                        description = excluded.description,
                        generated_at = excluded.generated_at
                    """,
                    (
                        repository_id,
                        section_key,
                        membership_hash,
                        title,
                        description,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

    def delete_entries(self, page_ids: Iterable[str]) -> None:
        with self._connection() as connection:
            with connection:
                connection.executemany("DELETE FROM doc_pages WHERE page_id = ?", [(page_id,) for page_id in page_ids])


class _ManifestSession:
    """`DocPageManifestStore.session`'s context manager.

    A class rather than a `@contextmanager` generator for the reason
    `cli/index_command.py`'s `_stage` spells out: `contextlib`'s wrapper
    assigns `exc.__traceback__` when an exception passes through it, and this
    codebase's engine errors are frozen dataclasses that raise
    `FrozenInstanceError` on any attribute assignment. Section narration runs
    inside this pass, so a provider error really does travel through here.
    """

    __slots__ = ("_store",)

    def __init__(self, store: "DocPageManifestStore") -> None:
        self._store = store

    def __enter__(self) -> "DocPageManifestStore":
        store = self._store
        with store._lock:
            if store._session_connection is None:
                store._session_connection = _connect(store.db_path, check_same_thread=False)
            store._session_depth += 1
        return store

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        store = self._store
        with store._lock:
            store._session_depth -= 1
            if store._session_depth == 0 and store._session_connection is not None:
                connection, store._session_connection = store._session_connection, None
                connection.close()
        return False


class _ManifestConnection:
    """One store call's connection - shared under the lock, or opened for it."""

    __slots__ = ("_store", "_shared", "_owned")

    def __init__(self, store: "DocPageManifestStore") -> None:
        self._store = store
        self._shared: sqlite3.Connection | None = None
        self._owned: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        store = self._store
        store._lock.acquire()
        shared = store._session_connection
        if shared is not None:
            self._shared = shared
            return shared
        store._lock.release()
        self._owned = _connect(store.db_path)
        return self._owned

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if self._shared is not None:
            self._shared = None
            self._store._lock.release()
        elif self._owned is not None:
            connection, self._owned = self._owned, None
            connection.close()
        return False



def open_doc_manifest_store(db_path: str | Path) -> DocPageManifestStore:
    return DocPageManifestStore(db_path=Path(db_path))