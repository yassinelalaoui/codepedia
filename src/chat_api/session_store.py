from __future__ import annotations

import uuid
from typing import Any

from chat import ChatSession


class SessionNotFoundError(LookupError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"No session with id '{session_id}'.")
        self.session_id = session_id


class SessionRegistry:
    def __init__(self, vector_index: Any, embedding_engine: Any, llm_engine: Any) -> None:
        self._vector_index = vector_index
        self._embedding_engine = embedding_engine
        self._llm_engine = llm_engine
        self._sessions: dict[str, ChatSession] = {}

    def create_session(self) -> ChatSession:
        session_id = uuid.uuid4().hex
        session = ChatSession(
            id=session_id,
            vectorIndex=self._vector_index,
            embeddingEngine=self._embedding_engine,
            llmEngine=self._llm_engine,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> ChatSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session
