from __future__ import annotations

from typing import Any

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
    def ask(self, question: str) -> ChatMessage:
        ensure_local_dependencies_available(self.embeddingEngine, self.llmEngine)

        history = tuple(self.messages)
        evidence = retrieve_evidence(self.vectorIndex, question, k=self.topK)

        if not evidence:
            content = render_insufficient_evidence_text(question)
            cited_symbol_ids: tuple[str, ...] = ()
            cited_file_paths: tuple[str, ...] = ()
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
            raw_answer = self.llmEngine.generate(envelope)
            content = render_answer_text(
                raw_answer,
                evidence,
                insufficient=insufficient,
                ambiguous=ambiguous,
            )
            cited_symbol_ids = tuple(dict.fromkeys(item.sourceSymbolId for item in evidence))
            cited_file_paths = tuple(dict.fromkeys(item.sourceFilePath for item in evidence))

        user_message = ChatMessage(role="user", content=question)
        assistant_message = ChatMessage(
            role="assistant",
            content=content,
            citedSymbolIds=cited_symbol_ids,
            citedFilePaths=cited_file_paths,
        )
        self.messages.append(user_message)
        self._persist(user_message)
        self.messages.append(assistant_message)
        self._persist(assistant_message)
        return assistant_message

    def _persist(self, message: ChatMessage) -> None:
        """Write one message immediately, right after it's appended to
        `self.messages` - never as a rewrite of the whole session (FR-004).
        A no-op when no `messageStore` (db path) is attached, e.g. for a
        purely in-memory session in a test."""
        if self.messageStore is not None:
            sqlite_store.append_message(self.messageStore, self.id, message)
