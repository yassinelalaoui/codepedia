"""The chat API is closed; the wiki it sits next to is not.

Both halves matter. The token stops another local process - or a page served
from another origin that guessed the port - from spending the LLM budget or
reading someone's conversation. The Host allowlist stops DNS rebinding, where an
attacker's domain resolves to 127.0.0.1 so their page becomes same-origin with
this server. Neither would help if requiring the token also locked the wiki
pages, so the last test pins that it does not.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from chat_api.security import TOKEN_HEADER

from ._chat_api_support import api_client, build_test_app


def _bare_client(app) -> TestClient:
    """A client with a valid Host but no token."""
    return TestClient(app, base_url="http://127.0.0.1")


def test_a_request_without_a_token_is_refused(tmp_path):
    app, index = build_test_app(tmp_path)

    response = _bare_client(app).post("/sessions")
    index.close()

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_a_request_with_the_wrong_token_is_refused(tmp_path):
    app, index = build_test_app(tmp_path)
    client = TestClient(app, base_url="http://127.0.0.1", headers={TOKEN_HEADER: "not-the-token"})

    response = client.post("/sessions")
    index.close()

    assert response.status_code == 401


def test_every_api_route_is_guarded_not_just_the_first(tmp_path):
    app, index = build_test_app(tmp_path)
    authorized = api_client(app)
    session_id = authorized.post("/sessions").json()["sessionId"]
    bare = _bare_client(app)

    statuses = [
        bare.post("/sessions").status_code,
        bare.post(f"/sessions/{session_id}/messages", json={"question": "where?"}).status_code,
        bare.get(f"/sessions/{session_id}/messages").status_code,
        bare.get("/providers/failover-log").status_code,
    ]
    index.close()

    assert statuses == [401, 401, 401, 401]


def test_the_run_token_is_accepted(tmp_path):
    app, index = build_test_app(tmp_path)

    response = api_client(app).post("/sessions")
    index.close()

    assert response.status_code == 201


def test_each_app_gets_its_own_token(tmp_path):
    first, first_index = build_test_app(tmp_path / "a")
    second, second_index = build_test_app(tmp_path / "b")
    token = first.state.authToken
    client = TestClient(second, base_url="http://127.0.0.1", headers={TOKEN_HEADER: token})

    response = client.post("/sessions")
    first_index.close()
    second_index.close()

    assert token != second.state.authToken
    assert response.status_code == 401


def test_a_foreign_host_header_is_refused_before_any_route_runs(tmp_path):
    # The DNS-rebinding case: the attacker's name resolves to 127.0.0.1, so the
    # request really does arrive here - carrying their Host.
    app, index = build_test_app(tmp_path)
    client = TestClient(
        app, base_url="http://evil.example", headers={TOKEN_HEADER: app.state.authToken}
    )

    api_response = client.post("/sessions")
    wiki_response = client.get("/")
    index.close()

    assert api_response.status_code == 400
    assert wiki_response.status_code == 400


def test_localhost_and_loopback_hosts_are_both_accepted(tmp_path):
    app, index = build_test_app(tmp_path)
    headers = {TOKEN_HEADER: app.state.authToken}

    statuses = [
        TestClient(app, base_url="http://localhost:8000", headers=headers).post("/sessions").status_code,
        TestClient(app, base_url="http://127.0.0.1:9999", headers=headers).post("/sessions").status_code,
    ]
    index.close()

    # The port is not part of the comparison, which is why no port variant is
    # listed in DEFAULT_ALLOWED_HOSTS.
    assert statuses == [201, 201]


def test_the_wiki_is_served_without_a_token(tmp_path):
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "index.html").write_text("<h1>wiki</h1>", encoding="utf-8")
    app, index = build_test_app(tmp_path, docs_root=docs_root)

    response = _bare_client(app).get("/")
    index.close()

    assert response.status_code == 200
    assert "wiki" in response.text


def test_the_failover_log_limit_is_bounded(tmp_path):
    app, index = build_test_app(tmp_path, metadata_db_path=tmp_path / "meta-store.sqlite")
    client = api_client(app)

    too_large = client.get("/providers/failover-log", params={"limit": 10_000})
    too_small = client.get("/providers/failover-log", params={"limit": 0})
    accepted = client.get("/providers/failover-log", params={"limit": 500})
    index.close()

    assert too_large.status_code == 422
    assert too_small.status_code == 422
    # An out-of-range limit is not an empty question; it used to answer as one.
    assert too_large.json()["code"] == "invalid_request"
    assert accepted.status_code == 200


def test_an_empty_question_still_answers_empty_question(tmp_path):
    app, index = build_test_app(tmp_path)
    client = api_client(app)
    session_id = client.post("/sessions").json()["sessionId"]

    response = client.post(f"/sessions/{session_id}/messages", json={"question": "   "})
    index.close()

    assert response.status_code == 422
    assert response.json()["code"] == "empty_question"
