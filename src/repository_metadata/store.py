from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from parser_engine import FileSymbolInventory, SourceFile

from .fingerprints import compute_content_hash, file_has_changed
from .git_provenance import read_commit_sha
from .models import DependencyEdge, Repository, RepositoryBundle, SourceFile as StoredSourceFile, SourceFileBundle
from .models import Symbol
from .sqlite_store import (
    connect,
    delete_source_file as _delete_source_file,
    get_source_file_content_hash,
    load_repository,
    load_repository_bundle,
    load_source_file,
    load_latest_summary_for_symbol,
    load_source_file_bundle,
    load_summary_by_context_hash,
    load_symbols_for_source_file,
    repository_root_exists,
    save_summary_to_ledger,
    update_repository_commit_sha,
    update_symbol_summary_provenance,
    stable_repository_id,
    stable_source_file_id,
    upsert_repository,
    upsert_source_file_bundle,
    update_symbol_generated_summary,
)


@dataclass(slots=True)
class RepositoryMetadataStore:
    db_path: Path
    # Set only while a `session()` is open; see that method for why.
    _session_connection: sqlite3.Connection | None = field(default=None, repr=False, compare=False)
    _session_depth: int = field(default=0, repr=False, compare=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def open(self):  # pragma: no cover - simple passthrough
        return connect(self.db_path)

    def session(self) -> "_MetadataSession":
        """Hold one connection open for a whole pass, instead of one per call.

        Every method below used to open its own connection and close it again.
        That is not just one `fsync` - `connect` also replays `ensure_schema`,
        six DDL statements plus three introspection-guarded migrations, on
        every single call. The summary ledger added three of those calls per
        symbol summarized, and `restoreSummariesFromLedger` one more per symbol
        restored, inside the loop the watcher runs on every save: 300 ledger
        writes measured 4.10s that way against 0.02s sharing a connection.

        Re-entrant on purpose - the incremental pipeline calls
        `restoreSummariesFromLedger` and then `summarizeRepository`, and both
        open one - and safe to share across the summary pool's threads, because
        `_connection` hands the shared connection out under `_lock`.

        Outside a session nothing changes: `_connection` opens and closes per
        call exactly as before.
        """
        return _MetadataSession(self)

    def _connection(self) -> "_StoreConnection":
        """The session's connection when there is one, a fresh one otherwise."""
        return _StoreConnection(self)

    def ensure_repository(self, root_path: str | Path, *, detected_languages: Iterable[str] = ()) -> Repository:
        # HEAD is read here and in `refresh_commit_sha` below, and nowhere else:
        # this runs once at the start of an indexing run, while `store_inventory`
        # further down runs per file and leaves the stored value alone by passing
        # no `commit_sha` at all.
        with self._connection() as connection:
            return upsert_repository(
                connection,
                root_path=root_path,
                detected_languages=tuple(detected_languages),
                last_indexed_at=datetime.now(timezone.utc).isoformat(),
                commit_sha=read_commit_sha(root_path),
            )

    def refresh_commit_sha(self, root_path: str | Path) -> str:
        """Re-read HEAD for a process that outlives the commit it started on.

        `ensure_repository` is right to read HEAD once for an `index` run: the
        wiki describes the commit it was built from, and that commit does not
        move mid-run. `serve` is the other case - the watcher regenerates pages
        for hours across any number of commits, and every one of those pages was
        stamping the sha the process started on. A footer asserting the wrong
        commit is worse than one asserting none.

        Cheap enough to do per pass because `git_provenance` reads the files
        directly instead of spawning `git`.

        An empty read is ignored rather than stored: `read_commit_sha` degrades
        to "" for everything uninteresting - not a repository, an unborn branch,
        a directory it cannot read - and a momentarily unreadable `.git` must not
        erase a provenance that was correct a second ago.
        """
        commit_sha = read_commit_sha(root_path)
        if not commit_sha:
            return ""
        with self._connection() as connection:
            update_repository_commit_sha(
                connection, repository_id=stable_repository_id(root_path), commit_sha=commit_sha
            )
        return commit_sha

    def store_inventory(
        self,
        *,
        repository_root: str | Path,
        source_file: SourceFile,
        inventory: FileSymbolInventory,
        dependency_edges: Iterable[DependencyEdge] = (),
        content_hash: str | None = None,
        last_modified: str | None = None,
    ) -> StoredSourceFile:
        repository_id = stable_repository_id(repository_root)
        with self._connection() as connection:
            detected_languages = (source_file.language,)
            if repository_root_exists(connection, root_path=repository_root):
                existing = load_repository(connection, repository_id=repository_id)
                detected_languages = tuple(sorted(set(existing.detectedLanguages) | {source_file.language}))
            upsert_repository(
                connection,
                root_path=repository_root,
                detected_languages=detected_languages,
                last_indexed_at=datetime.now(timezone.utc).isoformat(),
            )
            current_hash = content_hash or compute_content_hash(source_file)
            existing_hash = get_source_file_content_hash(connection, repository_id=repository_id, path=source_file.path)
            if existing_hash == current_hash:
                existing_file = load_source_file(connection, source_file_id=stable_source_file_id(repository_id, source_file.path))
                return existing_file
            return upsert_source_file_bundle(
                connection,
                repository_id=repository_id,
                source_file=source_file,
                inventory=inventory,
                content_hash=current_hash,
                last_modified=last_modified or datetime.now(timezone.utc).isoformat(),
                dependency_edges=dependency_edges,
            )

    def has_file_changed(self, *, repository_root: str | Path, path: str | Path, current_hash: str) -> bool:
        repository_id = stable_repository_id(repository_root)
        with self._connection() as connection:
            stored_hash = get_source_file_content_hash(connection, repository_id=repository_id, path=path)
        return file_has_changed(stored_hash, current_hash)

    def delete_source_file(self, repository_root: str | Path, path: str | Path) -> None:
        repository_id = stable_repository_id(repository_root)
        with self._connection() as connection:
            _delete_source_file(connection, repository_id=repository_id, path=path)

    def load_repository(self, repository_root: str | Path) -> RepositoryBundle:
        repository_id = stable_repository_id(repository_root)
        with self._connection() as connection:
            return load_repository_bundle(connection, repository_id=repository_id)

    def load_source_file(self, *, repository_root: str | Path, path: str | Path) -> SourceFileBundle:
        repository_id = stable_repository_id(repository_root)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id FROM source_files WHERE repository_id = ? AND path = ?",
                (repository_id, Path(path).as_posix().replace("\\", "/")),
            ).fetchone()
            if row is None:
                raise KeyError(str(path))
            return load_source_file_bundle(connection, source_file_id=row["id"])

    def load_module(self, *, repository_root: str | Path, path: str | Path) -> SourceFileBundle:
        return self.load_source_file(repository_root=repository_root, path=path)

    def load_repository_record(self, repository_root: str | Path) -> Repository:
        repository_id = stable_repository_id(repository_root)
        with self._connection() as connection:
            return load_repository(connection, repository_id=repository_id)

    def load_source_file_symbols(self, *, repository_root: str | Path, path: str | Path) -> tuple[Symbol, ...]:
        repository_id = stable_repository_id(repository_root)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id FROM source_files WHERE repository_id = ? AND path = ?",
                (repository_id, Path(path).as_posix().replace("\\", "/")),
            ).fetchone()
            if row is None:
                raise KeyError(str(path))
            return load_symbols_for_source_file(connection, source_file_id=row["id"])

    def update_symbol_generated_summary(self, symbol_id: str, generated_summary: str) -> None:
        with self._connection() as connection:
            update_symbol_generated_summary(connection, symbol_id=symbol_id, generated_summary=generated_summary)

    def record_symbol_summary(
        self, *, symbol_id: str, generated_summary: str, context_hash: str, is_stale: bool = False
    ) -> None:
        """Store a summary along with the content hash it was generated from."""
        with self._connection() as connection:
            update_symbol_summary_provenance(
                connection,
                symbol_id=symbol_id,
                generated_summary=generated_summary,
                context_hash=context_hash,
                is_stale=is_stale,
            )

    def remember_summary(
        self,
        *,
        context_hash: str,
        source_file_id: str,
        symbol_kind: str,
        symbol_name: str,
        generated_summary: str,
        model_name: str,
        generated_at: str,
    ) -> None:
        with self._connection() as connection:
            save_summary_to_ledger(
                connection,
                context_hash=context_hash,
                source_file_id=source_file_id,
                symbol_kind=symbol_kind,
                symbol_name=symbol_name,
                generated_summary=generated_summary,
                model_name=model_name,
                generated_at=generated_at,
            )

    def recall_summary(self, *, context_hash: str) -> str:
        """A summary already generated for exactly this content, or ""."""
        with self._connection() as connection:
            return load_summary_by_context_hash(connection, context_hash=context_hash)

    def recall_previous_summary(
        self, *, source_file_id: str, symbol_kind: str, symbol_name: str
    ) -> tuple[str, str]:
        """The last summary written for this symbol, as `(summary, context_hash)`."""
        with self._connection() as connection:
            return load_latest_summary_for_symbol(
                connection,
                source_file_id=source_file_id,
                symbol_kind=symbol_kind,
                symbol_name=symbol_name,
            )

    def update_symbol_generated_summaries(self, summaries: Iterable[tuple[str, str]]) -> None:
        with self._connection() as connection:
            with connection:
                for symbol_id, generated_summary in summaries:
                    connection.execute(
                        "UPDATE symbols SET generated_summary = ? WHERE id = ?",
                        (generated_summary, symbol_id),
                    )


