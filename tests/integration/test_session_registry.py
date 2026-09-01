from __future__ import annotations

from chat import sqlite_store as chat_sqlite_store
from chat_api.session_store import MAX_CACHED_SESSIONS, SessionRegistry

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


def test_the_in_memory_cache_is_bounded_and_evicts_the_least_recently_used(tmp_path):
    """`serve` runs for days; without a bound the cache held every session ever
    opened, each with its full message history, for the life of the process."""
    metadata_db_path = tmp_path / "repository-metadata.sqlite"
    registry = SessionRegistry(None, FakeEmbeddingEngine(), FakeLLMEngine(), metadata_db_path)

    created = [registry.create_session() for _ in range(MAX_CACHED_SESSIONS + 5)]

    assert len(registry._sessions) == MAX_CACHED_SESSIONS
    assert created[0].id not in registry._sessions


def test_an_evicted_session_is_still_served_from_the_store(tmp_path):
    """Eviction demotes a session to a re-read, it does not lose it - the same
    path a fresh process takes on a cache miss."""
    metadata_db_path = tmp_path / "repository-metadata.sqlite"
    registry = SessionRegistry(None, FakeEmbeddingEngine(), FakeLLMEngine(), metadata_db_path)
    first = registry.create_session()
    for _ in range(MAX_CACHED_SESSIONS + 5):
        registry.create_session()

    assert first.id not in registry._sessions
    assert registry.get_session(first.id).id == first.id


def test_a_recently_used_session_survives_eviction(tmp_path):
    """Least-recently-*used*, not least-recently-created: reading a session
    keeps it resident."""
    metadata_db_path = tmp_path / "repository-metadata.sqlite"
    registry = SessionRegistry(None, FakeEmbeddingEngine(), FakeLLMEngine(), metadata_db_path)
    first = registry.create_session()
    for _ in range(MAX_CACHED_SESSIONS - 1):
        registry.create_session()

    registry.get_session(first.id)
    for _ in range(5):
        registry.create_session()

    assert first.id in registry._sessions


def test_sessions_are_never_evicted_without_a_metadata_db():
    """Without a store this cache *is* the store - `get_session` raises rather
    than falling back - so evicting would destroy sessions outright."""
    registry = SessionRegistry(None, FakeEmbeddingEngine(), FakeLLMEngine())
    created = [registry.create_session() for _ in range(MAX_CACHED_SESSIONS + 5)]

    assert len(registry.list_sessions()) == len(created)
    assert registry.get_session(created[0].id).id == created[0].id
