from __future__ import annotations

import urllib.request

from ._chat_api_support import (
    FakeEmbeddingEngine,
    FakeLLMEngine,
    api_client,
    build_test_app,
    parse_sse_events,
)


def _blocked_urlopen(*args, **kwargs):
    raise AssertionError("no outbound network request should be made during a successful answer path")


def test_create_session_returns_unique_id_with_empty_history(tmp_path):
    app, index = build_test_app(tmp_path)
    client = api_client(app)

    response_one = client.post("/sessions")
    response_two = client.post("/sessions")
    index.close()

    assert response_one.status_code == 201
    assert response_two.status_code == 201
    session_id_one = response_one.json()["sessionId"]
    session_id_two = response_two.json()["sessionId"]
    assert session_id_one
    assert session_id_two
    assert session_id_one != session_id_two


def test_ask_question_streams_fragments_then_a_structured_cited_done_event(tmp_path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _blocked_urlopen)

    app, index = build_test_app(tmp_path)
    client = api_client(app)

    session_id = client.post("/sessions").json()["sessionId"]
    response = client.post(
        f"/sessions/{session_id}/messages",
        json={"question": "where is authentication handled and how is a user validated?"},
    )
    index.close()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse_events(response.text)

    assert events, "expected at least one SSE event"
    *fragment_events, (final_name, final_payload) = events
    assert fragment_events, "expected at least one fragment event before done"
    assert all(name == "message" and "fragment" in payload for name, payload in fragment_events)
    assert final_name == "done"
    fragments_text = "".join(payload["fragment"] for _name, payload in fragment_events)
    assert fragments_text in final_payload["answer"]
    assert "Authentication is handled by authenticate_user." in final_payload["answer"]
    assert "auth.authenticate_user" in final_payload["citedSymbolIds"]
    assert "src/auth/login.py" in final_payload["citedFilePaths"]


def test_ask_question_mid_stream_failure_ends_with_error_event_and_no_history_side_effect(tmp_path):
    embedding_engine = FakeEmbeddingEngine()
    llm_engine = FakeLLMEngine(fail_after_fragments=1)
    app, index = build_test_app(tmp_path, embedding_engine=embedding_engine, llm_engine=llm_engine)
    client = api_client(app)

    session_id = client.post("/sessions").json()["sessionId"]
    response = client.post(f"/sessions/{session_id}/messages", json={"question": "where is auth handled?"})

    registry = app.state.session_registry
    session = registry.get_session(session_id)
    index.close()

    assert response.status_code == 200  # headers were already sent by the time generation failed
    events = parse_sse_events(response.text)
    assert events, "expected at least one SSE event before the failure"
    event_names = [name for name, _payload in events]
    assert event_names[-1] == "error"
    error_payload = events[-1][1]
    assert error_payload["code"]
    assert error_payload["message"]
    # The user's question is persisted immediately, but no assistant message
    # is ever recorded for a generation that failed partway through (FR-011).
    assert [message.role for message in session.messages] == ["user"]


def test_ask_question_on_unknown_session_returns_404_without_side_effects(tmp_path):
    app, index = build_test_app(tmp_path)
    client = api_client(app)

    response = client.post("/sessions/does-not-exist/messages", json={"question": "where is auth handled?"})
    index.close()

    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"


def test_ask_empty_question_returns_422_without_side_effects(tmp_path):
    app, index = build_test_app(tmp_path)
    client = api_client(app)

    session_id = client.post("/sessions").json()["sessionId"]
    response = client.post(f"/sessions/{session_id}/messages", json={"question": "   "})

    registry = app.state.session_registry
    session = registry.get_session(session_id)
    index.close()

    assert response.status_code == 422
    assert response.json()["code"] == "empty_question"
    assert session.messages == []


def test_ask_question_with_unavailable_local_model_returns_503_without_side_effects(tmp_path):
    embedding_engine = FakeEmbeddingEngine()
    llm_engine = FakeLLMEngine(available=False)
    app, index = build_test_app(tmp_path, embedding_engine=embedding_engine, llm_engine=llm_engine)
    client = api_client(app)

    session_id = client.post("/sessions").json()["sessionId"]
    response = client.post(f"/sessions/{session_id}/messages", json={"question": "where is auth handled?"})

    registry = app.state.session_registry
    session = registry.get_session(session_id)
    index.close()

    assert response.status_code == 503
    assert response.json()["code"] == "local_dependency_unavailable"
    assert session.messages == []
    assert not llm_engine.calls


def test_history_is_empty_for_unused_session_and_404_for_unknown_session(tmp_path):
    app, index = build_test_app(tmp_path)
    client = api_client(app)

    session_id = client.post("/sessions").json()["sessionId"]
    empty_history_response = client.get(f"/sessions/{session_id}/messages")
    unknown_response = client.get("/sessions/does-not-exist/messages")
    index.close()

    assert empty_history_response.status_code == 200
    assert empty_history_response.json() == {"sessionId": session_id, "messages": []}
    assert unknown_response.status_code == 404
    assert unknown_response.json()["code"] == "session_not_found"


