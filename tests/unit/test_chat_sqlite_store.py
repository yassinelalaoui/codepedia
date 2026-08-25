from __future__ import annotations

import pytest
from chat import sqlite_store as chat_sqlite_store
from chat.models import ChatMessage

from ._chat_persistence_support import make_metadata_db


def test_same_timestamp_messages_keep_insertion_order(tmp_path):
    db_path = make_metadata_db(tmp_path)
    session_id = "session-1"
    chat_sqlite_store.create_session(db_path, session_id)

    shared_timestamp = "2026-08-19T00:00:00+00:00"
    first = ChatMessage(role="user", content="first", timestamp=shared_timestamp)
    second = ChatMessage(role="assistant", content="second", timestamp=shared_timestamp)
    chat_sqlite_store.append_message(db_path, session_id, first)
    chat_sqlite_store.append_message(db_path, session_id, second)

    messages = chat_sqlite_store.load_messages(db_path, session_id)

    assert [message.content for message in messages] == ["first", "second"]


def test_empty_citation_lists_round_trip_as_empty_not_missing(tmp_path):
    db_path = make_metadata_db(tmp_path)
    session_id = "session-1"
    chat_sqlite_store.create_session(db_path, session_id)

    chat_sqlite_store.append_message(db_path, session_id, ChatMessage(role="user", content="no citations here"))

    (loaded,) = chat_sqlite_store.load_messages(db_path, session_id)

    assert loaded.citedSymbolIds == ()
    assert loaded.citedFilePaths == ()


def test_load_messages_on_empty_session_returns_empty_tuple_not_error(tmp_path):
    db_path = make_metadata_db(tmp_path)
    session_id = "session-1"
    chat_sqlite_store.create_session(db_path, session_id)

    assert chat_sqlite_store.load_messages(db_path, session_id) == ()


def test_append_message_to_unknown_session_raises(tmp_path):
    db_path = make_metadata_db(tmp_path)

    with pytest.raises(KeyError):
        chat_sqlite_store.append_message(db_path, "never-created", ChatMessage(role="user", content="hi"))


def test_create_session_rejects_colliding_id(tmp_path):
    db_path = make_metadata_db(tmp_path)
    chat_sqlite_store.create_session(db_path, "session-1")

    with pytest.raises(Exception):
        chat_sqlite_store.create_session(db_path, "session-1")


def test_list_sessions_orders_by_last_activity_descending(tmp_path):
    db_path = make_metadata_db(tmp_path)
    chat_sqlite_store.create_session(db_path, "session-a")
    chat_sqlite_store.create_session(db_path, "session-b")
    # "session-a" was created first but touched last, so it must sort first.
    chat_sqlite_store.touch_session(db_path, "session-a")

    sessions = chat_sqlite_store.list_sessions(db_path)

    assert [session.id for session in sessions] == ["session-a", "session-b"]


def test_list_sessions_includes_a_session_with_no_messages_yet(tmp_path):
    db_path = make_metadata_db(tmp_path)
    chat_sqlite_store.create_session(db_path, "session-1")

    sessions = chat_sqlite_store.list_sessions(db_path)

    assert [session.id for session in sessions] == ["session-1"]
    assert sessions[0].messages == []


def test_list_sessions_on_empty_database_returns_empty_tuple(tmp_path):
    db_path = make_metadata_db(tmp_path)

    assert chat_sqlite_store.list_sessions(db_path) == ()
