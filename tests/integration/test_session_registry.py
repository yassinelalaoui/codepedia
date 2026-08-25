from __future__ import annotations

from chat import sqlite_store as chat_sqlite_store
from chat_api.session_store import SessionRegistry

from ._chat_api_support import FakeEmbeddingEngine, FakeLLMEngine


def test_list_sessions_reflects_the_store_even_with_an_empty_in_memory_cache(tmp_path):
    metadata_db_path = tmp_path / "repository-metadata.sqlite"
    registry = SessionRegistry(None, FakeEmbeddingEngine(), FakeLLMEngine(), metadata_db_path)
    created = registry.create_session()

    # Simulate a fresh process: a brand-new registry against the same db,
    # with nothing yet in its in-memory cache (027 FR-002).
    restarted_registry = SessionRegistry(None, FakeEmbeddingEngine(), FakeLLMEngine(), metadata_db_path)

    sessions = restarted_registry.list_sessions()

    assert [session.id for session in sessions] == [created.id]


def test_list_sessions_orders_most_recently_active_first(tmp_path):
    metadata_db_path = tmp_path / "repository-metadata.sqlite"
    registry = SessionRegistry(None, FakeEmbeddingEngine(), FakeLLMEngine(), metadata_db_path)
    first = registry.create_session()
    second = registry.create_session()
    chat_sqlite_store.touch_session(metadata_db_path, first.id)

    sessions = registry.list_sessions()

    assert [session.id for session in sessions] == [first.id, second.id]


def test_list_sessions_falls_back_to_the_in_memory_cache_without_a_metadata_db():
    registry = SessionRegistry(None, FakeEmbeddingEngine(), FakeLLMEngine())
    created = registry.create_session()

    sessions = registry.list_sessions()

    assert [session.id for session in sessions] == [created.id]


def test_list_sessions_is_empty_for_a_brand_new_in_memory_registry():
    registry = SessionRegistry(None, FakeEmbeddingEngine(), FakeLLMEngine())

    assert registry.list_sessions() == ()
