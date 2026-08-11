from __future__ import annotations

from pathlib import Path
from time import perf_counter

from vector_index import VectorIndex, build_code_chunk
from vector_index.search import encode_text


class FakeEmbeddingEngine:
    def embed(self, text: str):
        return encode_text(text)


def _create_index(tmp_path: Path) -> VectorIndex:
    return VectorIndex(tmp_path / "repo", tmp_path / "index.sqlite", tmp_path / "meta.sqlite", embedding_engine=FakeEmbeddingEngine())


def test_index_can_add_search_reopen_and_replace(tmp_path):
    engine = FakeEmbeddingEngine()
    index = VectorIndex(tmp_path / "repo", tmp_path / "index.sqlite", tmp_path / "meta.sqlite", embedding_engine=engine)
    alpha = build_code_chunk("alpha handles repository metadata", source_symbol_id="symbol-alpha", source_file_path="src/alpha.py", embedding_engine=engine)
    beta = build_code_chunk("beta handles semantic retrieval", source_symbol_id="symbol-beta", source_file_path="src/beta.py", embedding_engine=engine)

    index.addChunks([alpha, beta])
    first_results = index.search("semantic retrieval", k=2)
    assert first_results[0].chunkId == beta.id
    assert first_results[0].sourceSymbolId == "symbol-beta"

    index.save().to_dict()
    index.close()

    reopened = VectorIndex.load(tmp_path / "repo", tmp_path / "index.sqlite", tmp_path / "meta.sqlite", embedding_engine=engine)
    reopened_results = reopened.search("semantic retrieval", k=2)
    assert [item.chunkId for item in reopened_results] == [item.chunkId for item in first_results]

    updated_beta = build_code_chunk("beta now handles vector search ranking", source_symbol_id="symbol-beta", source_file_path="src/beta.py", embedding_engine=engine)
    reopened.reindexFile("src/beta.py", [updated_beta])
    updated_results = reopened.search("vector search ranking", k=1)
    assert updated_results[0].chunkId == updated_beta.id


def test_index_removes_deleted_file_vectors_and_keeps_unrelated_entries(tmp_path):
    engine = FakeEmbeddingEngine()
    index = VectorIndex(tmp_path / "repo", tmp_path / "index.sqlite", tmp_path / "meta.sqlite", embedding_engine=engine)
    alpha = build_code_chunk("alpha helper", source_symbol_id="symbol-alpha", source_file_path="src/alpha.py", embedding_engine=engine)
    beta = build_code_chunk("beta helper", source_symbol_id="symbol-beta", source_file_path="src/beta.py", embedding_engine=engine)
    index.addChunks([alpha, beta])

    removed = index.removeChunksForFile("src/alpha.py")
    assert removed == (alpha.id,)
    assert index.search("alpha helper", k=2)[0].chunkId == beta.id


def test_empty_index_returns_no_matches_and_is_fast_enough_for_interactive_use(tmp_path):
    index = VectorIndex(tmp_path / "repo", tmp_path / "index.sqlite", tmp_path / "meta.sqlite", embedding_engine=FakeEmbeddingEngine())
    start = perf_counter()
    results = index.search("anything at all", k=5)
    duration = perf_counter() - start

    assert results == []
    assert duration < 0.25
