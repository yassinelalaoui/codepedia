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
