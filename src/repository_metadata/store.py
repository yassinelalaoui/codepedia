from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
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

    def open(self):  # pragma: no cover - simple passthrough
        return connect(self.db_path)

    def ensure_repository(self, root_path: str | Path, *, detected_languages: Iterable[str] = ()) -> Repository:
        # HEAD is read here and in `refresh_commit_sha` below, and nowhere else:
        # this runs once at the start of an indexing run, while `store_inventory`
        # further down runs per file and leaves the stored value alone by passing
        # no `commit_sha` at all.
        with closing(connect(self.db_path)) as connection:
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
        with closing(connect(self.db_path)) as connection:
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
        with closing(connect(self.db_path)) as connection:
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
        with closing(connect(self.db_path)) as connection:
            stored_hash = get_source_file_content_hash(connection, repository_id=repository_id, path=path)
        return file_has_changed(stored_hash, current_hash)

    def delete_source_file(self, repository_root: str | Path, path: str | Path) -> None:
        repository_id = stable_repository_id(repository_root)
        with closing(connect(self.db_path)) as connection:
            _delete_source_file(connection, repository_id=repository_id, path=path)

    def load_repository(self, repository_root: str | Path) -> RepositoryBundle:
        repository_id = stable_repository_id(repository_root)
        with closing(connect(self.db_path)) as connection:
            return load_repository_bundle(connection, repository_id=repository_id)

    def load_source_file(self, *, repository_root: str | Path, path: str | Path) -> SourceFileBundle:
        repository_id = stable_repository_id(repository_root)
        with closing(connect(self.db_path)) as connection:
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
        with closing(connect(self.db_path)) as connection:
            return load_repository(connection, repository_id=repository_id)

    def load_source_file_symbols(self, *, repository_root: str | Path, path: str | Path) -> tuple[Symbol, ...]:
        repository_id = stable_repository_id(repository_root)
        with closing(connect(self.db_path)) as connection:
            row = connection.execute(
                "SELECT id FROM source_files WHERE repository_id = ? AND path = ?",
                (repository_id, Path(path).as_posix().replace("\\", "/")),
            ).fetchone()
            if row is None:
                raise KeyError(str(path))
            return load_symbols_for_source_file(connection, source_file_id=row["id"])

    def update_symbol_generated_summary(self, symbol_id: str, generated_summary: str) -> None:
        with closing(connect(self.db_path)) as connection:
            update_symbol_generated_summary(connection, symbol_id=symbol_id, generated_summary=generated_summary)

    def record_symbol_summary(
        self, *, symbol_id: str, generated_summary: str, context_hash: str, is_stale: bool = False
    ) -> None:
        """Store a summary along with the content hash it was generated from."""
        with closing(connect(self.db_path)) as connection:
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
        with closing(connect(self.db_path)) as connection:
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
        with closing(connect(self.db_path)) as connection:
            return load_summary_by_context_hash(connection, context_hash=context_hash)

    def recall_previous_summary(
        self, *, source_file_id: str, symbol_kind: str, symbol_name: str
    ) -> tuple[str, str]:
        """The last summary written for this symbol, as `(summary, context_hash)`."""
        with closing(connect(self.db_path)) as connection:
            return load_latest_summary_for_symbol(
                connection,
                source_file_id=source_file_id,
                symbol_kind=symbol_kind,
                symbol_name=symbol_name,
            )

    def update_symbol_generated_summaries(self, summaries: Iterable[tuple[str, str]]) -> None:
        with closing(connect(self.db_path)) as connection:
            with connection:
                for symbol_id, generated_summary in summaries:
                    connection.execute(
                        "UPDATE symbols SET generated_summary = ? WHERE id = ?",
                        (generated_summary, symbol_id),
                    )


def open_repository_metadata_store(db_path: str | Path) -> RepositoryMetadataStore:
    return RepositoryMetadataStore(db_path=Path(db_path))
