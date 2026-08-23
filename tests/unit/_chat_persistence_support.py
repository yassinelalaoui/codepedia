from __future__ import annotations

from pathlib import Path

from repository_metadata.sqlite_store import connect


def make_metadata_db(tmp_path: Path, name: str = "repository-metadata.sqlite") -> Path:
    """A fresh, schema-initialized repository-metadata.sqlite under tmp_path.

    Reuses the same connect()/ensure_schema() every other repository_metadata
    consumer goes through, so chat persistence tests exercise the real schema
    (chat_sessions/chat_messages included) rather than a hand-rolled one.
    """
    db_path = tmp_path / name
    connect(db_path).close()
    return db_path
