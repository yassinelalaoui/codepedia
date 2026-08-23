from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
from chat.models import ChatMessage
from chat.retrieval import (
    build_enriched_query,
    detect_ambiguous_evidence,
    is_insufficient_evidence,
    retrieve_evidence,
)


@dataclass(frozen=True)
class _SearchResult:
    chunkId: str
    content: str
    score: float
    sourceSymbolId: str
    sourceFilePath: str
    chunkType: str = "code"


class FakeVectorIndex:
    def __init__(self, results: tuple[_SearchResult, ...] = ()) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, k: int):
        self.calls.append((query, k))
        return self.results


def _exchange(question: str, *, symbol_ids=(), file_paths=()) -> tuple[ChatMessage, ChatMessage]:
    return (
        ChatMessage(role="user", content=question),
        ChatMessage(role="assistant", content="answer", citedSymbolIds=symbol_ids, citedFilePaths=file_paths),
    )


def test_empty_history_leaves_the_query_unchanged():
    assert build_enriched_query("where is auth handled?", ()) == "where is auth handled?"

    index = FakeVectorIndex()
    retrieve_evidence(index, "where is auth handled?", history=())

    assert index.calls == [("where is auth handled?", 5)]


def test_non_empty_history_includes_recent_questions_and_citations():
    history = (
        *_exchange("where is authentication handled?", symbol_ids=("auth.authenticate_user",), file_paths=("src/auth/login.py",)),
    )

    enriched = build_enriched_query("what about the fallback path?", history)

    assert "where is authentication handled?" in enriched
    assert "auth.authenticate_user" in enriched
    assert "src/auth/login.py" in enriched
    assert enriched.endswith("what about the fallback path?")


def test_context_window_bounds_how_much_history_is_included():
    history: tuple[ChatMessage, ...] = ()
    for index in range(5):
        history += _exchange(f"question {index}", symbol_ids=(f"symbol_{index}",))

    enriched = build_enriched_query("follow-up", history, context_window=2)

    assert "question 3" in enriched
    assert "question 4" in enriched
    assert "question 0" not in enriched
    assert "question 1" not in enriched
    assert "question 2" not in enriched
    assert "symbol_3" in enriched
    assert "symbol_4" in enriched
    assert "symbol_0" not in enriched


def test_self_contained_new_question_still_carries_its_own_exact_text():
    history = _exchange("where is authentication handled?", symbol_ids=("auth.authenticate_user",))

    enriched = build_enriched_query("how does the dependency graph get built?", history)

    assert "how does the dependency graph get built?" in enriched
    assert enriched.endswith("how does the dependency graph get built?")


def test_insufficiency_and_ambiguity_detection_still_work_against_enriched_results():
    history = _exchange("where is authentication handled?", symbol_ids=("auth.authenticate_user",))
    low_score_result = _SearchResult(
        chunkId="c1", content="unrelated", score=0.05, sourceSymbolId="x.y", sourceFilePath="x.py"
    )
    index = FakeVectorIndex(results=(low_score_result,))

    evidence = retrieve_evidence(index, "what about the other one?", history=history)

    assert index.calls[0][0] != "what about the other one?"  # the query was enriched
    assert is_insufficient_evidence(evidence) is True

    close_results = (
        _SearchResult(chunkId="c1", content="a", score=0.9, sourceSymbolId="a.b", sourceFilePath="a.py"),
        _SearchResult(chunkId="c2", content="b", score=0.88, sourceSymbolId="c.d", sourceFilePath="c.py"),
    )
    index_ambiguous = FakeVectorIndex(results=close_results)
    ambiguous_evidence = retrieve_evidence(index_ambiguous, "what about the other one?", history=history)

    assert is_insufficient_evidence(ambiguous_evidence) is False
    assert detect_ambiguous_evidence(ambiguous_evidence) is True


def test_enrichment_never_makes_a_network_call(monkeypatch):
    def _blocked_stream(self, method, url, **kwargs):
        raise AssertionError(f"unexpected network call to {url}")

    monkeypatch.setattr(httpx.AsyncClient, "stream", _blocked_stream)

    def _blocked_send(self, request, **kwargs):
        raise AssertionError(f"unexpected network call to {request.url}")

    monkeypatch.setattr(httpx.Client, "send", _blocked_send)

    history = _exchange("where is authentication handled?", symbol_ids=("auth.authenticate_user",))
    index = FakeVectorIndex(results=())

    retrieve_evidence(index, "what about the other one?", history=history)
    build_enriched_query("what about the other one?", history)
