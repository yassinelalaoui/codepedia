from __future__ import annotations

import sqlite3

from vector_index import CodeChunk, SearchQuery, VectorIndex, build_code_chunk, build_code_chunks, rank_entries
from vector_index import storage
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


def test_rank_entries_excludes_mismatched_dimensionality_instead_of_raising():
    # research.md §8: a repository with mixed-model vectors (spec User Story
    # 4) used to make VectorIndex.search() crash outright with ValueError -
    # rank_entries now silently excludes an incompatible entry instead.
    query = [1.0, 0.0, 0.0]
    matching = CodeChunk(id="chunk-a", content="alpha", embedding=[1.0, 0.0, 0.0], sourceSymbolId="symbol-a")
    mismatched = CodeChunk(id="chunk-b", content="beta", embedding=[1.0, 0.0], sourceSymbolId="symbol-b")

    results = rank_entries(query, [matching, mismatched], k=5)

    assert [result.chunkId for result in results] == ["chunk-a"]


def test_rank_entries_excludes_entries_with_a_different_embedding_model_id():
    query = encode_text("database helper")
    same_model = CodeChunk(
        id="chunk-a", content="database helper", embedding=query, sourceSymbolId="symbol-a",
        embeddingModelId="openai:text-embedding-3-small",
    )
    other_model = CodeChunk(
        id="chunk-b", content="database helper", embedding=query, sourceSymbolId="symbol-b",
        embeddingModelId="local:nomic-embed-text",
    )

    results = rank_entries(query, [same_model, other_model], k=5, filters={"embeddingModelId": "openai:text-embedding-3-small"})

    assert [result.chunkId for result in results] == ["chunk-a"]


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


def test_an_index_survives_the_directory_rename_that_publishes_it(tmp_path):
    """`codepedia index` builds into `<state>.staging-<pid>` and renames it
    into place on success.

    The index id is derived from the repository root *and* the metadata file's
    path, so that rename used to change it: the chunks stayed in the file under
    the staging-derived id while opening the same file at its final path minted
    a second, empty record. Every indexing run silently published an index that
    reported zero chunks, so chat retrieval found nothing.
    """
    root = tmp_path / "repo"
    root.mkdir()
    staging_dir = tmp_path / "state.staging-1234"
    staging_dir.mkdir()

    index = VectorIndex(root, staging_dir / "vector-metadata.sqlite")
    index.addChunk(
        build_code_chunk(
            "def alpha():\n    return 1",
            source_symbol_id="symbol-alpha",
            source_file_path="alpha.py",
            embedding_engine=FakeEmbeddingEngine(),
        )
    )
    assert len(index) == 1
    index.close()

    final_dir = tmp_path / "state"
    staging_dir.replace(final_dir)

    republished = VectorIndex(root, final_dir / "vector-metadata.sqlite")
    try:
        assert len(republished) == 1, "the published index must still see the chunks it stored"
    finally:
        republished.close()


def test_two_repositories_in_one_metadata_file_keep_separate_indexes(tmp_path):
    """Adoption is per repository root, so it must not merge two of them."""
    metadata_path = tmp_path / "shared.sqlite"
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    engine = FakeEmbeddingEngine()

    first = VectorIndex(first_root, metadata_path)
    first.addChunk(
        build_code_chunk("a = 1", source_symbol_id="s1", source_file_path="a.py", embedding_engine=engine)
    )
    second = VectorIndex(second_root, metadata_path)
    second.addChunk(
        build_code_chunk("b = 2", source_symbol_id="s2", source_file_path="b.py", embedding_engine=engine)
    )

    try:
        assert len(first) == 1
        assert len(second) == 1
        assert first.record.id != second.record.id
    finally:
        first.close()
        second.close()


# ---------------------------------------------------------------------------
# The write path, counted in commits rather than seconds.
#
# P1 - one transaction per chunk - survived three separate analyses of this
# repository because nothing here ever looked at the write path, and the one
# performance test that exists compares wall-clock seconds, which says nothing
# about why a run is slow. A commit is an fsync; counting commits is the
# measurement that fails when the defect comes back, on any machine and under
# any disk.
# ---------------------------------------------------------------------------


