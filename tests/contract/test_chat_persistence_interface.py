from __future__ import annotations

from pathlib import Path

from repository_metadata.sqlite_store import connect


def test_chat_sqlite_store_public_api_is_available():
    from chat import sqlite_store as chat_sqlite_store

    assert callable(chat_sqlite_store.create_session)
    assert callable(chat_sqlite_store.touch_session)
    assert callable(chat_sqlite_store.append_message)
    assert callable(chat_sqlite_store.load_session)
    assert callable(chat_sqlite_store.load_messages)


def test_schema_creates_chat_tables(tmp_path: Path):
    connection = connect(tmp_path / "repo.sqlite")
    try:
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "chat_sessions" in tables
        assert "chat_messages" in tables
    finally:
        connection.close()


def test_chat_messages_indexed_by_session_and_timestamp(tmp_path: Path):
    connection = connect(tmp_path / "repo.sqlite")
    try:
        indexes = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "idx_chat_messages_session_timestamp" in indexes
    finally:
        connection.close()
