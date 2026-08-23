from __future__ import annotations

from typing import Any, AsyncIterator

from . import sqlite_store
from .models import ChatMessage, ChatSession as _ChatSessionData, RAGContext
from .prompting import build_prompt_envelope, render_answer_text, render_insufficient_evidence_text
from .retrieval import detect_ambiguous_evidence, is_insufficient_evidence, retrieve_evidence


class LocalDependencyUnavailableError(RuntimeError):
    pass


def ensure_local_dependencies_available(embedding_engine: Any, llm_engine: Any) -> None:
    if not embedding_engine.isAvailableLocally():
        raise LocalDependencyUnavailableError(
            "Local embedding engine is unavailable; ChatSession cannot answer without it."
        )
    if not llm_engine.isAvailableLocally():
        raise LocalDependencyUnavailableError(
            "Local LLM is unavailable; ChatSession cannot answer without it."
        )


class ChatSession(_ChatSessionData):
    async def askStream(self, question: str) -> AsyncIterator[str | ChatMessage]:
        """Replaces `ask()` (026): an async generator yielding the answer's
        fragments as they're generated, then the final, persisted
        `ChatMessage` last. The user's question is persisted immediately;
        the assistant's message is persisted once, only after the stream
        completes successfully (FR-004/FR-011) - a mid-stream exception
        propagates to the caller with nothing persisted for it."""
        ensure_local_dependencies_available(self.embeddingEngine, self.llmEngine)

        history = tuple(self.messages)
        evidence = retrieve_evidence(self.vectorIndex, question, history=history, k=self.topK)

        user_message = ChatMessage(role="user", content=question)
        self.messages.append(user_message)
        self._persist(user_message)

        if not evidence:
            content = render_insufficient_evidence_text(question)
            cited_symbol_ids: tuple[str, ...] = ()
            cited_file_paths: tuple[str, ...] = ()
            yield content
        else:
            insufficient = is_insufficient_evidence(evidence)
            ambiguous = detect_ambiguous_evidence(evidence)
            context = RAGContext(
                question=question,
                conversationHistory=history,
                retrievedEvidence=evidence,
                citationMap=tuple(item.citation() for item in evidence),
            )
            envelope = build_prompt_envelope(context)
            raw_parts: list[str] = []
            async for fragment in self.llmEngine.generateStream(envelope):
                raw_parts.append(fragment)
                yield fragment
            raw_answer = "".join(raw_parts)
            content = render_answer_text(
                raw_answer,
                evidence,
                insufficient=insufficient,
                ambiguous=ambiguous,
            )
            for trailing_fragment in _fragments_beyond_raw_answer(content, raw_answer):
                yield trailing_fragment
            cited_symbol_ids = tuple(dict.fromkeys(item.sourceSymbolId for item in evidence))
            cited_file_paths = tuple(dict.fromkeys(item.sourceFilePath for item in evidence))

        assistant_message = ChatMessage(
            role="assistant",
            content=content,
            citedSymbolIds=cited_symbol_ids,
            citedFilePaths=cited_file_paths,
        )
        self.messages.append(assistant_message)
        self._persist(assistant_message)
        yield assistant_message

    def _persist(self, message: ChatMessage) -> None:
        """Write one message immediately, right after it's appended to
        `self.messages` - never as a rewrite of the whole session (FR-004).
        A no-op when no `messageStore` (db path) is attached, e.g. for a
        purely in-memory session in a test."""
        if self.messageStore is not None:
            sqlite_store.append_message(self.messageStore, self.id, message)


def _fragments_beyond_raw_answer(content: str, raw_answer: str) -> list[str]:
    """The parts of `content` (render_answer_text's assembled output) not
    already covered by the raw fragments streamed from the LLM - e.g. an
    insufficient-evidence banner (before the answer) and/or an
    ambiguous-evidence banner plus the Sources footer (after it).

    Keeps `render_answer_text` the single source of truth for final content
    assembly, while still letting the concatenation of every yielded
    fragment reconstruct `content` exactly (FR-003/SC-003)."""
    stripped = raw_answer.strip()
    if not stripped:
        return [content] if content else []
    position = content.find(stripped)
    if position == -1:
        return [content] if content else []
    fragments: list[str] = []
    if position > 0:
        fragments.append(content[:position])
    suffix_start = position + len(stripped)
    if suffix_start < len(content):
        fragments.append(content[suffix_start:])
    return fragments
