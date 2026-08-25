from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import ChatMessage, RetrievedEvidence

DEFAULT_TOP_K = 5
DEFAULT_CONTEXT_WINDOW = 3
INSUFFICIENT_EVIDENCE_SCORE_THRESHOLD = 0.15
AMBIGUOUS_SCORE_DELTA = 0.05

# Checked in order; the first match wins. Covers the common casing/extension
# variants without doing a full case-insensitive directory scan.
_README_CANDIDATES = ("README.md", "Readme.md", "readme.md", "README", "README.rst", "README.txt")

# A generous cap, not a token-accurate budget - keeps one outsized README
# from dominating every single chat prompt's token cost. Truncated rather
# than omitted, so even a huge README still contributes its introduction.
DEFAULT_README_MAX_CHARS = 8000


def read_readme_content(
    repository_root: str | Path, *, max_chars: int = DEFAULT_README_MAX_CHARS
) -> tuple[str, str]:
    """The repository's README, read fresh on every call (constitution
    2.7 - repository read-only; this is the one read, never a write) so a
    README edited mid-session is picked up on the next question.

    Returns `(relative_path, content)` - `("", "")` when no README file is
    found or it can't be read as text."""
    root = Path(repository_root).expanduser()
    for candidate in _README_CANDIDATES:
        path = root / candidate
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return "", ""
        if not text:
            return "", ""
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "\n\n[...truncated...]"
        return candidate, text
    return "", ""


def build_enriched_query(
    question: str,
    history: tuple[ChatMessage, ...],
    *,
    context_window: int = DEFAULT_CONTEXT_WINDOW,
) -> str:
    """The query actually sent to the vector index: `question` alone when
    `history` is empty (FR-007), or `question` combined with a small, fixed
    window of recent conversational context (FR-005) - the text of up to
    `context_window` recent user questions, and the citedSymbolIds/
    citedFilePaths already recorded on up to `context_window` recent
    assistant messages. Pure local text/citation concatenation - no LLM
    call, no network dependency (FR-006/FR-010).

    The current question is always included, and always last, so it stays
    the dominant signal even alongside unrelated older context (User Story
    2, Acceptance Scenario 3)."""
    if not history:
        return question

    recent_user_questions = [message.content for message in history if message.role == "user"][-context_window:]
    recent_assistant_messages = [message for message in history if message.role == "assistant"][-context_window:]
    recent_citations: list[str] = []
    for message in recent_assistant_messages:
        recent_citations.extend(message.citedSymbolIds)
        recent_citations.extend(message.citedFilePaths)
    recent_citations = list(dict.fromkeys(recent_citations))

    parts: list[str] = []
    if recent_user_questions:
        parts.append("Recent conversation questions: " + " | ".join(recent_user_questions))
    if recent_citations:
        parts.append("Recently discussed code: " + ", ".join(recent_citations))
    parts.append(question)
    return "\n".join(parts)


def retrieve_evidence(
    vector_index: Any,
    question: str,
    history: tuple[ChatMessage, ...] = (),
    *,
    k: int = DEFAULT_TOP_K,
    context_window: int = DEFAULT_CONTEXT_WINDOW,
) -> tuple[RetrievedEvidence, ...]:
    search_query = build_enriched_query(question, history, context_window=context_window)
    results = vector_index.search(search_query, k)
    evidence: list[RetrievedEvidence] = []
    seen_chunk_ids: set[str] = set()
    for result in results:
        if result.chunkId in seen_chunk_ids:
            continue
        seen_chunk_ids.add(result.chunkId)
        evidence.append(
            RetrievedEvidence(
                chunkId=result.chunkId,
                content=result.content,
                score=result.score,
                sourceSymbolId=result.sourceSymbolId,
                sourceFilePath=result.sourceFilePath,
                chunkType=result.chunkType,
            )
        )
    return tuple(evidence)


def is_insufficient_evidence(
    evidence: tuple[RetrievedEvidence, ...],
    *,
    threshold: float = INSUFFICIENT_EVIDENCE_SCORE_THRESHOLD,
) -> bool:
    if not evidence:
        return True
    return evidence[0].score < threshold


def detect_ambiguous_evidence(
    evidence: tuple[RetrievedEvidence, ...],
    *,
    delta: float = AMBIGUOUS_SCORE_DELTA,
) -> bool:
    if len(evidence) < 2:
        return False
    top_score = evidence[0].score
    close_count = sum(1 for item in evidence if top_score - item.score <= delta)
    return close_count > 1
