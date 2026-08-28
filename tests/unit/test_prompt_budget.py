from __future__ import annotations

from chat.budget import CHARS_PER_TOKEN, estimate_tokens, fit_to_budget
from chat.models import ChatMessage, RAGContext, RetrievedEvidence
from chat.prompting import build_prompt_envelope


def _message(role: str, content: str) -> ChatMessage:
    return ChatMessage(role=role, content=content)


def _evidence(chunk_id: str, content: str, score: float = 0.9) -> RetrievedEvidence:
    return RetrievedEvidence(
        chunkId=chunk_id,
        content=content,
        score=score,
        sourceSymbolId=f"symbol_{chunk_id}",
        sourceFilePath="src/module.py",
    )


def _long_history(messages: int, size: int = 400) -> tuple[ChatMessage, ...]:
    return tuple(
        _message("user" if index % 2 == 0 else "assistant", f"m{index} " + "x" * size)
        for index in range(messages)
    )


def test_estimate_tokens_is_conservative_for_code():
    """Under-counting would let the prompt overrun; the ratio must over-count."""
    assert CHARS_PER_TOKEN < 4.0
    assert estimate_tokens("x" * 300) >= 100
    assert estimate_tokens("") == 0


def test_a_short_context_is_left_completely_untouched():
    history = (_message("user", "hello"),)
    evidence = (_evidence("c1", "def f(): pass"),)

    budgeted = fit_to_budget(
        conversation_history=history, readme_content="readme", retrieved_evidence=evidence
    )

    assert budgeted.conversationHistory == history
    assert budgeted.readmeContent == "readme"
    assert budgeted.retrievedEvidence == evidence
    assert budgeted.droppedHistoryMessages == 0
    assert budgeted.readmeTruncated is False
    assert budgeted.truncatedEvidenceCount == 0


def test_the_oldest_history_is_sacrificed_first():
    history = _long_history(40)

    budgeted = fit_to_budget(
        conversation_history=history,
        readme_content="",
        retrieved_evidence=(_evidence("c1", "def f(): pass"),),
        token_budget=500,
    )

    assert budgeted.droppedHistoryMessages > 0
    # Whatever survives is the tail: the most recent turns.
    assert budgeted.conversationHistory == history[len(history) - len(budgeted.conversationHistory):]


def test_the_readme_is_only_trimmed_once_history_is_exhausted():
    budgeted = fit_to_budget(
        conversation_history=(),
        readme_content="R" * 30_000,
        retrieved_evidence=(_evidence("c1", "def f(): pass"),),
        token_budget=500,
    )

    assert budgeted.readmeTruncated is True
    assert len(budgeted.readmeContent) < 30_000


def test_evidence_is_truncated_but_never_dropped():
    """`session.py` derives the persisted citations from this same tuple.

    Dropping an entry would leave the answer citing a source the model was never
    shown; truncating keeps every citation honest.
    """
    evidence = tuple(_evidence(f"c{index}", "y" * 20_000) for index in range(4))

    budgeted = fit_to_budget(
        conversation_history=(), readme_content="", retrieved_evidence=evidence, token_budget=400
    )

    assert len(budgeted.retrievedEvidence) == len(evidence)
    assert [item.chunkId for item in budgeted.retrievedEvidence] == [item.chunkId for item in evidence]
    assert budgeted.truncatedEvidenceCount > 0


def test_the_top_ranked_evidence_always_keeps_some_content():
    evidence = tuple(_evidence(f"c{index}", "y" * 20_000) for index in range(3))

    budgeted = fit_to_budget(
        conversation_history=(), readme_content="", retrieved_evidence=evidence, token_budget=10
    )

    assert budgeted.retrievedEvidence[0].content


def test_the_worst_ranked_evidence_is_shortened_before_the_best():
    evidence = (
        _evidence("top", "y" * 4_000, score=0.9),
        _evidence("worst", "z" * 4_000, score=0.2),
    )

    budgeted = fit_to_budget(
        conversation_history=(), readme_content="", retrieved_evidence=evidence, token_budget=1_400
    )

    by_id = {item.chunkId: item for item in budgeted.retrievedEvidence}
    assert len(by_id["worst"].content) < len(by_id["top"].content)


def test_the_assembled_prompt_stays_bounded_for_a_very_long_session():
    context = RAGContext(
        question="what does the indexer do?",
        conversationHistory=_long_history(200, size=800),
        retrievedEvidence=(_evidence("c1", "def index(): pass"),),
        citationMap=(),
        readmePath="README.md",
        readmeContent="R" * 8_000,
    )

    envelope = build_prompt_envelope(context, token_budget=2_000)

    rendered = envelope.to_prompt_text()
    assert estimate_tokens(rendered) < 2_000 + estimate_tokens(context.question) + 1_500
    # The question itself is never a casualty of the budget.
    assert context.question in rendered
