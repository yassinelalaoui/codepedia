from __future__ import annotations

from reindex_pipeline.embeddings import update_embeddings
from vector_index import VectorIndex
from vector_index.search import encode_text

from ._doc_generator_support import build_indexed_repo


class FakeEmbeddingEngine:
    def embed(self, text: str):
        return encode_text(text)


def _embed_file(tmp_path, root, store, relative_path):
    index = VectorIndex(root, tmp_path / "vectors.sqlite", embedding_engine=FakeEmbeddingEngine())
    chunks = update_embeddings(
        repository_root=root,
        relative_path=relative_path,
        metadata_store=store,
        vector_index=index,
        embedding_engine=FakeEmbeddingEngine(),
    )
    return index, chunks


def _symbols_of(store, root, relative_path):
    return store.load_source_file(repository_root=root, path=root / relative_path)


def test_a_class_now_produces_its_own_chunk(tmp_path):
    """`beta.py` declares `class Child(BaseThing)`; classes used to be skipped entirely."""
    root, store, _graph = build_indexed_repo(tmp_path)
    bundle = _symbols_of(store, root, "beta.py")
    class_ids = {symbol.id for symbol in bundle.classes}
    assert class_ids, "fixture precondition: beta.py declares at least one class"

    _index, chunks = _embed_file(tmp_path, root, store, "beta.py")

    embedded_symbol_ids = {chunk.sourceSymbolId for chunk in chunks}
    assert class_ids & embedded_symbol_ids


def test_a_summarized_symbol_produces_a_separate_summary_chunk(tmp_path):
    root, store, _graph = build_indexed_repo(tmp_path)
    bundle = _symbols_of(store, root, "beta.py")
    target = bundle.classes[0]
    store.update_symbol_generated_summary(target.id, "Bridges alpha and gamma.")

    _index, chunks = _embed_file(tmp_path, root, store, "beta.py")

    for_target = [chunk for chunk in chunks if chunk.sourceSymbolId == target.id]
    kinds = {chunk.chunkType for chunk in for_target}
    assert kinds == {"code", "summary"}
    summary_chunk = next(chunk for chunk in for_target if chunk.chunkType == "summary")
    assert "Bridges alpha and gamma." in summary_chunk.content
    assert target.name in summary_chunk.content


def test_a_symbol_without_a_summary_produces_no_summary_chunk(tmp_path):
    """Un-summarized is a normal state: the incremental path embeds even when the LLM was down."""
    root, store, _graph = build_indexed_repo(tmp_path)

    _index, chunks = _embed_file(tmp_path, root, store, "beta.py")

    assert {chunk.chunkType for chunk in chunks} == {"code"}


def test_code_and_summary_chunks_for_one_symbol_do_not_collide(tmp_path):
    """`build_chunk_id` seeds on chunk_type, so the two ids must differ."""
    root, store, _graph = build_indexed_repo(tmp_path)
    bundle = _symbols_of(store, root, "beta.py")
    target = bundle.classes[0]
    store.update_symbol_generated_summary(target.id, "Bridges alpha and gamma.")

    _index, chunks = _embed_file(tmp_path, root, store, "beta.py")

    ids = [chunk.id for chunk in chunks if chunk.sourceSymbolId == target.id]
    assert len(ids) == len(set(ids)) == 2


def test_summary_chunks_are_retrievable_by_chunk_type_filter(tmp_path):
    """The filter existed in `search.py` long before anything emitted a summary chunk."""
    root, store, _graph = build_indexed_repo(tmp_path)
    bundle = _symbols_of(store, root, "beta.py")
    store.update_symbol_generated_summary(bundle.classes[0].id, "Bridges alpha and gamma.")

    index, _chunks = _embed_file(tmp_path, root, store, "beta.py")
    results = index.search("bridges alpha", 5, filters={"chunkType": "summary"})

    assert results
    assert all(result.chunkType == "summary" for result in results)
