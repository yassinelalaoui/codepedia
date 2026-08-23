from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from vector_index import VectorIndex, build_code_chunk
from vector_index.search import encode_text

from chat_api import create_app


class FakeEmbeddingEngine:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available

    def isAvailableLocally(self) -> bool:
        return self.available

    def embed(self, text: str):
        return encode_text(text)


class FakeLLMEngine:
    def __init__(self, response_text: str = "Authentication is handled by authenticate_user.", *, available: bool = True) -> None:
        self.response_text = response_text
        self.available = available
        self.calls: list = []

    def isAvailableLocally(self) -> bool:
        return self.available

    def generate(self, envelope) -> str:
        self.calls.append(envelope)
        return self.response_text


def build_test_app(
    tmp_path: Path,
    *,
    embedding_engine: FakeEmbeddingEngine | None = None,
    llm_engine: FakeLLMEngine | None = None,
    docs_root: Path | None = None,
    metadata_db_path: Path | None = None,
) -> tuple[FastAPI, VectorIndex]:
    embedding_engine = embedding_engine if embedding_engine is not None else FakeEmbeddingEngine()
    llm_engine = llm_engine if llm_engine is not None else FakeLLMEngine()
    docs_root = docs_root if docs_root is not None else tmp_path / "docs"

    index = VectorIndex(
        tmp_path / "repo",
        tmp_path / "meta.sqlite",
        embedding_engine=embedding_engine,
    )
    chunk = build_code_chunk(
        "def authenticate_user(): validate credentials and start a session",
        source_symbol_id="auth.authenticate_user",
        source_file_path="src/auth/login.py",
        embedding_engine=embedding_engine,
    )
    index.addChunk(chunk)

    app = create_app(index, embedding_engine, llm_engine, docs_root, metadata_db_path)
    return app, index