def test_history_reflects_asked_questions_in_order_with_matching_citations(tmp_path):
    app, index = build_test_app(tmp_path)
    client = api_client(app)

    session_id = client.post("/sessions").json()["sessionId"]
    ask_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"question": "where is authentication handled?"},
    )
    history_response = client.get(f"/sessions/{session_id}/messages")
    index.close()

    ask_events = parse_sse_events(ask_response.text)
    _final_name, ask_body = ask_events[-1]
    history_body = history_response.json()

    assert history_response.status_code == 200
    assert history_body["sessionId"] == session_id
    messages = history_body["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "where is authentication handled?"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == ask_body["answer"]
    assert messages[1]["citedSymbolIds"] == ask_body["citedSymbolIds"]
    assert messages[1]["citedFilePaths"] == ask_body["citedFilePaths"]


def test_session_history_survives_a_simulated_restart_via_http(tmp_path):
    metadata_db_path = tmp_path / "repository-metadata.sqlite"
    app, index = build_test_app(tmp_path, metadata_db_path=metadata_db_path)
    client = api_client(app)

    session_id = client.post("/sessions").json()["sessionId"]
    ask_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"question": "where is authentication handled?"},
    )
    before = client.get(f"/sessions/{session_id}/messages").json()
    index.close()

    # Simulate a full server restart: build a brand-new app/SessionRegistry
    # pointed at the same metadata db path - nothing in-memory carries over.
    restarted_app, restarted_index = build_test_app(tmp_path, metadata_db_path=metadata_db_path)
    restarted_client = api_client(restarted_app)
    after = restarted_client.get(f"/sessions/{session_id}/messages").json()
    restarted_index.close()

    assert ask_response.status_code == 200
    assert after == before
    assert len(after["messages"]) == 2


def test_the_api_does_not_expose_a_session_listing(tmp_path):
    # `SessionRegistry.list_sessions()` still exists and is still tested
    # (tests/integration/test_session_registry.py); what is gone is the route
    # that handed every conversation on this machine to any caller.
    app, index = build_test_app(tmp_path)
    client = api_client(app)

    response = client.get("/sessions")
    index.close()

    # No route matches, so the request falls through to the wiki mount and gets
    # an ordinary 404 - the same answer as any other path that is not a page.
    assert response.status_code == 404


def test_unknown_session_returns_404_after_restart(tmp_path):
    metadata_db_path = tmp_path / "repository-metadata.sqlite"
    app, index = build_test_app(tmp_path, metadata_db_path=metadata_db_path)
    index.close()

    restarted_app, restarted_index = build_test_app(tmp_path, metadata_db_path=metadata_db_path)
    client = api_client(restarted_app)
    response = client.get("/sessions/never-created/messages")
    restarted_index.close()

    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"


def test_ask_question_response_and_history_carry_generated_by(tmp_path):
    metadata_db_path = tmp_path / "repository-metadata.sqlite"
    app, index = build_test_app(tmp_path, metadata_db_path=metadata_db_path)
    client = api_client(app)

    session_id = client.post("/sessions").json()["sessionId"]
    response = client.post(f"/sessions/{session_id}/messages", json={"question": "where is auth handled?"})
    index.close()

    events = parse_sse_events(response.text)
    _final_name, final_payload = events[-1]
    assert final_payload["generatedBy"] == "local:fake"

    history = client.get(f"/sessions/{session_id}/messages").json()
    assistant_message = next(message for message in history["messages"] if message["role"] == "assistant")
    assert assistant_message["generatedBy"] == "local:fake"
    user_message = next(message for message in history["messages"] if message["role"] == "user")
    assert user_message["generatedBy"] == ""


def test_failover_log_endpoint_returns_empty_list_with_no_events(tmp_path):
    metadata_db_path = tmp_path / "repository-metadata.sqlite"
    app, index = build_test_app(tmp_path, metadata_db_path=metadata_db_path)
    client = api_client(app)

    response = client.get("/providers/failover-log")
    index.close()

    assert response.status_code == 200
    assert response.json() == {"events": []}


def test_failover_log_endpoint_returns_appended_events_filtered_by_stage(tmp_path):
    from provider_routing import append_failover_event
    from repository_metadata.sqlite_store import connect

    metadata_db_path = tmp_path / "repository-metadata.sqlite"
    app, index = build_test_app(tmp_path, metadata_db_path=metadata_db_path)
    client = api_client(app)

    connection = connect(metadata_db_path)
    append_failover_event(connection, stage="chat", attempted_provider="groq:m1", result_provider="local:m2", reason="network_error")
    append_failover_event(connection, stage="embeddings", attempted_provider="openai:m1", result_provider="local:m2", reason="rate_limited")
    connection.close()

    all_events = client.get("/providers/failover-log").json()["events"]
    chat_events = client.get("/providers/failover-log", params={"stage": "chat"}).json()["events"]
    index.close()

    assert len(all_events) == 2
    assert len(chat_events) == 1
    assert chat_events[0]["stage"] == "chat"
    assert chat_events[0]["attemptedProvider"] == "groq:m1"
    assert chat_events[0]["resultProvider"] == "local:m2"
    assert chat_events[0]["reason"] == "network_error"
