from __future__ import annotations

import hashlib
import math
import re
from dataclasses import replace
from typing import Any, Iterable, Mapping, Sequence

from .models import CodeChunk, SearchQuery, SearchResult, VectorEntry


TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")


def _tokenize(text: str) -> list[str]:
    tokens = [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]
    if tokens:
        return tokens
    return [piece.lower() for piece in text.split() if piece.strip()]


def encode_text(text: str, dimension: int = 128) -> tuple[float, ...]:
    vector = [0.0] * dimension
    tokens = _tokenize(text)
    if not tokens:
        return tuple(vector)

    for token in tokens:
        token_hash = int(hashlib.sha1(token.encode("utf-8")).hexdigest()[:8], 16)
        bucket = token_hash % dimension
        weight = 1.0 + min(len(token), 12) / 12.0
        vector[bucket] += weight

        for index in range(len(token) - 1):
            shingle = token[index : index + 2]
            shingle_hash = int(hashlib.sha1(shingle.encode("utf-8")).hexdigest()[:8], 16)
            vector[shingle_hash % dimension] += 0.25

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return tuple(vector)
    return tuple(value / norm for value in vector)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same dimensionality")
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _matches_filters(entry: VectorEntry, filters: Mapping[str, Any]) -> bool:
    for key, expected in filters.items():
        if expected is None:
            continue
        if key == "sourceFilePath" and entry.sourceFilePath != str(expected).replace("\\", "/"):
            return False
        if key == "sourceSymbolId" and entry.sourceSymbolId != expected:
            return False
        if key == "chunkType" and entry.chunkType != expected:
            return False
        if key == "chunkId" and entry.chunkId != expected:
            return False
        # Checked before rank_entries' dimensionality comparison below, so a
        # vector from a different embedding model/provider is excluded by
        # construction rather than ever reaching (and crashing) that check
        # (spec FR-010, research.md §8).
        if key == "embeddingModelId" and entry.embeddingModelId != expected:
            return False
    return True


def _coerce_entry(entry: VectorEntry | CodeChunk) -> VectorEntry:
    if isinstance(entry, VectorEntry):
        return entry
    return VectorEntry.from_chunk(entry)


RRF_K = 60
"""Reciprocal Rank Fusion damping constant, the value from the original paper.

It flattens the contribution of deep ranks so a result the lexical side ranked
first cannot be buried by a long vector ranking, and vice versa.
"""


def score_entry(query_vector: Sequence[float], entry: VectorEntry | CodeChunk, *, filters: Mapping[str, Any] | None = None) -> float | None:
    """Cosine score for one entry, or None when it fails the same gates as `rank_entries`.

    Used to give a lexical-only hit a real similarity score: the fused ordering
    decides position, but `SearchResult.score` must stay a raw cosine value
    because the chat layer compares it against absolute thresholds
    (`chat/retrieval.py`'s insufficient/ambiguous banners).
    """
    coerced = _coerce_entry(entry)
    if not _matches_filters(coerced, filters or {}):
        return None
    if coerced.dimensionality != len(query_vector):
        return None
    return cosine_similarity(query_vector, coerced.vector)


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], *, k_constant: int = RRF_K) -> list[str]:
    """Fuse several ranked id lists into one order, best first.

    Ties are broken by chunk id so the same inputs always produce the same
    output - `rank_entries` makes the same guarantee, and existing tests depend
    on search being deterministic.
    """
    fused: dict[str, float] = {}
    for ranking in rankings:
        for position, chunk_id in enumerate(ranking):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (k_constant + position + 1)
    return sorted(fused, key=lambda chunk_id: (-fused[chunk_id], chunk_id))


def rank_entries(
    query_vector: Sequence[float],
    entries: Iterable[VectorEntry | CodeChunk],
    *,
    k: int,
    filters: Mapping[str, Any] | None = None,
) -> list[SearchResult]:
    if k <= 0:
        raise ValueError("k must be positive")
    active_filters = filters or {}
    scored: list[tuple[float, VectorEntry]] = []
    for entry in entries:
        entry = _coerce_entry(entry)
        if not _matches_filters(entry, active_filters):
            continue
        if entry.dimensionality != len(query_vector):
            # A repository can accumulate vectors from more than one
            # embedding model/provider (spec User Story 4) - an
            # incompatible-dimensionality entry is silently excluded from
            # ranking rather than crashing the whole search (research.md
            # §8; the `embeddingModelId` filter above already excludes most
            # of these by construction, this is the remaining safety net
            # for any entry with no/mismatched model id).
            continue
        scored.append((cosine_similarity(query_vector, entry.vector), entry))
    scored.sort(key=lambda item: (-item[0], item[1].chunkId))
    return [
        SearchResult(
            chunkId=entry.chunkId,
            content=entry.content,
            score=score,
            sourceSymbolId=entry.sourceSymbolId,
            sourceFilePath=entry.sourceFilePath,
            chunkType=entry.chunkType,
        )
        for score, entry in scored[:k]
    ]


def search_query_to_vector(query: SearchQuery, *, dimension: int = 128) -> tuple[float, ...]:
    return encode_text(query.queryText, dimension=dimension)


def rebuild_results(
    query: SearchQuery,
    entries: Iterable[VectorEntry],
    *,
    dimension: int = 128,
) -> list[SearchResult]:
    return rank_entries(search_query_to_vector(query, dimension=dimension), entries, k=query.k, filters=query.filters)
