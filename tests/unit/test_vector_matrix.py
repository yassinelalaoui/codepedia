from __future__ import annotations

import json
import random

import numpy as np
import pytest

from vector_index.matrix import VectorMatrix, iter_top_indices
from vector_index.search import cosine_similarity


def _random_vectors(count: int, dimension: int, seed: int = 1) -> dict[str, tuple[float, ...]]:
    rng = random.Random(seed)
    return {
        f"c{index}": tuple(rng.random() for _ in range(dimension)) for index in range(count)
    }


def test_scores_match_the_reference_cosine_implementation():
    """The matrix path must agree with `search.cosine_similarity`.

    Both are used - `rank_entries` keeps the per-object path for callers passing
    ad-hoc chunks - so a divergence would make results depend on which path ran.
    Tolerance is float32 precision, not correctness slack.
    """
    vectors = _random_vectors(40, 8)
    query = tuple(random.Random(2).random() for _ in range(8))

    scored = VectorMatrix.build(vectors).score(query)

    for chunk_id, score in zip(scored.chunkIds, scored.scores):
        assert float(score) == pytest.approx(cosine_similarity(query, vectors[chunk_id]), abs=1e-5)



def test_a_query_only_sees_rows_of_its_own_dimensionality():
    """Multi-provider tolerance, structural rather than guarded.

    A repository can hold 1536-dim OpenAI vectors beside 768-dim local ones.
    """
    matrix = VectorMatrix.build({"two": (1.0, 0.0), "three": (1.0, 0.0, 0.0)})

    assert matrix.dimensionalities == (2, 3)
    assert matrix.score((1.0, 0.0)).chunkIds == ("two",)
    assert matrix.score((1.0, 0.0, 0.0)).chunkIds == ("three",)


def test_an_unknown_dimensionality_scores_nothing_rather_than_raising():
    matrix = VectorMatrix.build({"two": (1.0, 0.0)})

    scored = matrix.score((1.0, 0.0, 0.0, 0.0))

    assert scored.chunkIds == ()
    assert len(scored.scores) == 0


def test_a_zero_vector_scores_zero_instead_of_dividing_by_zero():
    matrix = VectorMatrix.build({"zero": (0.0, 0.0), "unit": (1.0, 0.0)})

    scored = matrix.score((1.0, 0.0))
    by_id = dict(zip(scored.chunkIds, (float(value) for value in scored.scores)))

    assert by_id["zero"] == 0.0
    assert by_id["unit"] == pytest.approx(1.0, abs=1e-5)


def test_a_zero_query_scores_everything_zero():
    matrix = VectorMatrix.build({"unit": (1.0, 0.0)})

    scored = matrix.score((0.0, 0.0))

    assert [float(value) for value in scored.scores] == [0.0]


def test_build_from_rows_produces_the_same_scores_as_build():
    vectors = _random_vectors(12, 6, seed=7)
    query = tuple(random.Random(8).random() for _ in range(6))
    counts = {6: len(vectors)}
    rows = [
        (chunk_id, 6, json.dumps(list(vector))) for chunk_id, vector in vectors.items()
    ]

    from_rows = VectorMatrix.build_from_rows(counts, rows).score(query)
    from_memory = VectorMatrix.build(vectors).score(query)

    assert dict(zip(from_rows.chunkIds, from_rows.scores.tolist())) == pytest.approx(
        dict(zip(from_memory.chunkIds, from_memory.scores.tolist())), abs=1e-5
    )



def test_build_from_rows_trims_when_fewer_rows_arrive_than_counted():
    """The table can change between the counting query and the streaming one."""
    matrix = VectorMatrix.build_from_rows({4: 3}, [("only", 4, json.dumps([1.0, 0.0, 0.0, 0.0]))])

    assert len(matrix) == 1
    assert matrix.score((1.0, 0.0, 0.0, 0.0)).chunkIds == ("only",)


def test_iter_top_indices_returns_the_best_rows_first():
    scores = np.array([0.1, 0.9, 0.5, 0.7], dtype=np.float32)

    assert list(iter_top_indices(scores, 2)) == [1, 3]
    assert list(iter_top_indices(scores, 10)) == [1, 3, 2, 0]
    assert list(iter_top_indices(scores, 0)) == []
    assert list(iter_top_indices(np.empty(0, dtype=np.float32), 5)) == []


def test_vector_for_returns_the_normalized_row():
    matrix = VectorMatrix.build({"c": (3.0, 4.0)})

    stored = matrix.vector_for("c")

    assert stored is not None
    assert stored[0] == pytest.approx(0.6, abs=1e-5)
    assert stored[1] == pytest.approx(0.8, abs=1e-5)
    assert matrix.vector_for("absent") is None
