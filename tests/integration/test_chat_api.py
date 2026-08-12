from __future__ import annotations

import urllib.request

from fastapi.testclient import TestClient

from ._chat_api_support import FakeEmbeddingEngine, FakeLLMEngine, build_test_app


def _blocked_urlopen(*args, **kwargs):
    raise AssertionError("no outbound network request should be made during a successful answer path")


def test_create_session_returns_unique_id_with_empty_history(tmp_path):
    app, index = build_test_app(tmp_path)
    client = TestClient(app)

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


def test_ask_question_returns_structured_cited_answer_without_outbound_network_request(tmp_path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _blocked_urlopen)

    app, index = build_test_app(tmp_path)
    client = TestClient(app)

    session_id = client.post("/sessions").json()["sessionId"]
    response = client.post(
        f"/sessions/{session_id}/messages",
        json={"question": "where is authentication handled and how is a user validated?"},
    )
    index.close()

    assert response.status_code == 200
    body = response.json()
    assert "Authentication is handled by authenticate_user." in body["answer"]
    assert "auth.authenticate_user" in body["citedSymbolIds"]
    assert "src/auth/login.py" in body["citedFilePaths"]


def test_ask_question_on_unknown_session_returns_404_without_side_effects(tmp_path):
    app, index = build_test_app(tmp_path)
    client = TestClient(app)

    response = client.post("/sessions/does-not-exist/messages", json={"question": "where is auth handled?"})
    index.close()

    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"


def test_ask_empty_question_returns_422_without_side_effects(tmp_path):
    app, index = build_test_app(tmp_path)
    client = TestClient(app)

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
    client = TestClient(app)

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
    client = TestClient(app)

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
    client = TestClient(app)

    session_id = client.post("/sessions").json()["sessionId"]
    ask_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"question": "where is authentication handled?"},
    )
    history_response = client.get(f"/sessions/{session_id}/messages")
    index.close()

    ask_body = ask_response.json()
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
