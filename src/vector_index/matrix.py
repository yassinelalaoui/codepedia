"""Embeddings held as float32 matrices, one per dimensionality.

Replaces a per-entry Python cosine loop that measured 19.4 s and 2.3 GB at 50k
chunks of 1536 dimensions. Two things make the difference:

* **float32 instead of Python floats.** A CPython `float` object costs 24 bytes
  against 4 for a native float32, so the same 50k vectors occupy ~307 MB rather
  than ~2.3 GB.
* **One matrix-vector product instead of 50k interpreted cosines.** Rows are L2
  normalized at build time and the query is normalized once, so scoring reduces
  to a single dot product per row with no per-comparison norm recomputation -
  the three passes of `search.cosine_similarity` collapse to one, in BLAS.

Grouping by dimensionality is not an optimization, it is what preserves the
multi-provider tolerance the index has always had: a repository can hold 1536-dim
OpenAI vectors beside 768-dim local ones, and a query is only ever compared
against the matrix matching its own length. Entries of another dimensionality are
excluded *by construction* rather than skipped by a guard inside a loop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Iterator, Mapping, Sequence

import numpy as np

DTYPE = np.float32


@dataclass(frozen=True, slots=True)
class ScoredRows:
    """Cosine scores for every row of one dimensionality group."""

    chunkIds: tuple[str, ...]
    scores: np.ndarray

    def __len__(self) -> int:
        return len(self.chunkIds)


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    """L2-normalize in place, leaving all-zero rows as zeros.

    A zero row would otherwise divide by zero; scoring it as 0.0 matches
    `search.cosine_similarity`, which returns 0.0 when either norm is zero.
    """
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    np.divide(matrix, norms, out=matrix, where=norms > 0)
    return matrix


class VectorMatrix:
    """Row-major float32 storage, addressed by chunk id."""

    def __init__(
        self,
        matrices: Mapping[int, np.ndarray],
        row_ids: Mapping[int, Sequence[str]],
    ) -> None:
        self._matrices = dict(matrices)
        self._row_ids = {dimension: tuple(ids) for dimension, ids in row_ids.items()}
        self._row_of: dict[str, tuple[int, int]] = {
            chunk_id: (dimension, row)
            for dimension, ids in self._row_ids.items()
            for row, chunk_id in enumerate(ids)
        }

    @classmethod
    def empty(cls) -> "VectorMatrix":
        return cls({}, {})

    @classmethod
    def build(cls, vectors: Mapping[str, Sequence[float]]) -> "VectorMatrix":
        """Build from in-memory vectors. Convenient for tests and small indexes.

        `build_from_rows` is the memory-flat path used against a real database.
        """
        grouped: dict[int, list[str]] = {}
        for chunk_id, vector in vectors.items():
            grouped.setdefault(len(vector), []).append(chunk_id)

        matrices: dict[int, np.ndarray] = {}
        for dimension, ids in grouped.items():
            matrix = np.empty((len(ids), dimension), dtype=DTYPE)
            for row, chunk_id in enumerate(ids):
                matrix[row] = vectors[chunk_id]
            matrices[dimension] = _normalize_rows(matrix)
        return cls(matrices, grouped)

    @classmethod
    def build_from_rows(
        cls,
        counts: Mapping[int, int],
        rows: Iterable[tuple[str, int, str]],
    ) -> "VectorMatrix":
        """Build from `(chunk_id, dimensionality, json_payload)` rows.

        `counts` lets every matrix be allocated once at its final size, so the
        peak memory cost is one decoded row rather than the whole index
        materialized as Python floats.
        """
        matrices = {
            dimension: np.empty((count, dimension), dtype=DTYPE)
            for dimension, count in counts.items()
            if count > 0
        }
        row_ids: dict[int, list[str]] = {dimension: [] for dimension in matrices}
        next_row = {dimension: 0 for dimension in matrices}

        for chunk_id, dimension, payload in rows:
            matrix = matrices.get(dimension)
            if matrix is None:
                continue
            row = next_row[dimension]
            if row >= matrix.shape[0]:
                continue
            matrix[row] = np.asarray(json.loads(payload), dtype=DTYPE)
            row_ids[dimension].append(chunk_id)
            next_row[dimension] = row + 1

        # A row count can fall short of its allocation if the table changed
        # between the counting query and the streaming one; trim rather than
        # score uninitialized memory.
        trimmed: dict[int, np.ndarray] = {}
        for dimension, matrix in matrices.items():
            filled = next_row[dimension]
            trimmed[dimension] = _normalize_rows(matrix[:filled].copy() if filled != matrix.shape[0] else matrix)
        return cls(trimmed, row_ids)

    def __len__(self) -> int:
        return len(self._row_of)

    @property
    def dimensionalities(self) -> tuple[int, ...]:
        return tuple(sorted(self._matrices))

    def score(self, query_vector: Sequence[float]) -> ScoredRows:
        """Cosine scores against every row of the query's own dimensionality.

        Rows of any other dimensionality are not represented in the returned
        group at all - the exclusion is structural.
        """
        dimension = len(query_vector)
        matrix = self._matrices.get(dimension)
        if matrix is None or matrix.shape[0] == 0:
            return ScoredRows(chunkIds=(), scores=np.empty(0, dtype=DTYPE))

        query = np.asarray(query_vector, dtype=DTYPE)
        norm = float(np.linalg.norm(query))
        if norm == 0.0:
            return ScoredRows(chunkIds=self._row_ids[dimension], scores=np.zeros(matrix.shape[0], dtype=DTYPE))
        return ScoredRows(chunkIds=self._row_ids[dimension], scores=matrix @ (query / norm))

    def vector_for(self, chunk_id: str) -> tuple[float, ...] | None:
        """The stored row as a plain tuple.

        Rows are normalized, so this is the *unit* vector, not the original one -
        only meaningful for scoring, never for round-tripping to storage (which
        keeps its own JSON copy).
        """
        located = self._row_of.get(chunk_id)
        if located is None:
            return None
        dimension, row = located
        return tuple(float(value) for value in self._matrices[dimension][row])


def iter_top_indices(scores: np.ndarray, limit: int) -> Iterator[int]:
    """Row indices of the `limit` highest scores, best first.

    `argpartition` avoids sorting the whole score vector when only a small head
    is needed; the head itself is then sorted. Ties are left to the caller to
    break, which `VectorIndex` does by chunk id so ordering stays deterministic.
    """
    if scores.size == 0 or limit <= 0:
        return iter(())
    take = min(limit, scores.size)
    if take == scores.size:
        head = np.argsort(-scores, kind="stable")
    else:
        candidates = np.argpartition(-scores, take - 1)[:take]
        head = candidates[np.argsort(-scores[candidates], kind="stable")]
    return iter(int(index) for index in head)
