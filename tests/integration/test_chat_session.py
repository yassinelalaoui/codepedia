from __future__ import annotations

import time
import urllib.request

import pytest
from chat import ChatMessage, ChatSession, sqlite_store as chat_sqlite_store
from repository_metadata.sqlite_store import connect
from vector_index import VectorIndex, build_code_chunk
from vector_index.search import encode_text


class FakeEmbeddingEngine:
    def isAvailableLocally(self) -> bool:
        return True

    def embed(self, text: str):
        return encode_text(text)


class FakeLLMEngine:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list = []

    def isAvailableLocally(self) -> bool:
        return True

    def generate(self, envelope) -> str:
        self.calls.append(envelope)
        return self.response_text


def _blocked_urlopen(*args, **kwargs):
    raise AssertionError("no outbound network request should be made during a successful answer path")


def _build_index(tmp_path, engine: FakeEmbeddingEngine) -> VectorIndex:
    index = VectorIndex(
        tmp_path / "repo",
        tmp_path / "meta.sqlite",
        embedding_engine=engine,
    )
    chunk = build_code_chunk(
        "def authenticate_user(): validate credentials and start a session",
        source_symbol_id="auth.authenticate_user",
        source_file_path="src/auth/login.py",
        embedding_engine=engine,
    )
    index.addChunk(chunk)
    return index


def test_ask_returns_cited_answer_without_any_outbound_network_request(tmp_path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _blocked_urlopen)

    engine = FakeEmbeddingEngine()
    index = _build_index(tmp_path, engine)
    llm = FakeLLMEngine("Authentication is handled by authenticate_user.")

    session = ChatSession(id="session-1", vectorIndex=index, embeddingEngine=engine, llmEngine=llm)

    message = session.ask("where is authentication handled and how is a user validated?")

    index.close()

    assert message.role == "assistant"
    assert "src/auth/login.py" in message.citedFilePaths
    assert "auth.authenticate_user" in message.citedSymbolIds
    assert len(session.messages) == 2
    assert session.messages[0].role == "user"
    assert session.messages[1] is message
    assert llm.calls, "the local LLM should have been invoked to generate the answer"


def test_session_history_survives_a_simulated_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _blocked_urlopen)

    engine = FakeEmbeddingEngine()
    index = _build_index(tmp_path, engine)
    llm = FakeLLMEngine("Authentication is handled by authenticate_user.")
    db_path = tmp_path / "repository-metadata.sqlite"
    connect(db_path).close()

    session_id = "session-restart"
    chat_sqlite_store.create_session(db_path, session_id)
    session = ChatSession(id=session_id, vectorIndex=index, embeddingEngine=engine, llmEngine=llm, messageStore=db_path)
    session.ask("where is authentication handled and how is a user validated?")
    index.close()

    before = chat_sqlite_store.load_messages(db_path, session_id)
    assert len(before) == 2

    # chat.sqlite_store opens a brand-new connection on every call, so a second,
    # independent load is equivalent to a fresh process reading the file back
    # after a full server restart - nothing is cached in-process to carry over.
    after = chat_sqlite_store.load_messages(db_path, session_id)

    assert after == before
    assert [message.role for message in after] == ["user", "assistant"]
    assert after[1].citedFilePaths == ("src/auth/login.py",)
    assert after[1].citedSymbolIds == ("auth.authenticate_user",)


def test_unknown_session_id_raises_not_found_after_restart(tmp_path):
    db_path = tmp_path / "repository-metadata.sqlite"
    connect(db_path).close()

    with pytest.raises(KeyError):
        chat_sqlite_store.load_session(db_path, "never-created")


def test_appending_a_message_leaves_prior_messages_unchanged(tmp_path):
    db_path = tmp_path / "repository-metadata.sqlite"
    connect(db_path).close()
    session_id = "session-append"
    chat_sqlite_store.create_session(db_path, session_id)

    for index in range(5):
        chat_sqlite_store.append_message(db_path, session_id, ChatMessage(role="user", content=f"question {index}"))
        before_next_append = chat_sqlite_store.load_messages(db_path, session_id)
        assert [message.content for message in before_next_append] == [f"question {i}" for i in range(index + 1)]

    final = chat_sqlite_store.load_messages(db_path, session_id)
    assert len(final) == 5


def test_append_time_does_not_grow_with_session_length(tmp_path):
    db_path = tmp_path / "repository-metadata.sqlite"
    connect(db_path).close()
    session_id = "session-scale"
    chat_sqlite_store.create_session(db_path, session_id)

    def _append(index: int) -> float:
        start = time.perf_counter()
        chat_sqlite_store.append_message(db_path, session_id, ChatMessage(role="user", content=f"message {index}"))
        return time.perf_counter() - start

    early_times = [_append(index) for index in range(5)]
    for index in range(5, 495):
        _append(index)
    late_times = [_append(index) for index in range(495, 500)]

    assert len(chat_sqlite_store.load_messages(db_path, session_id)) == 500
    early_median = sorted(early_times)[len(early_times) // 2]
    late_median = sorted(late_times)[len(late_times) // 2]
    # A generous bound - the point is "doesn't scale with session length",
    # not a tight timing assertion that would make this test flaky.
    assert late_median < early_median * 5 + 0.05
