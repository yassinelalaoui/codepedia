from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from chat import LocalDependencyUnavailableError
from chat_api.errors import register_exception_handlers
from chat_api.schemas import AskQuestionRequest
from chat_api.session_store import SessionNotFoundError


def _build_error_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/unavailable")
    def _raise_unavailable():
        raise LocalDependencyUnavailableError("Local LLM is unavailable; ChatSession cannot answer without it.")

    @app.get("/missing-session")
    def _raise_not_found():
        raise SessionNotFoundError("does-not-exist")

    @app.post("/validate")
    def _validate(request: AskQuestionRequest):
        return {"question": request.question}

    return app


def test_local_dependency_unavailable_maps_to_503():
    client = TestClient(_build_error_test_app())

    response = client.get("/unavailable")

    assert response.status_code == 503
    assert response.json()["code"] == "local_dependency_unavailable"


def test_session_not_found_maps_to_404():
    client = TestClient(_build_error_test_app())

    response = client.get("/missing-session")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "session_not_found"
    assert "does-not-exist" in body["message"]


def test_empty_question_maps_to_422():
    client = TestClient(_build_error_test_app())

    response = client.post("/validate", json={"question": "   "})

    assert response.status_code == 422
    assert response.json()["code"] == "empty_question"
