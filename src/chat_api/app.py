from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator, Optional

from chat import ChatMessage
from chat.session import ensure_local_dependencies_available
from fastapi import FastAPI
from provider_routing import list_failover_events
from repository_metadata.sqlite_store import connect as connect_metadata_db
from starlette.responses import StreamingResponse
from starlette.staticfiles import StaticFiles

from .errors import register_exception_handlers
from .schemas import (
    AnswerFragmentEvent,
    ApiErrorResponse,
    AskQuestionRequest,
    AskQuestionResponse,
    ChatMessageView,
    CreateSessionResponse,
    FailoverLogEntryView,
    FailoverLogResponse,
    SessionHistoryResponse,
    SessionListResponse,
    SessionSummary,
)
from .session_store import SessionRegistry


def _error_code_for(exc: Exception) -> str:
    kind = getattr(exc, "kind", None)
    return kind if isinstance(kind, str) else "generation_failed"


def create_app(
    vector_index: Any,
    embedding_engine: Any,
    llm_engine: Any,
    docs_root: str | Path,
    metadata_db_path: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Local Chat API")
    app.state.session_registry = SessionRegistry(vector_index, embedding_engine, llm_engine, metadata_db_path)
    app.state.metadata_db_path = metadata_db_path
    register_exception_handlers(app)

    @app.post("/sessions", status_code=201)
    def create_session() -> CreateSessionResponse:
        session = app.state.session_registry.create_session()
        return CreateSessionResponse(sessionId=session.id)

    @app.post("/sessions/{session_id}/messages")
    async def ask_question(session_id: str, request: AskQuestionRequest) -> StreamingResponse:
        session = app.state.session_registry.get_session(session_id)
        # Checked here, before any StreamingResponse is constructed, so an
        # unavailable engine still surfaces as a normal 503 response rather
        # than a stream that opens and then immediately errors - askStream()
        # performs the same check again itself for callers that don't.
        ensure_local_dependencies_available(session.embeddingEngine, session.llmEngine)

        async def _event_stream() -> AsyncIterator[str]:
            try:
                async for item in session.askStream(request.question):
                    if isinstance(item, ChatMessage):
                        done_payload = AskQuestionResponse(
                            answer=item.content,
                            citedSymbolIds=item.citedSymbolIds,
                            citedFilePaths=item.citedFilePaths,
                            generatedBy=item.generatedBy,
                        )
                        yield f"event: done\ndata: {done_payload.model_dump_json()}\n\n"
                    else:
                        fragment_payload = AnswerFragmentEvent(fragment=item)
                        yield f"data: {fragment_payload.model_dump_json()}\n\n"
            except Exception as exc:  # noqa: BLE001 - surfaced to the client as an SSE error event
                error_payload = ApiErrorResponse(code=_error_code_for(exc), message=str(exc))
                yield f"event: error\ndata: {error_payload.model_dump_json()}\n\n"

        return StreamingResponse(_event_stream(), media_type="text/event-stream")

    @app.get("/sessions")
    def list_sessions() -> SessionListResponse:
        sessions = app.state.session_registry.list_sessions()
        return SessionListResponse(
            sessions=tuple(
                SessionSummary(
                    sessionId=session.id,
                    createdAt=session.createdAt,
                    lastActivityAt=session.lastActivityAt,
                )
                for session in sessions
            )
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
                generatedBy=message.generatedBy,
            )
            for message in session.messages
        )
        return SessionHistoryResponse(sessionId=session_id, messages=messages)

    @app.get("/providers/failover-log")
    def get_failover_log(stage: Optional[str] = None, limit: int = 100) -> FailoverLogResponse:
        db_path = app.state.metadata_db_path
        if db_path is None:
            return FailoverLogResponse(events=())
        connection = connect_metadata_db(db_path)
        try:
            events = list_failover_events(connection, stage=stage, limit=limit)
        finally:
            connection.close()
        return FailoverLogResponse(
            events=tuple(
                FailoverLogEntryView(
                    id=event.id,
                    timestamp=event.timestamp,
                    stage=event.stage,
                    attemptedProvider=event.attemptedProvider,
                    resultProvider=event.resultProvider,
                    reason=event.reason,
                )
                for event in events
            )
        )

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
