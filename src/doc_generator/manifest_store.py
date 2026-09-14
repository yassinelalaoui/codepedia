from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from sqlite_support import apply_write_pragmas

from .models import PageAlias, PageManifestEntry

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
    # The previous navigation scheme's cached group names. Nothing writes this
    # any more; it survives only so the migration in `generator` can find a
    # legacy wiki and drop it. Removing the table outright would make an old
    # database unreadable rather than upgradeable.
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
    # Which templates produced the pages currently on disk. Page content hashes
    # answer "did this page's *inputs* change"; they cannot answer "did the
    # renderer change", because a template is not a source file and appears in no
    # impact set. Without this row, editing the shared layout left every already
    # written page stale and nothing marked it - see `template_fingerprint`.
    """
    CREATE TABLE IF NOT EXISTS doc_render_state (
        repository_id TEXT PRIMARY KEY,
        template_fingerprint TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # Addresses this wiki has published that now belong to a different page.
    #
    # A feature's page id is its anchor module's key, and an anchor is the most
    # internally connected member - so a single new import edge can move it and
    # change the page's URL. Measured on this repository: six of eleven groups
    # are one edge away from a different anchor, one of them an exact tie. That
    # makes a dead bookmark the ordinary outcome of a refactor rather than an
    # edge case, and unlike most defects it cannot be repaired later: once the
    # links are in issues and chat messages they cannot be recalled.
    #
    # `old_page_id` is the primary key because one address resolves to exactly
    # one destination; a later move overwrites it, so a chain of moves collapses
    # to its endpoint rather than needing to be walked.
    """
    CREATE TABLE IF NOT EXISTS doc_page_aliases (
        repository_id TEXT NOT NULL,
        old_page_id TEXT NOT NULL,
        new_page_id TEXT NOT NULL,
        old_output_path_markdown TEXT NOT NULL,
        old_output_path_html TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        PRIMARY KEY (repository_id, old_page_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_doc_page_aliases_repository ON doc_page_aliases(repository_id)",
    # What each feature is currently *called*. Separate from the plan cache
    # because a title is the output of repair, not of the model: a feature the
    # planner never named still has one. `impact` compares these across runs,
    # because a renamed feature changes the sidebar of every already-written page
    # while moving no page id at all.
    """
    CREATE TABLE IF NOT EXISTS doc_features (
        repository_id TEXT NOT NULL,
        feature_key TEXT NOT NULL,
        title TEXT NOT NULL,
        PRIMARY KEY (repository_id, feature_key)
    )
    """,
    # The model's answer to "what features does this repository offer", cached
    # against the repository *structure* that was described to it.
    #
    # `doc_generator` regenerates more than once per index - once for structure,
    # once after summaries land - and again on every incremental run. Without
    # this the one-call-per-plan budget would be spent on every pass over a
    # repository that had not changed.
    #
    # What is stored is the model's raw answer, not the repaired feature set.
    # Repair is deterministic and cheap, so re-running it on load costs nothing
    # and means a change to the repair rules takes effect immediately instead of
    # waiting for the cache to expire.
    """
    CREATE TABLE IF NOT EXISTS doc_feature_plans (
        repository_id TEXT NOT NULL,
        plan_key TEXT NOT NULL,
        plan_json TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        PRIMARY KEY (repository_id)
    )
    """,
    # The model's answer to "what is this repository", cached against the exact
    # prompt that produced it (`overview.narrator.narrative_cache_key`). Same
    # shape and same reasoning as `doc_feature_plans`: the raw reply, not the
    # grounded result, so grounding re-runs on every render against the
    # repository as it is now, and a symbol deleted since the call drops its
    # paragraph without a new call.
    #
    # `handle_map_json` records which feature each `fN` handle meant in that
    # prompt. A key hit never needs it - the same prompt numbers features the
    # same way - but the earlier-version fallback does, because the current
    # evidence may number them differently (038 research Decision 13).
    """
    CREATE TABLE IF NOT EXISTS doc_overview_narratives (
        repository_id TEXT NOT NULL,
        narrative_key TEXT NOT NULL,
        reply_text TEXT NOT NULL,
        handle_map_json TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        repository_fingerprint TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (repository_id)
    )
    """,
)

# Columns added after a table first shipped. `CREATE TABLE IF NOT EXISTS` never
# alters an existing table, so each is added in place when missing - rows
# written before it read back the column's default.
#
# `repository_fingerprint` (038 analyze finding I2): which repository contents a
# narrative described, so a prompt change alone is not reported as an earlier
# version of the repository. An empty value means "unknown", which stays stale.
ADDED_COLUMNS = (
    ("doc_overview_narratives", "repository_fingerprint", "TEXT NOT NULL DEFAULT ''"),
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
    for table, column, declaration in ADDED_COLUMNS:
        present = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in present:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    return connection


def _narrative_row(row: sqlite3.Row | None) -> tuple[str, dict[str, str]] | None:
    """A stored narrative, or `None` for a row that is absent or unreadable.

    Unreadable is a miss, which costs one call - never a crash, and never a
    handle map that silently points subsystem links somewhere wrong.
    """
    if row is None:
        return None
    try:
        handle_map = json.loads(row["handle_map_json"])
    except ValueError:
        return None
    if not isinstance(handle_map, dict):
        return None
    return str(row["reply_text"]), {str(key): str(value) for key, value in handle_map.items()}


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

    def record_alias(
        self,
        repository_id: str,
        *,
        old_page_id: str,
        new_page_id: str,
        old_output_path_markdown: str,
        old_output_path_html: str,
    ) -> None:
        """Remember that `old_page_id`'s address now belongs to `new_page_id`.

        Re-recording the same old address overwrites the destination, so a page
        that moves twice leaves one alias pointing at where it ended up rather
        than a chain nobody walks.
        """
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO doc_page_aliases (
                        repository_id, old_page_id, new_page_id,
                        old_output_path_markdown, old_output_path_html, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(repository_id, old_page_id) DO UPDATE SET
                        new_page_id = excluded.new_page_id,
                        old_output_path_markdown = excluded.old_output_path_markdown,
                        old_output_path_html = excluded.old_output_path_html,
                        recorded_at = excluded.recorded_at
                    """,
                    (
                        repository_id,
                        old_page_id,
                        new_page_id,
                        old_output_path_markdown,
                        old_output_path_html,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

    def list_aliases(self, repository_id: str) -> tuple[PageAlias, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM doc_page_aliases WHERE repository_id = ? ORDER BY old_page_id",
                (repository_id,),
            ).fetchall()
            return tuple(
                PageAlias(
                    oldPageId=row["old_page_id"],
                    newPageId=row["new_page_id"],
                    oldOutputPathMarkdown=row["old_output_path_markdown"],
                    oldOutputPathHtml=row["old_output_path_html"],
                    recordedAt=row["recorded_at"],
                )
                for row in rows
            )

    def aliased_output_paths(self, repository_id: str) -> set[str]:
        """Every output path a redirect stub currently occupies.

        Read by `DocumentationWriter.remove_page` before it unlinks anything.
        A set rather than the aliases themselves because the removal pass asks
        one question - "is this file a redirect?" - and asking it per page over a
        list would be quadratic on a wiki with many moves.
        """
        paths: set[str] = set()
        for alias in self.list_aliases(repository_id):
            paths.add(alias.oldOutputPathMarkdown)
            paths.add(alias.oldOutputPathHtml)
        paths.discard("")
        return paths

    def load_feature_plan(self, repository_id: str, plan_key: str) -> list[dict] | None:
        """The cached plan for this exact repository structure, if any.

        A row whose `plan_key` no longer matches is treated as absent rather than
        returned stale - the repository it described is not the repository being
        documented.
        """
        with self._connection() as connection:
            row = connection.execute(
                "SELECT plan_json FROM doc_feature_plans WHERE repository_id = ? AND plan_key = ?",
                (repository_id, plan_key),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["plan_json"])
        except ValueError:
            # A row written by an older shape, or truncated. Treated as a miss,
            # which costs one call - never as a crash.
            return None
        return payload if isinstance(payload, list) else None

    def save_feature_plan(self, repository_id: str, plan_key: str, features: Iterable[dict]) -> None:
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO doc_feature_plans (repository_id, plan_key, plan_json, generated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(repository_id) DO UPDATE SET
                        plan_key = excluded.plan_key,
                        plan_json = excluded.plan_json,
                        generated_at = excluded.generated_at
                    """,
                    (
                        repository_id,
                        plan_key,
                        json.dumps(list(features)),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

    def load_overview_narrative(
        self, repository_id: str, narrative_key: str
    ) -> tuple[str, dict[str, str]] | None:
        """The cached reply to this exact prompt, with its handle map, if any.

        A row whose key no longer matches is a miss, never a stale answer:
        answering a different prompt's question as if it were this one's is the
        earlier-version fallback's job, and that path says so on the page.
        """
        with self._connection() as connection:
            row = connection.execute(
                "SELECT reply_text, handle_map_json FROM doc_overview_narratives "
                "WHERE repository_id = ? AND narrative_key = ?",
                (repository_id, narrative_key),
            ).fetchone()
        return _narrative_row(row)

    def load_latest_overview_narrative(self, repository_id: str) -> tuple[str, dict[str, str], str] | None:
        """This repository's most recent reply, whatever prompt it answered.

        Returned with the repository fingerprint it was written for (`""` when
        unknown), so the fallback can tell an earlier *prompt* about the same
        repository from an earlier *version* of the repository.
        """
        with self._connection() as connection:
            row = connection.execute(
                "SELECT reply_text, handle_map_json, repository_fingerprint FROM doc_overview_narratives "
                "WHERE repository_id = ?",
                (repository_id,),
            ).fetchone()
        narrative = _narrative_row(row)
        if narrative is None:
            return None
        return (*narrative, str(row["repository_fingerprint"] or ""))

    def save_overview_narrative(
        self,
        repository_id: str,
        narrative_key: str,
        reply_text: str,
        handle_map: Mapping[str, str],
        *,
        repository_fingerprint: str = "",
    ) -> None:
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO doc_overview_narratives
                        (repository_id, narrative_key, reply_text, handle_map_json, generated_at,
                         repository_fingerprint)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(repository_id) DO UPDATE SET
                        narrative_key = excluded.narrative_key,
                        reply_text = excluded.reply_text,
                        handle_map_json = excluded.handle_map_json,
                        generated_at = excluded.generated_at,
                        repository_fingerprint = excluded.repository_fingerprint
                    """,
                    (
                        repository_id,
                        narrative_key,
                        reply_text,
                        json.dumps(dict(handle_map), sort_keys=True),
                        datetime.now(timezone.utc).isoformat(),
                        repository_fingerprint,
                    ),
                )

    def list_feature_titles(self, repository_id: str) -> dict[str, str]:
        """Every feature's currently stored title, keyed by feature key.

        Read *before* this run's features are derived: the titles are overwritten
        in place, so afterwards the previous names exist nowhere - and they are
        what tells us whether every already-written page's sidebar went stale.
        """
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT feature_key, title FROM doc_features WHERE repository_id = ?",
                (repository_id,),
            ).fetchall()
            return {row["feature_key"]: row["title"] for row in rows}

    def save_feature_titles(self, repository_id: str, titles: Mapping[str, str]) -> None:
        """Replace this repository's feature titles wholesale.

        A delete-then-insert rather than an upsert: a feature that no longer
        exists must not leave its title behind, or the next run would compare
        against a name nothing carries and regenerate the whole wiki forever.
        """
        with self._connection() as connection:
            with connection:
                connection.execute(
                    "DELETE FROM doc_features WHERE repository_id = ?", (repository_id,)
                )
                connection.executemany(
                    "INSERT INTO doc_features (repository_id, feature_key, title) VALUES (?, ?, ?)",
                    [(repository_id, key, title) for key, title in sorted(titles.items())],
                )

    def drop_section_narrations(self, repository_id: str) -> None:
        """Discard the previous navigation scheme's cached names.

        Called once, by the migration that converts a `kind="section"` manifest.
        Left behind, an old section title could surface in a feature's sidebar
        entry - the two schemes keyed their cache differently, so nothing else
        would notice the collision.
        """
        with self._connection() as connection:
            with connection:
                connection.execute(
                    "DELETE FROM doc_section_narrations WHERE repository_id = ?", (repository_id,)
                )

    def load_template_fingerprint(self, repository_id: str) -> str | None:
        """The template fingerprint the pages on disk were rendered with.

        `None` means "unknown", which is deliberately *not* the same as
        "unchanged": a wiki generated before this was tracked has pages whose
        renderer cannot be identified, so the caller must treat it as stale and
        rebuild once. That single rebuild is what repairs an existing wiki.
        """
        with self._connection() as connection:
            row = connection.execute(
                "SELECT template_fingerprint FROM doc_render_state WHERE repository_id = ?",
                (repository_id,),
            ).fetchone()
            return row["template_fingerprint"] if row is not None else None

    def save_template_fingerprint(self, repository_id: str, fingerprint: str) -> None:
        """Record the fingerprint - only after a pass that rewrote every page.

        Saving it after a partial pass would claim the whole wiki had been
        rendered by these templates when only some of it had, and the pages left
        behind would never be revisited.
        """
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO doc_render_state (repository_id, template_fingerprint, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(repository_id) DO UPDATE SET
                        template_fingerprint = excluded.template_fingerprint,
                        updated_at = excluded.updated_at
                    """,
                    (repository_id, fingerprint, datetime.now(timezone.utc).isoformat()),
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