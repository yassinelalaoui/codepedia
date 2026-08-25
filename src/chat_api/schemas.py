from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator


class CreateSessionResponse(BaseModel):
    sessionId: str


class AskQuestionRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def _reject_empty_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be empty")
        return value


class AskQuestionResponse(BaseModel):
    answer: str
    citedSymbolIds: tuple[str, ...]
    citedFilePaths: tuple[str, ...]
    generatedBy: str = ""


class AnswerFragmentEvent(BaseModel):
    """One SSE `fragment` event body (026) - `AskQuestionResponse` itself is
    reused, unchanged, as the terminal `done` event's payload; `ApiErrorResponse`
    is reused as the terminal `error` event's payload. This is the only
    genuinely new shape streaming introduces."""

    fragment: str


class ChatMessageView(BaseModel):
    role: str
    content: str
    citedSymbolIds: tuple[str, ...]
    citedFilePaths: tuple[str, ...]
    timestamp: str
    generatedBy: str = ""


class SessionHistoryResponse(BaseModel):
    sessionId: str
    messages: tuple[ChatMessageView, ...]


class SessionSummary(BaseModel):
    """One entry in `GET /sessions` (027) - deliberately excludes messages;
    a summary for picking a session to resume, not that session's history."""

    sessionId: str
    createdAt: str
    lastActivityAt: str


class SessionListResponse(BaseModel):
    sessions: tuple[SessionSummary, ...]


class ApiErrorResponse(BaseModel):
    code: str
    message: str


class FailoverLogEntryView(BaseModel):
    id: str
    timestamp: str
    stage: str
    attemptedProvider: str
    resultProvider: Optional[str]
    reason: str


class FailoverLogResponse(BaseModel):
    events: tuple[FailoverLogEntryView, ...]
