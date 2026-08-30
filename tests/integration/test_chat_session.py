from __future__ import annotations

import asyncio
import time
import urllib.request

import pytest
from chat import ChatMessage, ChatSession, sqlite_store as chat_sqlite_store
from provider_routing import FailoverExecutor, ProviderRef
from repository_metadata.sqlite_store import connect
from vector_index import VectorIndex, build_code_chunk
from vector_index.search import encode_text


class FakeEmbeddingEngine:
    def isAvailableLocally(self) -> bool:
        return True

    def isAvailable(self) -> bool:
        return True

    def embed(self, text: str):
        return encode_text(text)


class FakeLLMEngine:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list = []

    def isAvailableLocally(self) -> bool:
        return True

    def isAvailable(self) -> bool:
        return True

    def generate(self, envelope) -> str:
        self.calls.append(envelope)
        return self.response_text

    async def generateStream(self, envelope):
        self.calls.append(envelope)
        midpoint = max(1, len(self.response_text) // 2)
        yield self.response_text[:midpoint]
        yield self.response_text[midpoint:]


def _wrap_chat(llm: FakeLLMEngine) -> FailoverExecutor:
    """ChatSession.askStream() now routes through a `FailoverExecutor`
    (spec 029) - a single-provider chain is regression-equivalent to
    today's direct-engine behavior (T034)."""
    return FailoverExecutor("chat", ((ProviderRef("local", "fake"), llm),))


async def _collect_stream(session: ChatSession, question: str) -> tuple[list[str], ChatMessage]:
    fragments: list[str] = []
    final_message: ChatMessage | None = None
    async for item in session.askStream(question):
        if isinstance(item, ChatMessage):
            final_message = item
        else:
            fragments.append(item)
    assert final_message is not None, "askStream must yield the final ChatMessage last"
    return fragments, final_message


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


def test_ask_stream_returns_cited_answer_without_any_outbound_network_request(tmp_path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _blocked_urlopen)

    engine = FakeEmbeddingEngine()
    index = _build_index(tmp_path, engine)
    llm = FakeLLMEngine("Authentication is handled by authenticate_user.")

    session = ChatSession(id="session-1", vectorIndex=index, embeddingEngine=engine, llmEngine=_wrap_chat(llm))

    fragments, message = asyncio.run(
        _collect_stream(session, "where is authentication handled and how is a user validated?")
    )

    index.close()

    assert fragments, "expected at least one streamed fragment"
    assert "".join(fragments) == message.content
    assert message.role == "assistant"
    assert "src/auth/login.py" in message.citedFilePaths
    assert "auth.authenticate_user" in message.citedSymbolIds
    assert len(session.messages) == 2
    assert session.messages[0].role == "user"
    assert session.messages[1] is message
    assert llm.calls, "the local LLM should have been invoked to generate the answer"


def test_ask_stream_persists_user_message_immediately_and_assistant_message_once_at_completion(tmp_path):
    engine = FakeEmbeddingEngine()
    index = _build_index(tmp_path, engine)
    llm = FakeLLMEngine("Authentication is handled by authenticate_user.")
    db_path = tmp_path / "repository-metadata.sqlite"
    connect(db_path).close()
    session_id = "session-persist"
    chat_sqlite_store.create_session(db_path, session_id)
    session = ChatSession(
        id=session_id, vectorIndex=index, embeddingEngine=engine, llmEngine=_wrap_chat(llm), messageStore=db_path
    )

    async def _consume_and_watch_persistence():
        saw_user_message = False
        saw_assistant_message_before_done = False
        async for item in session.askStream("where is authentication handled?"):
            if isinstance(item, str):
                roles = [message.role for message in chat_sqlite_store.load_messages(db_path, session_id)]
                saw_user_message = saw_user_message or "user" in roles
                saw_assistant_message_before_done = saw_assistant_message_before_done or "assistant" in roles
        return saw_user_message, saw_assistant_message_before_done

    saw_user_message, saw_assistant_message_before_done = asyncio.run(_consume_and_watch_persistence())
    index.close()

    assert saw_user_message, "the user question must be persisted before any fragment is yielded"
    assert not saw_assistant_message_before_done, "the assistant message must not be persisted until the stream completes"

    final = chat_sqlite_store.load_messages(db_path, session_id)
    assert [message.role for message in final] == ["user", "assistant"]


def test_session_history_survives_a_simulated_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _blocked_urlopen)

    engine = FakeEmbeddingEngine()
    index = _build_index(tmp_path, engine)
    llm = FakeLLMEngine("Authentication is handled by authenticate_user.")
    db_path = tmp_path / "repository-metadata.sqlite"
    connect(db_path).close()

    session_id = "session-restart"
    chat_sqlite_store.create_session(db_path, session_id)
    session = ChatSession(id=session_id, vectorIndex=index, embeddingEngine=engine, llmEngine=_wrap_chat(llm), messageStore=db_path)
    asyncio.run(_collect_stream(session, "where is authentication handled and how is a user validated?"))
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


class _SearchResult:
    def __init__(self, chunk_id, content, score, symbol_id, file_path):
        self.chunkId = chunk_id
        self.content = content
        self.score = score
        self.sourceSymbolId = symbol_id
        self.sourceFilePath = file_path
        self.chunkType = "code"


