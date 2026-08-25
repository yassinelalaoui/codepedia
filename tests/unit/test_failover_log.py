from __future__ import annotations

from repository_metadata.sqlite_store import connect
from provider_routing import append_failover_event, list_failover_events


def test_append_and_list_orders_most_recent_first(tmp_path) -> None:
    connection = connect(tmp_path / "repo.sqlite")

    append_failover_event(connection, stage="chat", attempted_provider="groq:m1", result_provider="local:m2", reason="network_error")
    append_failover_event(connection, stage="chat", attempted_provider="local:m2", result_provider="local:m3", reason="rate_limited")

    events = list_failover_events(connection, stage="chat")

    assert [event.attemptedProvider for event in events] == ["local:m2", "groq:m1"]
    assert events[0].reason == "rate_limited"


def test_exhausted_event_has_null_result_provider(tmp_path) -> None:
    connection = connect(tmp_path / "repo.sqlite")

    append_failover_event(connection, stage="summary", attempted_provider="groq:m1", result_provider=None, reason="auth_failed")

    events = list_failover_events(connection)

    assert len(events) == 1
    assert events[0].resultProvider is None


def test_stage_filtering(tmp_path) -> None:
    connection = connect(tmp_path / "repo.sqlite")

    append_failover_event(connection, stage="chat", attempted_provider="groq:m1", result_provider="local:m2", reason="network_error")
    append_failover_event(connection, stage="embeddings", attempted_provider="openai:m1", result_provider="local:m2", reason="rate_limited")

    chat_events = list_failover_events(connection, stage="chat")
    embeddings_events = list_failover_events(connection, stage="embeddings")

    assert [event.stage for event in chat_events] == ["chat"]
    assert [event.stage for event in embeddings_events] == ["embeddings"]


def test_limit_caps_the_number_of_returned_events(tmp_path) -> None:
    connection = connect(tmp_path / "repo.sqlite")
    for index in range(5):
        append_failover_event(connection, stage="chat", attempted_provider=f"groq:m{index}", result_provider="local:m", reason="network_error")

    events = list_failover_events(connection, limit=2)

    assert len(events) == 2