class CommitCounter:
    """Counts the COMMITs a connection actually issues.

    Via `set_trace_callback`, because `with connection:` commits below the
    Python API - subclassing `Connection.commit` sees nothing. The callback
    receives the statements sqlite really prepares, implicit `BEGIN`/`COMMIT`
    included, so this counts fsyncs rather than intentions and needs no seam in
    production code: every function in `storage` is handed its connection.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.count = 0
        connection.set_trace_callback(self._seen)

    def _seen(self, statement: str) -> None:
        if statement.strip().upper().startswith("COMMIT"):
            self.count += 1

    def reset(self) -> None:
        self.count = 0


def _counting_index(tmp_path, name: str = "vectors.sqlite"):
    connection = storage.connect(tmp_path / name)
    record = storage.ensure_index_record(
        connection, repository_root=tmp_path, metadata_path=tmp_path / name
    )
    return connection, record.id, CommitCounter(connection)


def _chunks(count: int, *, source_file_path: str = "src/app.py"):
    return [
        CodeChunk(
            id=f"chunk-{index}",
            content=f"def f{index}(): return {index}",
            embedding=(float(index), 1.0, 0.5),
            sourceSymbolId=f"symbol-{index}",
            sourceFilePath=source_file_path,
            embeddingModelId="test:model",
        )
        for index in range(count)
    ]


def test_re_embedding_a_file_costs_exactly_one_commit(tmp_path):
    connection, index_id, commits = _counting_index(tmp_path)
    try:
        storage.replace_chunks_for_file(
            connection, index_id=index_id, source_file_path="src/app.py", chunks=_chunks(50)
        )
        assert commits.count == 1
    finally:
        connection.close()


def test_the_write_path_does_not_commit_once_per_chunk(tmp_path):
    """The regression guard: the cost of writing a file must not scale with it."""
    connection, index_id, commits = _counting_index(tmp_path)
    try:
        storage.replace_chunks_for_file(
            connection, index_id=index_id, source_file_path="a.py", chunks=_chunks(5, source_file_path="a.py")
        )
        few = commits.count
        storage.replace_chunks_for_file(
            connection, index_id=index_id, source_file_path="b.py", chunks=_chunks(200, source_file_path="b.py")
        )
        many = commits.count - few

        assert few == many == 1, "forty times the chunks must still be one fsync"
    finally:
        connection.close()


def test_a_batch_of_chunks_is_one_commit(tmp_path):
    connection, index_id, commits = _counting_index(tmp_path)
    try:
        storage.upsert_chunks(connection, index_id=index_id, chunks=_chunks(30))
        assert commits.count == 1
    finally:
        connection.close()


def test_an_index_entry_carries_no_second_copy_of_its_vector(tmp_path):
    """9.4: `VectorMatrix` holds the vectors, so the entries must not.

    Two representations of every embedding is what made the memory figure in
    `pyproject.toml` untrue - the matrix was allocated *on top of* the Python
    floats rather than instead of them.
    """
    engine = FakeEmbeddingEngine()
    index = VectorIndex(tmp_path / "repo", tmp_path / "vectors.sqlite", embedding_engine=engine)
    try:
        index.addChunk(
            build_code_chunk("a = 1", source_symbol_id="s1", source_file_path="a.py", embedding_engine=engine)
        )
        index.refresh()

        entry = index.entries[0]
        assert entry.vector == (), "a loaded entry must not hold its own vector"
        assert entry.dimensionality > 0, "it still knows its own length"
        assert index.search("a = 1", k=1), "and search still scores it, from the matrix"
    finally:
        index.close()


def test_deleting_a_file_leaves_no_lifecycle_rows_behind(tmp_path):
    """`chunk_lifecycle` used to keep a "removed" tombstone per deleted chunk,
    forever. Nothing ever read them - `load_lifecycle_state` is reachable only
    through `VectorIndex.get_lifecycle`, which has no caller - so they were one
    INSERT per deleted chunk on every incremental pass, in a table that then
    grew for the life of the server."""
    connection, index_id, _ = _counting_index(tmp_path)
    try:
        storage.replace_chunks_for_file(
            connection, index_id=index_id, source_file_path="src/app.py", chunks=_chunks(20)
        )
        assert len(storage.load_lifecycle_state(connection, source_file_path="src/app.py")) == 20

        storage.delete_chunks_for_file(connection, index_id=index_id, source_file_path="src/app.py")

        assert storage.load_lifecycle_state(connection) == {}
    finally:
        connection.close()


def test_re_embedding_a_file_does_not_grow_the_lifecycle_table(tmp_path):
    """What is in the table is what is live: rewriting the same file must leave
    one row per current chunk, not one per chunk ever written."""
    connection, index_id, _ = _counting_index(tmp_path)
    try:
        for _ in range(5):
            storage.replace_chunks_for_file(
                connection, index_id=index_id, source_file_path="src/app.py", chunks=_chunks(10)
            )

        states = storage.load_lifecycle_state(connection)
        assert len(states) == 10
        assert set(states.values()) == {"added"}
    finally:
        connection.close()
