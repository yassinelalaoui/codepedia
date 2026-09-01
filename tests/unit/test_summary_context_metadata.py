"""What the prompt's `Metadata:` block actually carries.

This file exists because nothing covered `build_summary_context`, and that gap
hid a real defect for a long time: `summary_context` imported `Symbol`,
`ModuleSymbol`, `ClassSymbol` and `FunctionSymbol` from `parser_engine`, but a
`SourceFileBundle` carries `repository_metadata.models` symbols. Every
`isinstance()` branch in `_symbol_metadata`, `_collect_direct_callers` and
`_symbol_source_text` was therefore unreachable, and `filePath`, `imports`,
`parentClass`, `parameters`, `returnType` and `owner` silently never reached
the model. The two hierarchies pass identically to `isinstance` only when the
right one is imported, so these assertions are the guard.
"""

from __future__ import annotations

from pathlib import Path
from shutil import copytree

from dependency_graph import DependencyGraph
from parser_engine import SourceFile, extract_symbols
from repository_metadata import RepositoryMetadataStore, compute_content_hash
from repository_metadata.summary_context import _symbol_metadata, build_summary_context


def _indexed_repository(tmp_path: Path):
    root = tmp_path / "sample-repo"
    copytree(Path("tests/integration/fixtures/repository-metadata/sample-repo"), root)
    store = RepositoryMetadataStore(tmp_path / "repo.sqlite")
    store.ensure_repository(root, detected_languages=("python",))
    for name in ("alpha.py", "beta.py", "gamma.py"):
        path = root / name
        source_file = SourceFile(path=path, language="python")
        store.store_inventory(
            repository_root=root,
            source_file=source_file,
            inventory=extract_symbols(source_file),
            content_hash=compute_content_hash(path),
        )
    return root, store, store.load_repository(root)


def _bundle(repository, filename: str):
    return next(bundle for bundle in repository.files if bundle.file.path.endswith(filename))


def test_module_metadata_carries_its_file_path_and_imports(tmp_path):
    _root, _store, repository = _indexed_repository(tmp_path)
    module = _bundle(repository, "alpha.py").module

    metadata = _symbol_metadata(module)

    assert metadata["symbolKind"] == "module"
    assert metadata["filePath"] == module.filePath
    assert isinstance(metadata["imports"], list)


def test_class_metadata_carries_its_parent_class(tmp_path):
    _root, _store, repository = _indexed_repository(tmp_path)
    child = _bundle(repository, "beta.py").classes[0]

    metadata = _symbol_metadata(child)

    assert metadata["symbolKind"] == "class"
    assert "parentClass" in metadata
    assert metadata["parentClass"] == child.parentClass


def test_function_metadata_carries_its_signature(tmp_path):
    _root, _store, repository = _indexed_repository(tmp_path)
    function = _bundle(repository, "alpha.py").functions[0]

    metadata = _symbol_metadata(function)

    assert metadata["symbolKind"] == "function"
    assert metadata["parameters"] == [param.to_dict() for param in function.parameters]
    assert metadata["returnType"] == function.returnType
    assert metadata["owner"] == function.owner


def test_a_module_is_focused_on_its_file_path_not_its_symbol_id(tmp_path):
    """`_collect_direct_callers` looks a module up by path (`files_importing`).
    Given `symbol.id` instead - which is what a dead `isinstance` branch
    produced - it searched the graph for a node that does not exist."""
    root, _store, repository = _indexed_repository(tmp_path)
    bundle = _bundle(repository, "gamma.py")
    inventories = [
        extract_symbols(SourceFile(path=root / name, language="python"))
        for name in ("alpha.py", "beta.py", "gamma.py")
    ]
    graph = DependencyGraph.build_from_inventories(inventories, sourceFile=str(root))

    context = build_summary_context(
        repository_root=root,
        source_file_bundle=bundle,
        symbol=bundle.module,
        dependency_graph=graph,
        source_text="",
        symbol_source_text="",
    )

    assert context.symbolKind == "module"
    assert context.metadata["filePath"] == bundle.module.filePath
    assert any("beta" in caller for caller in context.directCallers)
