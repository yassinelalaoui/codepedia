from __future__ import annotations

from local_llm import PromptEnvelope

from .models import ChatMessage, RAGContext, RetrievedEvidence

SYSTEM_PROMPT = (
    "You are a local code assistant. Answer only using the provided repository "
    "evidence. Cite the file paths and symbols that support your answer."
)


def _format_evidence_block(evidence: tuple[RetrievedEvidence, ...]) -> str:
    entries = [
        f"[{item.sourceFilePath} :: {item.sourceSymbolId}] ({item.chunkType}, score={item.score:.3f})\n{item.content}"
        for item in evidence
    ]
    return "\n\n".join(entries)


def _format_history_block(history: tuple[ChatMessage, ...]) -> str:
    return "\n".join(f"{message.role}: {message.content}" for message in history)


def build_prompt_envelope(context: RAGContext) -> PromptEnvelope:
    context_sections: list[str] = []
    if context.conversationHistory:
        context_sections.append(f"Conversation so far:\n{_format_history_block(context.conversationHistory)}")
    if context.retrievedEvidence:
        context_sections.append(f"Retrieved evidence:\n{_format_evidence_block(context.retrievedEvidence)}")
    return PromptEnvelope.from_prompt(
        context.question,
        context=context_sections,
        system_prompt=SYSTEM_PROMPT,
    )


def _citation_lines(evidence: tuple[RetrievedEvidence, ...]) -> tuple[str, ...]:
    seen: set[tuple[str, str]] = set()
    lines: list[str] = []
    for item in evidence:
        key = (item.sourceFilePath, item.sourceSymbolId)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{item.sourceFilePath} ({item.sourceSymbolId})")
    return tuple(lines)


def render_answer_text(
    raw_answer: str,
    evidence: tuple[RetrievedEvidence, ...],
    *,
    insufficient: bool = False,
    ambiguous: bool = False,
) -> str:
    sections: list[str] = []
    if insufficient:
        sections.append(
            "The repository does not contain enough evidence to fully answer this "
            "question. Here is the nearest relevant local evidence found:"
        )
    answer = raw_answer.strip()
    if answer:
        sections.append(answer)
    if ambiguous:
        sections.append(
            "Multiple retrieved fragments were similarly relevant; the sources below "
            "are ranked by closeness to the question."
        )
    citation_lines = _citation_lines(evidence)
    if citation_lines:
        sections.append("Sources:\n" + "\n".join(f"- {line}" for line in citation_lines))
    return "\n\n".join(sections)


def render_insufficient_evidence_text(question: str) -> str:
    return (
        "The repository does not contain enough indexed evidence to answer the "
        f'question: "{question}". No relevant local fragments were found.'
    )
