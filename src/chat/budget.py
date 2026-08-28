"""Keep the assembled prompt inside a bounded size.

Before this, only the README was capped (8000 characters) and `k` bounded the
*number* of evidence chunks but not their size. Conversation history had no cap
at all, and it is the fastest-growing part: every prior assistant answer is
replayed into the prompt in full, so a long session eventually overruns the
model's context window with no warning.

Exact token counting is not possible here. The default chat chain is Groq's
`openai/gpt-oss-20b` and the full-local alternative is an Ollama model with a
different tokenizer; neither is available offline, and a dependency that fit one
would be wrong for the other. A conservative characters-per-token ratio is used
instead - the same posture `retrieval.py` already takes with its README cap
("a generous cap, not a token-accurate budget").
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ChatMessage, RetrievedEvidence

# Deliberately below the ~4.0 typical of English prose: code, paths and symbol
# ids tokenize denser, so this over-estimates the token count and errs toward
# sending less than the budget rather than more.
CHARS_PER_TOKEN = 3.0

# Applies to the assembled context sections only - the system prompt, the
# question and the model's own completion all need room beyond this.
DEFAULT_CONTEXT_TOKEN_BUDGET = 8000

_TRUNCATION_MARKER = "\n\n[...truncated to fit the context budget...]"


def estimate_tokens(text: str) -> int:
    """Approximate token count for `text`, rounded up."""
    if not text:
        return 0
    return int(len(text) / CHARS_PER_TOKEN) + 1


@dataclass(frozen=True, slots=True)
class BudgetedContext:
    """What survives the budget, plus what it cost to get there."""

    conversationHistory: tuple[ChatMessage, ...]
    readmeContent: str
    retrievedEvidence: tuple[RetrievedEvidence, ...]
    droppedHistoryMessages: int = 0
    readmeTruncated: bool = False
    truncatedEvidenceCount: int = 0


def fit_to_budget(
    *,
    conversation_history: tuple[ChatMessage, ...],
    readme_content: str,
    retrieved_evidence: tuple[RetrievedEvidence, ...],
    token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
) -> BudgetedContext:
    """Trim the context to `token_budget`, sacrificing the least useful parts first.

    Order of sacrifice: oldest conversation history, then the README, then the
    *body* of the lowest-ranked evidence.

    Evidence chunks are truncated, never dropped. `chat/session.py` derives the
    persisted `citedSymbolIds`/`citedFilePaths` from this same evidence tuple, so
    removing an entry here would leave the answer citing a source the model was
    never shown. Truncating keeps every citation honest: the chunk was shown, if
    only in part.
    """
    history = list(conversation_history)
    readme = readme_content
    evidence = list(retrieved_evidence)
    dropped_history = 0
    readme_truncated = False
    truncated_evidence = 0

    def total() -> int:
        return (
            sum(estimate_tokens(f"{message.role}: {message.content}") for message in history)
            + estimate_tokens(readme)
            + sum(estimate_tokens(item.content) for item in evidence)
        )

    # 1. Oldest history first - the current question is never part of this.
    while total() > token_budget and history:
        history.pop(0)
        dropped_history += 1

    # 2. The README is background, not the answer's evidence.
    if total() > token_budget and readme:
        overshoot_tokens = total() - token_budget
        keep = max(0, len(readme) - int(overshoot_tokens * CHARS_PER_TOKEN) - len(_TRUNCATION_MARKER))
        readme = (readme[:keep].rstrip() + _TRUNCATION_MARKER) if keep > 0 else ""
        readme_truncated = True

    # 3. Last resort: shorten evidence bodies, worst-ranked first, and never
    #    shorten the top-ranked chunk to nothing.
    if total() > token_budget and evidence:
        for position in range(len(evidence) - 1, -1, -1):
            if total() <= token_budget:
                break
            item = evidence[position]
            overshoot_tokens = total() - token_budget
            keep = len(item.content) - int(overshoot_tokens * CHARS_PER_TOKEN) - len(_TRUNCATION_MARKER)
            floor = 1 if position == 0 else 0
            keep = max(floor, keep)
            if keep >= len(item.content):
                continue
            shortened = item.content[:keep].rstrip() or item.content[:1]
            evidence[position] = _replace_content(item, shortened + _TRUNCATION_MARKER)
            truncated_evidence += 1

    return BudgetedContext(
        conversationHistory=tuple(history),
        readmeContent=readme,
        retrievedEvidence=tuple(evidence),
        droppedHistoryMessages=dropped_history,
        readmeTruncated=readme_truncated,
        truncatedEvidenceCount=truncated_evidence,
    )


def _replace_content(item: RetrievedEvidence, content: str) -> RetrievedEvidence:
    """`RetrievedEvidence` is frozen and rejects empty text, so rebuild it explicitly."""
    return RetrievedEvidence(
        chunkId=item.chunkId,
        content=content,
        score=item.score,
        sourceSymbolId=item.sourceSymbolId,
        sourceFilePath=item.sourceFilePath,
        chunkType=item.chunkType,
    )
