from __future__ import annotations

from vector_index import CodeChunk, IndexRecord, SearchQuery, SearchResult, VectorIndex, VectorEntry, build_code_chunk, build_code_chunks


def test_public_api_exposes_core_types():
    assert CodeChunk.__name__ == "CodeChunk"
    assert VectorEntry.__name__ == "VectorEntry"
    assert SearchQuery.__name__ == "SearchQuery"
    assert SearchResult.__name__ == "SearchResult"
    assert VectorIndex.__name__ == "VectorIndex"
    assert IndexRecord.__name__ == "IndexRecord"
    assert callable(build_code_chunk)
    assert callable(build_code_chunks)


def test_vector_index_supports_expected_methods(tmp_path):
    index = VectorIndex(tmp_path / "repo", tmp_path / "meta.sqlite")

    for method_name in ["addChunk", "addChunks", "removeChunksForFile", "reindexFile", "search", "save", "close"]:
        assert hasattr(index, method_name)

    chunk = CodeChunk(id="chunk-1", content="def run(): pass", embedding=(1.0, 0.0), sourceSymbolId="symbol-1")
    stored = index.addChunk(chunk, sourceFilePath="src/app.py")

    assert stored.chunkId == "chunk-1"
    assert stored.sourceFilePath.endswith("src/app.py")
    assert index.save().repositoryRoot == str((tmp_path / "repo").resolve())
