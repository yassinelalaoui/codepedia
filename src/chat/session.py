from __future__ import annotations

from typing import Any, AsyncIterator

from . import sqlite_store
from .models import ChatMessage, ChatSession as _ChatSessionData, RAGContext
from .prompting import build_prompt_envelope, render_answer_text, render_insufficient_evidence_text
from .retrieval import detect_ambiguous_evidence, is_insufficient_evidence, read_readme_content, retrieve_evidence


class LocalDependencyUnavailableError(RuntimeError):
    pass


def ensure_local_dependencies_available(embedding_engine: Any, llm_engine: Any) -> None:
    """Works identically whether handed a raw engine or a
    `provider_routing.FailoverExecutor` wrapping a chain - both expose
    `isAvailable()` (research.md §13's C2 fix)."""
    if not embedding_engine.isAvailable():
        raise LocalDependencyUnavailableError(
            "No embedding provider is currently available; ChatSession cannot answer without one."
        )
    if not llm_engine.isAvailable():
        raise LocalDependencyUnavailableError(
            "No chat provider is currently available; ChatSession cannot answer without one."
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
        # Unconditional baseline context - unlike evidence, never subject to
        # retrieval scoring, so a broad "what does this project do?"-style
        # question can still be answered even when nothing in the vector
        # index scores as relevant for it (getattr: some vectorIndex test
        # doubles don't carry a repositoryRoot at all).
        repository_root = getattr(self.vectorIndex, "repositoryRoot", None)
        readme_path, readme_content = read_readme_content(repository_root) if repository_root else ("", "")

        user_message = ChatMessage(role="user", content=question)
        self.messages.append(user_message)
        self._persist(user_message)

        if not evidence and not readme_content:
            content = render_insufficient_evidence_text(question)
            cited_symbol_ids: tuple[str, ...] = ()
            cited_file_paths: tuple[str, ...] = ()
            generated_by = ""
            yield content
        else:
            insufficient = is_insufficient_evidence(evidence) if evidence else False
            ambiguous = detect_ambiguous_evidence(evidence)
            context = RAGContext(
                question=question,
                conversationHistory=history,
                retrievedEvidence=evidence,
                citationMap=tuple(item.citation() for item in evidence),
                readmePath=readme_path,
                readmeContent=readme_content,
            )
            envelope = build_prompt_envelope(context)
            raw_parts: list[str] = []
            async for fragment in self.llmEngine.stream(lambda engine: engine.generateStream(envelope)):
                raw_parts.append(fragment)
                yield fragment
            raw_answer = "".join(raw_parts)
            generated_by = str(self.llmEngine.providerUsed) if self.llmEngine.providerUsed is not None else ""
            content = render_answer_text(
                raw_answer,
                insufficient=insufficient,
                ambiguous=ambiguous,
            )
            for trailing_fragment in _fragments_beyond_raw_answer(content, raw_answer):
                yield trailing_fragment
            cited_symbol_ids = tuple(dict.fromkeys(item.sourceSymbolId for item in evidence))
            cited_paths = [*([readme_path] if readme_path else []), *(item.sourceFilePath for item in evidence)]
            cited_file_paths = tuple(dict.fromkeys(cited_paths))

        assistant_message = ChatMessage(
            role="assistant",
            content=content,
            citedSymbolIds=cited_symbol_ids,
            citedFilePaths=cited_file_paths,
            generatedBy=generated_by,
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
