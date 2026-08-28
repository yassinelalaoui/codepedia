from __future__ import annotations

from vector_index import CodeChunk, VectorIndex
from vector_index.search import reciprocal_rank_fusion, score_entry

QUERY_VECTOR = (1.0, 0.0)


class FixedEmbeddingEngine:
    """Always answers with the same query vector, so ranking is fully controlled."""

    def embed(self, text: str):
        return QUERY_VECTOR


def _chunk(chunk_id: str, content: str, embedding, path: str = "a.py") -> CodeChunk:
    return CodeChunk(
        id=chunk_id,
        content=content,
        embedding=embedding,
        sourceSymbolId=f"symbol_{chunk_id}",
        sourceFilePath=path,
    )


def _index_with_buried_identifier(tmp_path) -> VectorIndex:
    """A target that only the lexical side can find.

    Its vector is orthogonal to the query, so cosine ranks it last; its text
    carries the exact identifier being searched for.
    """
    index = VectorIndex(tmp_path, tmp_path / "meta.sqlite", embedding_engine=FixedEmbeddingEngine())
    for number in range(6):
        index.addChunk(
            _chunk(f"noise{number}", f"handles session state {number}", (1.0, 0.05 * number))
        )
    index.addChunk(_chunk("target", "def rotate_refresh_token(store): pass", (0.0, 1.0), path="auth.py"))
    return index


def test_reciprocal_rank_fusion_rewards_agreement_between_the_two_rankings():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "b", "z"]])

    # "a" is first on one side but absent from the other; "b" and "c" are on
    # both. Agreement across the two rankings is what fusion is for, so both
    # outrank the single-sided leader.
    assert fused.index("b") < fused.index("a")
    assert fused.index("c") < fused.index("a")
    assert fused[-1] == "z", "seen once, and last there"
    assert set(fused) == {"a", "b", "c", "z"}


def test_reciprocal_rank_fusion_is_deterministic_on_ties():
    """Same inputs, same output - `rank_entries` makes the same guarantee."""
    first = reciprocal_rank_fusion([["x", "y"], ["y", "x"]])
    second = reciprocal_rank_fusion([["x", "y"], ["y", "x"]])

    assert first == second == sorted(first)


def test_score_entry_rejects_an_entry_of_a_different_dimensionality():
    entry = _chunk("c1", "text", (1.0, 0.0, 0.0))

    assert score_entry((1.0, 0.0), entry) is None


def test_score_entry_rejects_an_entry_the_filters_exclude():
    entry = _chunk("c1", "text", (1.0, 0.0))

    assert score_entry(QUERY_VECTOR, entry, filters={"chunkType": "summary"}) is None
    assert score_entry(QUERY_VECTOR, entry, filters={"chunkType": "code"}) is not None


def test_an_exact_identifier_surfaces_even_when_its_vector_ranks_last(tmp_path):
    index = _index_with_buried_identifier(tmp_path)

    hybrid = index.search("rotate_refresh_token", 3)

    assert "target" in [result.chunkId for result in hybrid]


def test_fusion_changes_the_order_but_never_the_score(tmp_path):
    """The chat layer compares `score` against absolute thresholds.

    `chat/retrieval.py` treats below 0.15 as "not enough evidence" and within
    0.05 of the top as "ambiguous". An RRF score (~0.016 at rank 1) would fire
    both banners on every answer, so `score` must stay a raw cosine.
    """
    index = _index_with_buried_identifier(tmp_path)

    result = next(
        item for item in index.search("rotate_refresh_token", 7) if item.chunkId == "target"
    )

    # Orthogonal to the query vector, so exactly 0.0 - and nowhere near an RRF value.
    assert result.score == 0.0


def test_a_lexical_only_hit_carries_a_real_cosine_score(tmp_path):
    index = _index_with_buried_identifier(tmp_path)

    results = index.search("session state", 7)

    for result in results:
        assert -1.0 <= result.score <= 1.0
    top = results[0]
    assert top.score > 0.5, "a vector-side match should still score highly"


def test_filters_still_apply_to_lexical_hits(tmp_path):
    index = _index_with_buried_identifier(tmp_path)

    results = index.search("rotate_refresh_token", 5, filters={"sourceFilePath": "a.py"})

    assert "target" not in [result.chunkId for result in results]


def test_search_still_returns_at_most_k(tmp_path):
    index = _index_with_buried_identifier(tmp_path)

    assert len(index.search("session state rotate_refresh_token", 2)) == 2
