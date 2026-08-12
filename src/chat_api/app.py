from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

from .errors import register_exception_handlers
from .schemas import (
    AskQuestionRequest,
    AskQuestionResponse,
    ChatMessageView,
    CreateSessionResponse,
    SessionHistoryResponse,
)
from .session_store import SessionRegistry


def create_app(vector_index: Any, embedding_engine: Any, llm_engine: Any, docs_root: str | Path) -> FastAPI:
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

    docs_root = Path(docs_root)
    if not (docs_root / "index.html").exists():
        print(
            f"No documentation wiki found at {docs_root}; run the documentation generator first."
        )
    # StaticFiles re-checks that `directory` exists on every request (not just at
    # construction, even with check_dir=False), raising a hard 500 rather than a
    # clean 404 if it is missing. Create it eagerly so a not-yet-generated wiki
    # degrades to ordinary 404s instead, mirroring DocumentationWriter's own
    # mkdir(parents=True, exist_ok=True) pattern (012).
    docs_root.mkdir(parents=True, exist_ok=True)
    app.mount("/", StaticFiles(directory=docs_root, html=True, check_dir=False), name="wiki")

    return app
