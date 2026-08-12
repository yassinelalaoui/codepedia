from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from .errors import register_exception_handlers
from .schemas import (
    AskQuestionRequest,
    AskQuestionResponse,
    ChatMessageView,
    CreateSessionResponse,
    SessionHistoryResponse,
)
from .session_store import SessionRegistry


def create_app(vector_index: Any, embedding_engine: Any, llm_engine: Any) -> FastAPI:
    app = FastAPI(title="Local Chat API")
    app.state.session_registry = SessionRegistry(vector_index, embedding_engine, llm_engine)
    register_exception_handlers(app)

    @app.post("/sessions", status_code=201)
    def create_session() -> CreateSessionResponse:
        session = app.state.session_registry.create_session()
        return CreateSessionResponse(sessionId=session.id)

    @app.post("/sessions/{session_id}/messages")
    def ask_question(session_id: str, request: AskQuestionRequest) -> AskQuestionResponse:
        session = app.state.session_registry.get_session(session_id)
        message = session.ask(request.question)
        return AskQuestionResponse(
            answer=message.content,
            citedSymbolIds=message.citedSymbolIds,
            citedFilePaths=message.citedFilePaths,
        )

    @app.get("/sessions/{session_id}/messages")
    def get_history(session_id: str) -> SessionHistoryResponse:
        session = app.state.session_registry.get_session(session_id)
        messages = tuple(
            ChatMessageView(
                role=message.role,
                content=message.content,
                citedSymbolIds=message.citedSymbolIds,
                citedFilePaths=message.citedFilePaths,
                timestamp=message.timestamp,
            )
            for message in session.messages
        )
        return SessionHistoryResponse(sessionId=session_id, messages=messages)

    return app
