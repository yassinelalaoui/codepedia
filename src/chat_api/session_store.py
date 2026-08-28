from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from chat import ChatSession, sqlite_store as chat_sqlite_store


class SessionNotFoundError(LookupError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"No session with id '{session_id}'.")
        self.session_id = session_id


class SessionRegistry:
    """In-memory session cache backed by `chat.sqlite_store` (025).

    `metadata_db_path` is optional: when not given, sessions behave exactly
    as before this feature - purely in-memory, gone on the next process.
    """

    def __init__(
        self,
        vector_index: Any,
        embedding_engine: Any,
        llm_engine: Any,
        metadata_db_path: str | Path | None = None,
        dependency_graph: Any = None,
    ) -> None:
        self._vector_index = vector_index
        self._embedding_engine = embedding_engine
        self._llm_engine = llm_engine
        self._metadata_db_path = metadata_db_path
        self._dependency_graph = dependency_graph
        self._sessions: dict[str, ChatSession] = {}

    def create_session(self) -> ChatSession:
        session_id = uuid.uuid4().hex
        if self._metadata_db_path is not None:
            chat_sqlite_store.create_session(self._metadata_db_path, session_id)
        session = ChatSession(
            id=session_id,
            vectorIndex=self._vector_index,
            embeddingEngine=self._embedding_engine,
            llmEngine=self._llm_engine,
            messageStore=self._metadata_db_path,
            dependencyGraph=self._dependency_graph,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> ChatSession:
        """The in-memory cache is the fast path for an active conversation
        within one running process. On a cache miss - a fresh process after
        a restart, or a browser resuming a session id this process hasn't
        seen yet - fall back to `chat.sqlite_store` before concluding the
        session doesn't exist."""
        session = self._sessions.get(session_id)
        if session is not None:
            return session
        if self._metadata_db_path is not None:
            try:
                stored = chat_sqlite_store.load_session(self._metadata_db_path, session_id)
            except KeyError:
                raise SessionNotFoundError(session_id) from None
            stored.vectorIndex = self._vector_index
            stored.embeddingEngine = self._embedding_engine
            stored.llmEngine = self._llm_engine
            stored.messageStore = self._metadata_db_path
            # Easy to forget, and invisible when forgotten: a session resumed
            # after a restart would silently lose graph reranking while still
            # answering normally.
            stored.dependencyGraph = self._dependency_graph
            stored.messages = list(chat_sqlite_store.load_messages(self._metadata_db_path, session_id))
            self._sessions[session_id] = stored
            return stored
        raise SessionNotFoundError(session_id)

    def list_sessions(self) -> tuple[ChatSession, ...]:
        """Every existing session, most-recently-active first (027).

        When a metadata db is configured, this is the authoritative source
        (`chat.sqlite_store.list_sessions`) rather than the in-memory cache
        alone, so a session created in a previous process - one this
        registry's cache has never seen - is still included. Without a
        metadata db (in-memory-only mode, e.g. a lightweight test), falls
        back to the in-memory cache, mirroring how `get_session` already
        treats that cache as authoritative in the no-persistence case.
        """
        if self._metadata_db_path is not None:
            return chat_sqlite_store.list_sessions(self._metadata_db_path)
        return tuple(
            sorted(self._sessions.values(), key=lambda session: session.lastActivityAt, reverse=True)
        )
