"""The analyse history, derived from what is already on disk.

Nothing is stored for this. `~/.codepedia/repos/<state_id>/repository-metadata.sqlite`
already holds `repositories.root_path` and `last_indexed_at`, written on every
index by `upsert_repository` (`repository_metadata/sqlite_store.py:279-311`), so
the listing is a scan rather than a second source of truth that could disagree
with the directory (spec FR-029, research.md §6).

The filtering is the part that matters. `~/.codepedia/repos/` accumulates
`<state_id>.staging-<pid>` directories from runs that never finished - seven of
them against four real entries on the machine this was built for. The test is
positive: a real state directory's name is `sha256(...)[:16]`
(`cli/paths.py`), so it always matches `^[0-9a-f]{16}$` exactly. Matching that
admits only what the tool itself produces, which cannot be defeated by a form of
residue nobody anticipated - excluding a `.staging-` substring could be
(spec FR-030).
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cli import paths as cli_paths

STATE_DIR_PATTERN = re.compile(r"^[0-9a-f]{16}$")


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    stateId: str
    repositoryPath: str
    lastIndexedAt: Optional[str]
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "stateId": self.stateId,
            "repositoryPath": self.repositoryPath,
            "lastIndexedAt": self.lastIndexedAt,
            "available": self.available,
        }


def repos_root() -> Path:
    return cli_paths.codepedia_home() / "repos"


def state_dir_for(state_id: str) -> Path:
    return repos_root() / state_id


def list_entries() -> list[HistoryEntry]:
    """Every analysed repository, newest first (spec FR-028).

    One unreadable entry is skipped rather than failing the listing
    (spec FR-031): a half-written database from an interrupted run must not cost
    the person access to every other repository they have analysed.
    """
    root = repos_root()
    if not root.is_dir():
        return []

    entries: list[HistoryEntry] = []
    try:
        candidates = sorted(root.iterdir())
    except OSError:
        return []

    for directory in candidates:
        if not directory.is_dir() or not STATE_DIR_PATTERN.match(directory.name):
            continue
        entry = _read_entry(directory)
        if entry is not None:
            entries.append(entry)

    # `lastIndexedAt` is an ISO-8601 string, so lexical ordering is chronological
    # ordering. A row with no timestamp sorts last rather than crashing the sort.
    entries.sort(key=lambda item: (item.lastIndexedAt or ""), reverse=True)
    return entries


def _read_entry(directory: Path) -> Optional[HistoryEntry]:
    database = cli_paths.metadata_db_path(directory)
    if not database.exists():
        return None

    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    except sqlite3.Error:
        return None

    try:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT root_path, last_indexed_at FROM repositories ORDER BY last_indexed_at DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        # Covers a missing `repositories` table (a database from a version that
        # did not have one) as much as a corrupt file.
        return None
    finally:
        connection.close()

    if row is None or not row["root_path"]:
        return None

    repository_path = str(row["root_path"])
    return HistoryEntry(
        stateId=directory.name,
        repositoryPath=repository_path,
        lastIndexedAt=row["last_indexed_at"],
        # Spec FR-031b: a repository whose folder has moved or been deleted
        # stays listed and is marked, rather than vanishing. Its documentation
        # is still readable; only bringing it up to date is impossible.
        available=Path(repository_path).is_dir(),
    )


def find(state_id: str) -> Optional[HistoryEntry]:
    directory = state_dir_for(state_id)
    if not STATE_DIR_PATTERN.match(state_id) or not directory.is_dir():
        return None
    return _read_entry(directory)


def remove(state_id: str) -> bool:
    """Delete one repository's stored analysis, and nothing else.

    Spec FR-041 and constitution 2.7: this removes
    `~/.codepedia/repos/<state_id>/` - the generated wiki, the index and the
    metadata - and never touches a single file in the analysed repository. The
    pattern check is what keeps a crafted id from escaping that directory.
    """
    if not STATE_DIR_PATTERN.match(state_id):
        return False
    directory = state_dir_for(state_id)
    if not directory.is_dir():
        return False
    shutil.rmtree(directory, ignore_errors=False)
    return True
