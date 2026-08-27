from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

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


def _connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
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

    def save_entry(self, repository_id: str, entry: PageManifestEntry) -> None:
        with closing(_connect(self.db_path)) as connection:
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
        with closing(_connect(self.db_path)) as connection:
            row = connection.execute("SELECT * FROM doc_pages WHERE page_id = ?", (page_id,)).fetchone()
            return _row_to_entry(row) if row is not None else None

    def list_entries(self, repository_id: str) -> tuple[PageManifestEntry, ...]:
        with closing(_connect(self.db_path)) as connection:
            rows = connection.execute(
                "SELECT * FROM doc_pages WHERE repository_id = ? ORDER BY page_id",
                (repository_id,),
            ).fetchall()
            return tuple(_row_to_entry(row) for row in rows)

    def delete_entry(self, page_id: str) -> None:
        with closing(_connect(self.db_path)) as connection:
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
        with closing(_connect(self.db_path)) as connection:
            row = connection.execute(
                """
                SELECT title, description FROM doc_section_narrations
                WHERE repository_id = ? AND section_key = ? AND membership_hash = ?
                """,
                (repository_id, section_key, membership_hash),
            ).fetchone()
            return (row["title"], row["description"]) if row is not None else None

    def save_section_narration(
        self, repository_id: str, section_key: str, membership_hash: str, *, title: str, description: str
    ) -> None:
        with closing(_connect(self.db_path)) as connection:
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
        with closing(_connect(self.db_path)) as connection:
            with connection:
                connection.executemany("DELETE FROM doc_pages WHERE page_id = ?", [(page_id,) for page_id in page_ids])


def open_doc_manifest_store(db_path: str | Path) -> DocPageManifestStore:
    return DocPageManifestStore(db_path=Path(db_path))