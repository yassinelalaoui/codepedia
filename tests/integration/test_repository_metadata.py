from pathlib import Path
from shutil import copytree

from dependency_graph import DependencyGraph
from parser_engine import SourceFile, extract_symbols
from repository_metadata import DependencyEdge, RepositoryMetadataStore, compute_content_hash
from repository_metadata.sqlite_store import stable_repository_id, stable_source_file_id


def _fixture_root() -> Path:
    return Path("tests/integration/fixtures/repository-metadata/sample-repo")


def _copy_fixture_repo(tmp_path: Path) -> Path:
    destination = tmp_path / "sample-repo"
    copytree(_fixture_root(), destination)
    return destination


def _inventories_and_edges(root: Path):
    files = [root / "alpha.py", root / "beta.py", root / "gamma.py"]
    inventories = [extract_symbols(SourceFile(path=path, language="python")) for path in files]
    graph = DependencyGraph.build_from_inventories(inventories, sourceFile=str(root))
    repository_id = stable_repository_id(root)
    edges = [
        DependencyEdge(
            sourceId=edge.sourceId,
            targetId=edge.targetId,
            type=edge.type,
            sourceFileId=stable_source_file_id(repository_id, edge.sourceFile or root),
            metadata=dict(edge.metadata),
        )
        for edge in graph.edges.values()
    ]
    return inventories, edges, graph


def test_repository_can_be_stored_reopened_and_queried(tmp_path):
    root = _copy_fixture_repo(tmp_path)
    inventories, edges, graph = _inventories_and_edges(root)
    store = RepositoryMetadataStore(tmp_path / "repo.sqlite")
    repository = store.ensure_repository(root, detected_languages=("python",))

    for inventory in inventories:
        source_path = Path(inventory.sourceFile)
        store.store_inventory(
            repository_root=root,
            source_file=SourceFile(path=source_path, language="python"),
            inventory=inventory,
            dependency_edges=edges,
            content_hash=compute_content_hash(source_path),
        )

    reopened = store.load_repository(root)
    alpha_bundle = store.load_source_file(repository_root=root, path=root / "alpha.py")

    assert reopened.repository.id == repository.id
    assert len(reopened.files) == 3
    assert len(reopened.graph.edges) == len(graph.edges)
    assert alpha_bundle.module.name == "alpha"
    assert alpha_bundle.functions[0].name == "alpha_entry"
    assert any(edge.type == "import" for edge in alpha_bundle.dependencyEdges)


def test_incremental_update_changes_only_modified_file(tmp_path):
    root = _copy_fixture_repo(tmp_path)
    inventories, edges, _graph = _inventories_and_edges(root)
    store = RepositoryMetadataStore(tmp_path / "repo.sqlite")
    store.ensure_repository(root, detected_languages=("python",))

    alpha_path = root / "alpha.py"
    beta_path = root / "beta.py"
    gamma_path = root / "gamma.py"
    for inventory in inventories:
        source_path = Path(inventory.sourceFile)
        store.store_inventory(
            repository_root=root,
            source_file=SourceFile(path=source_path, language="python"),
            inventory=inventory,
            dependency_edges=edges,
            content_hash=compute_content_hash(source_path),
        )

    alpha_file = root / "alpha.py"
    alpha_file.write_text('"""Alpha module updated."""\n\nfrom beta import beta_helper\n\n\ndef alpha_entry(value: int) -> int:\n    return beta_helper(value) + 1\n', encoding="utf-8")
    changed_inventory = extract_symbols(SourceFile(path=alpha_file, language="python"))
    store.store_inventory(
        repository_root=root,
        source_file=SourceFile(path=alpha_file, language="python"),
        inventory=changed_inventory,
        dependency_edges=edges,
        content_hash=compute_content_hash(alpha_file),
    )

    reopened = store.load_repository(root)
    stored_alpha = store.load_source_file(repository_root=root, path=alpha_file)
    stored_beta = store.load_source_file(repository_root=root, path=beta_path)
    stored_gamma = store.load_source_file(repository_root=root, path=gamma_path)

    assert stored_alpha.file.contentHash == compute_content_hash(alpha_file)
    assert stored_beta.file.contentHash == compute_content_hash(beta_path)
    assert stored_gamma.file.contentHash == compute_content_hash(gamma_path)
    assert stored_beta.file.language == "python"
    assert stored_gamma.file.language == "python"
    assert len(reopened.files) == 3


def test_file_change_detection_uses_content_hash(tmp_path):
    root = _copy_fixture_repo(tmp_path)
    store = RepositoryMetadataStore(tmp_path / "repo.sqlite")
    store.ensure_repository(root, detected_languages=("python",))
    alpha_path = root / "alpha.py"
    inventory = extract_symbols(SourceFile(path=alpha_path, language="python"))
    store.store_inventory(
        repository_root=root,
        source_file=SourceFile(path=alpha_path, language="python"),
        inventory=inventory,
        dependency_edges=(),
        content_hash=compute_content_hash(alpha_path),
    )

    assert store.has_file_changed(repository_root=root, path=alpha_path, current_hash=compute_content_hash(alpha_path)) is False
    assert store.has_file_changed(repository_root=root, path=alpha_path, current_hash="different") is True