class _MetadataSession:
    """`RepositoryMetadataStore.session`'s context manager.

    A class rather than a `@contextmanager` generator for the reason
    `cli/index_command.py`'s `_stage` spells out: `contextlib`'s wrapper
    assigns `exc.__traceback__` when an exception passes through it, and this
    codebase's engine errors are frozen dataclasses that raise
    `FrozenInstanceError` on any attribute assignment. A summarization pass is
    exactly where `FailoverExhaustedError` comes from, so a generator here
    would replace every real provider error with a meaningless one.
    """

    __slots__ = ("_store",)

    def __init__(self, store: "RepositoryMetadataStore") -> None:
        self._store = store

    def __enter__(self) -> "RepositoryMetadataStore":
        store = self._store
        with store._lock:
            if store._session_connection is None:
                store._session_connection = connect(store.db_path, check_same_thread=False)
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


class _StoreConnection:
    """One store call's connection - shared under the lock, or opened for it.

    Inside a session the store's lock is held for the whole call: a single
    sqlite connection shared by the summary pool's threads has to be used by
    one of them at a time. `_lock` is reentrant, so a call nesting another on
    the same thread still works.

    A class, not a generator, for the same reason as `_MetadataSession`.
    """

    __slots__ = ("_store", "_shared", "_owned")

    def __init__(self, store: "RepositoryMetadataStore") -> None:
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
        self._owned = connect(store.db_path)
        return self._owned

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if self._shared is not None:
            self._shared = None
            self._store._lock.release()
        elif self._owned is not None:
            connection, self._owned = self._owned, None
            connection.close()
        return False



def open_repository_metadata_store(db_path: str | Path) -> RepositoryMetadataStore:
    return RepositoryMetadataStore(db_path=Path(db_path))
