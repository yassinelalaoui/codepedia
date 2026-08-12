from __future__ import annotations

import urllib.request

from chat import ChatSession
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
        tmp_path / "index.sqlite",
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
