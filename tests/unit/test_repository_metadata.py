from pathlib import Path

import sqlite3

from parser_engine import SourceFile, extract_symbols
from repository_metadata import (
    ClassSymbol,
    DependencyEdge,
    FunctionSymbol,
    ModuleSymbol,
    Parameter,
    Repository,
    RepositoryMetadataStore,
    SourceFile as StoredSourceFile,
    compute_content_hash,
    file_has_changed,
)


def test_content_hash_changes_with_content(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text("print('one')\n", encoding="utf-8")
    first = compute_content_hash(sample)
    sample.write_text("print('two')\n", encoding="utf-8")
    second = compute_content_hash(sample)

    assert first != second
    assert file_has_changed(first, second) is True
    assert file_has_changed(first, first) is False


def test_models_validate_and_serialise():
    repository = Repository(id="repo::1", rootPath="C:/repo", detectedLanguages=("python",), lastIndexedAt="2026-08-11T00:00:00Z")
    file_record = StoredSourceFile(id="file::1", repositoryId=repository.id, path="alpha.py", language="python", contentHash="abc", lastModified="2026-08-11T00:00:00Z")
    module = ModuleSymbol(id="symbol::m", sourceFileId=file_record.id, kind="module", name="alpha", lineStart=1, lineEnd=10, filePath="alpha.py", imports=("from beta import helper",))
    klass = ClassSymbol(id="symbol::c", sourceFileId=file_record.id, kind="class", name="Child", lineStart=2, lineEnd=7, parentClass="Base", methods=("symbol::f",))
    function = FunctionSymbol(id="symbol::f", sourceFileId=file_record.id, kind="function", name="run", lineStart=3, lineEnd=5, parameters=(Parameter(name="x", type="int"),), returnType="int", owner="class")
    edge = DependencyEdge(sourceId=function.id, targetId=klass.id, type="call", sourceFileId=file_record.id)

    assert repository.detectedLanguages == ("python",)
    assert file_record.language == "python"
    assert module.kind == "module"
    assert klass.parentClass == "Base"
    assert function.parameters[0].name == "x"
    assert edge.type == "call"
    assert repository.to_dict()["rootPath"] == "C:/repo"


def test_store_round_trip_with_empty_database(tmp_path):
    store = RepositoryMetadataStore(tmp_path / "repo.sqlite")

    repository = store.ensure_repository(tmp_path / "repo", detected_languages=("python",))
    loaded = store.load_repository_record(tmp_path / "repo")

    assert loaded.id == repository.id
    assert loaded.rootPath == repository.rootPath


def _store_one_file(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "app.py"
    source.write_text("def helper():\n    return 1\n", encoding="utf-8")
    db_path = tmp_path / "meta.sqlite"
    store = RepositoryMetadataStore(db_path)
    store.ensure_repository(root, detected_languages=("python",))
    store.store_inventory(
        repository_root=root,
        source_file=SourceFile(path=source, language="python"),
        inventory=extract_symbols(SourceFile(path=source, language="python")),
        dependency_edges=[],
        content_hash=compute_content_hash(source),
    )
    return root, db_path


def test_an_index_written_under_an_older_id_scheme_is_marked_for_reparse(tmp_path):
    """A changed id derivation has to reach files nobody edits.

    The incremental path only re-parses a file whose content hash moved, so an
    index written before the ids stopped encoding line numbers would keep both
    schemes side by side indefinitely. Blanking the stored hash is the lever the
    watcher's catch-up scan already reads.
    """
    from repository_metadata.sqlite_store import SYMBOL_ID_SCHEME_VERSION, connect

    _root, db_path = _store_one_file(tmp_path)

    raw = sqlite3.connect(db_path)
    try:
        raw.execute("PRAGMA user_version = 1")
    finally:
        raw.close()

    connection = connect(db_path)
    try:
        hashes = [row[0] for row in connection.execute("SELECT content_hash FROM source_files")]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()

    assert hashes == [""]
    assert version == SYMBOL_ID_SCHEME_VERSION


def test_reopening_a_current_index_leaves_its_content_hashes_alone(tmp_path):
    from repository_metadata.sqlite_store import connect

    _root, db_path = _store_one_file(tmp_path)

    connection = connect(db_path)
    try:
        hashes = [row[0] for row in connection.execute("SELECT content_hash FROM source_files")]
    finally:
        connection.close()

    assert hashes and all(value for value in hashes)
