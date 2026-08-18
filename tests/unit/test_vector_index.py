from __future__ import annotations

from vector_index import CodeChunk, SearchQuery, VectorIndex, build_code_chunk, build_code_chunks, rank_entries
from vector_index.search import encode_text


class FakeEmbeddingEngine:
    def embed(self, text: str):
        return encode_text(text)


def test_code_chunk_normalizes_embedding_and_path():
    chunk = CodeChunk(id="chunk-1", content="print('hello')", embedding=[1, 2], sourceSymbolId="symbol-1", sourceFilePath=r"src\main.py")

    assert chunk.embedding == (1.0, 2.0)
    assert chunk.sourceFilePath == "src/main.py"
    assert chunk.dimensionality == 2


def test_build_chunk_helpers_create_stable_ids_and_embeddings():
    engine = FakeEmbeddingEngine()
    first = build_code_chunk(
        "def alpha():\n    return 1",
        source_symbol_id="symbol-alpha",
        source_file_path="src/alpha.py",
        embedding_engine=engine,
    )
    second = build_code_chunk(
        "def alpha():\n    return 1",
        source_symbol_id="symbol-alpha",
        source_file_path="src/alpha.py",
        embedding_engine=engine,
    )

    assert first.id == second.id
    assert first.embedding == second.embedding
    assert first.chunkType == "code"

    chunks = build_code_chunks(["one", "two"], source_symbol_id="symbol-beta", embedding_engine=engine)
    assert len(chunks) == 2


def test_rank_entries_orders_by_similarity_then_chunk_id():
    query = encode_text("database helper function")
    entry_a = CodeChunk(id="chunk-a", content="database helper", embedding=query, sourceSymbolId="symbol-a")
    entry_b = CodeChunk(id="chunk-b", content="logging utility", embedding=encode_text("logging utility"), sourceSymbolId="symbol-b")
    results = rank_entries(query, [entry_a, entry_b], k=1)

    assert results[0].chunkId == "chunk-a"


def test_search_query_validates_k():
    query = SearchQuery(queryText="hello", k=1)
    assert query.k == 1


def test_vector_index_add_remove_and_reindex_round_trip(tmp_path):
    engine = FakeEmbeddingEngine()
    index = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite", embedding_engine=engine)
    first = build_code_chunk("alpha helper", source_symbol_id="symbol-alpha", source_file_path="src/alpha.py", embedding_engine=engine)
    second = build_code_chunk("beta helper", source_symbol_id="symbol-beta", source_file_path="src/beta.py", embedding_engine=engine)

    index.addChunks([first, second])
    assert len(index.entries) == 2
    assert len(index.search("alpha helper", k=2)) == 2

    removed = index.removeChunksForFile("src/alpha.py")
    assert removed == (first.id,)
    assert len(index.chunks_for_file("src/alpha.py")) == 0

    replaced = index.reindexFile(
        "src/beta.py",
        [build_code_chunk("beta helper updated", source_symbol_id="symbol-beta", source_file_path="src/beta.py", embedding_engine=engine)],
    )
    assert len(replaced) == 1
    assert index.search("updated helper", k=1)[0].sourceFilePath.endswith("src/beta.py")
