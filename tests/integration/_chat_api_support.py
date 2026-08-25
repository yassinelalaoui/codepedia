from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from provider_routing import FailoverExecutor, ProviderRef
from vector_index import VectorIndex, build_code_chunk
from vector_index.search import encode_text

from chat_api import create_app


def parse_sse_events(text: str) -> list[tuple[str, dict]]:
    """Parse an SSE response body (026) into a list of (event name, JSON
    payload) tuples, in order. Defaults an event's name to "message" per
    the SSE spec when no explicit `event:` line is present (the `fragment`
    events)."""
    events: list[tuple[str, dict]] = []
    for block in text.strip("\n").split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data_line = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_line = line[len("data:") :].strip()
        if data_line is not None:
            events.append((event_name, json.loads(data_line)))
    return events


class FakeEmbeddingEngine:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available

    def isAvailableLocally(self) -> bool:
        return self.available

    def isAvailable(self) -> bool:
        return self.available

    def embed(self, text: str):
        return encode_text(text)


class FakeLLMEngine:
    def __init__(
        self,
        response_text: str = "Authentication is handled by authenticate_user.",
        *,
        available: bool = True,
        fail_after_fragments: int | None = None,
    ) -> None:
        self.response_text = response_text
        self.available = available
        self.fail_after_fragments = fail_after_fragments
        self.calls: list = []

    def isAvailableLocally(self) -> bool:
        return self.available

    def isAvailable(self) -> bool:
        return self.available

    def generate(self, envelope) -> str:
        self.calls.append(envelope)
        return self.response_text

    async def generateStream(self, envelope):
        self.calls.append(envelope)
        midpoint = max(1, len(self.response_text) // 2)
        for index, fragment in enumerate((self.response_text[:midpoint], self.response_text[midpoint:])):
            if self.fail_after_fragments is not None and index >= self.fail_after_fragments:
                raise RuntimeError("simulated mid-stream generation failure")
            yield fragment


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

    chat_executor = FailoverExecutor("chat", ((ProviderRef("local", "fake"), llm_engine),))
    app = create_app(index, embedding_engine, chat_executor, docs_root, metadata_db_path)
    return app, index