class SeededVectorIndex:
    """A fake vector index that only ever finds one chunk, and only when the
    query mentions authentication-related terms or the symbol a prior
    answer cited - proving history-aware enrichment, not a follow-up's own
    bare wording, is what finds it again for an elliptical follow-up (US2)."""

    def __init__(self):
        self.queries: list[str] = []

    def search(self, query: str, k: int):
        self.queries.append(query)
        if "auth.authenticate_user" in query or "authentication" in query.lower():
            return [_SearchResult("chunk-a", "auth chunk", 0.9, "auth.authenticate_user", "src/auth/login.py")]
        return []


def test_elliptical_follow_up_retrieves_the_evidence_the_prior_answer_cited(tmp_path):
    engine = FakeEmbeddingEngine()
    index = SeededVectorIndex()
    llm = FakeLLMEngine("Authentication is handled by authenticate_user.")
    session = ChatSession(id="session-1", vectorIndex=index, embeddingEngine=engine, llmEngine=_wrap_chat(llm), topK=1)

    asyncio.run(_collect_stream(session, "where is authentication handled?"))
    assert index.queries[-1] == "where is authentication handled?"  # first question: not enriched (FR-007)

    llm.response_text = "Yes, authenticate_user has full test coverage."
    _fragments, follow_up_message = asyncio.run(_collect_stream(session, "is that well tested?"))

    assert follow_up_message.citedSymbolIds == ("auth.authenticate_user",)
    assert follow_up_message.citedFilePaths == ("src/auth/login.py",)
    # "is that well tested?" alone shares nothing with the fake index's
    # trigger condition - only the enriched query (carrying forward the
    # prior answer's citation) does, proving enrichment is what found it.
    assert "auth.authenticate_user" in index.queries[-1]
    assert "auth.authenticate_user" not in "is that well tested?"


def test_first_question_in_a_brand_new_session_is_not_enriched(tmp_path):
    engine = FakeEmbeddingEngine()
    index = SeededVectorIndex()
    llm = FakeLLMEngine("Authentication is handled by authenticate_user.")
    session = ChatSession(id="session-1", vectorIndex=index, embeddingEngine=engine, llmEngine=_wrap_chat(llm), topK=1)

    asyncio.run(_collect_stream(session, "where is authentication handled?"))

    assert index.queries == ["where is authentication handled?"]


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


def test_ask_stream_answers_from_an_unparsed_readme_when_no_code_evidence_matches(tmp_path):
    """A README no parser handles is still attached as baseline context.

    `.rst`/`.txt`/extensionless READMEs never reach the index, so for those
    repositories this remains the only way the README informs an answer, and
    it is unaffected by retrieval scoring. A `README.md` takes the other route
    now - see the test below."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "README.rst").write_text(
        "Widget Factory\n==============\n\nThis project builds widgets from raw materials.",
        encoding="utf-8",
    )

    engine = FakeEmbeddingEngine()
    index = VectorIndex(repo_root, tmp_path / "meta.sqlite", embedding_engine=engine)
    llm = FakeLLMEngine("This project builds widgets from raw materials.")
    session = ChatSession(id="session-1", vectorIndex=index, embeddingEngine=engine, llmEngine=_wrap_chat(llm))

    fragments, message = asyncio.run(_collect_stream(session, "what does this project do?"))
    index.close()

    assert fragments, "expected the LLM to actually be called, not the canned no-evidence message"
    assert "does not contain enough indexed evidence" not in message.content
    assert llm.calls, "the LLM should have been invoked using the README as context"
    # Citation is carried as structured data (citedFilePaths), not duplicated
    # as a plain-text "Sources:" footer inside the answer content.
    assert "README.rst" in message.citedFilePaths
    assert message.content == "This project builds widgets from raw materials."


def test_a_markdown_readme_is_not_also_pasted_into_the_prompt(tmp_path):
    """`README.md` reaches answers through the index, not through this path.

    It is parsed and chunked like any other source file, so retrieval returns
    the sections that bear on the question. Attaching the whole file here as
    well would put the same text in the prompt twice and pay for it twice in
    the token budget. With an empty index there is therefore nothing to answer
    from, which is what this asserts."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "README.md").write_text(
        "# Widget Factory\n\nThis project builds widgets from raw materials.", encoding="utf-8"
    )

    engine = FakeEmbeddingEngine()
    index = VectorIndex(repo_root, tmp_path / "meta.sqlite", embedding_engine=engine)
    llm = FakeLLMEngine("unused")
    session = ChatSession(id="session-1", vectorIndex=index, embeddingEngine=engine, llmEngine=_wrap_chat(llm))

    _fragments, message = asyncio.run(_collect_stream(session, "what does this project do?"))
    index.close()

    assert "does not contain enough indexed evidence" in message.content
    assert not llm.calls


def test_ask_stream_still_returns_canned_message_when_no_evidence_and_no_readme(tmp_path):
    engine = FakeEmbeddingEngine()
    index = _build_index_without_chunks(tmp_path, engine)
    llm = FakeLLMEngine("unused")
    session = ChatSession(id="session-1", vectorIndex=index, embeddingEngine=engine, llmEngine=_wrap_chat(llm))

    _fragments, message = asyncio.run(_collect_stream(session, "what does this project do?"))
    index.close()

    assert "does not contain enough indexed evidence" in message.content
    assert not llm.calls, "no README and no evidence - the LLM must not be called at all"


def _build_index_without_chunks(tmp_path, engine: FakeEmbeddingEngine) -> VectorIndex:
    repo_root = tmp_path / "repo-empty"
    repo_root.mkdir()
    return VectorIndex(repo_root, tmp_path / "meta-empty.sqlite", embedding_engine=engine)
