from __future__ import annotations

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


class ChatMessageView(BaseModel):
    role: str
    content: str
    citedSymbolIds: tuple[str, ...]
    citedFilePaths: tuple[str, ...]
    timestamp: str


class SessionHistoryResponse(BaseModel):
    sessionId: str
    messages: tuple[ChatMessageView, ...]


class ApiErrorResponse(BaseModel):
    code: str
    message: str
