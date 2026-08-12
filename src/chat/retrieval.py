from __future__ import annotations

from typing import Any

from .models import RetrievedEvidence

DEFAULT_TOP_K = 5
INSUFFICIENT_EVIDENCE_SCORE_THRESHOLD = 0.15
AMBIGUOUS_SCORE_DELTA = 0.05


def retrieve_evidence(vector_index: Any, question: str, *, k: int = DEFAULT_TOP_K) -> tuple[RetrievedEvidence, ...]:
    results = vector_index.search(question, k)
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
