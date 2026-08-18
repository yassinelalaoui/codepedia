from __future__ import annotations

from pathlib import Path

from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, open_doc_manifest_store
from doc_generator.mermaid_diagram import build_use_case_diagram_mermaid_source
from doc_generator.use_case_diagram import Actor, UseCase, UseCaseDiagramSelection
from parser_engine import SourceFile, extract_symbols
from repository_metadata import DependencyEdge, RepositoryMetadataStore, compute_content_hash
from repository_metadata.sqlite_store import stable_repository_id, stable_source_file_id

from ._doc_generator_support import build_indexed_repo


def _build_generator(tmp_path: Path, root: Path, store, graph, *, db_name: str = "repo.sqlite") -> DocGenerator:
    manifest_store = open_doc_manifest_store(tmp_path / db_name)
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=root / "docs",
        repositoryRoot=root,
    )


def _assert_zero_broken_links(manifest_store, repository_id: str) -> None:
    entries = manifest_store.list_entries(repository_id)
    known_page_ids = {entry.pageId for entry in entries}
    for entry in entries:
        for target_page_id in entry.linkedPageIds:
            assert target_page_id in known_page_ids, (
                f"{entry.pageId} links to {target_page_id}, which does not exist in the documentation set"
            )


def _index_repo(tmp_path: Path, root: Path, file_paths: list[Path], db_name: str):
    inventories = [extract_symbols(SourceFile(path=path, language="python")) for path in file_paths]
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
    store = RepositoryMetadataStore(tmp_path / db_name)
    store.ensure_repository(root, detected_languages=("python",))
    for inventory in inventories:
        source_path = Path(inventory.sourceFile)
        store.store_inventory(
            repository_root=root,
            source_file=SourceFile(path=source_path, language="python"),
            inventory=inventory,
            dependency_edges=edges,
            content_hash=compute_content_hash(source_path),
        )
    return store, graph


def _build_cli_and_api_repo(tmp_path: Path):
    """One module with two CLI commands, one module with two API routes."""
    root = tmp_path / "cli-and-api-repo"
    root.mkdir()
    (root / "cli.py").write_text(
        '"""CLI module."""\n\nimport typer\n\napp = typer.Typer()\n\n\n'
        "@app.command()\ndef run_index() -> int:\n    return 1\n\n\n"
        "@app.command()\ndef run_serve() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    (root / "api.py").write_text(
        '"""API module."""\n\nimport fastapi\n\napp = fastapi.FastAPI()\n\n\n'
        '@app.get("/sessions")\ndef get_sessions() -> int:\n    return 1\n\n\n'
        '@app.get("/health")\ndef get_health() -> int:\n    return 1\n',
        encoding="utf-8",
    )
    store, graph = _index_repo(tmp_path, root, [root / "cli.py", root / "api.py"], "cli-and-api-repo.sqlite")
    return root, store, graph


def test_use_case_diagram_shows_distinct_cli_and_api_actors_and_home_page_links_to_it(tmp_path):
    root, store, graph = _build_cli_and_api_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="cli-and-api-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    use_case_page = next(page for page in doc_set.pages if page.kind == "use-case-diagram")
    assert use_case_page.contentMarkdown.count('"CLI"') == 1
    assert use_case_page.contentMarkdown.count('"API"') == 1
    assert "cli.run_index" in use_case_page.contentMarkdown
    assert "api.get_sessions" in use_case_page.contentMarkdown

    home_page = next(page for page in doc_set.pages if page.kind == "home")
    assert use_case_page.outputPathMarkdown.split("/")[-1] in home_page.contentMarkdown

    repository_id = stable_repository_id(root)
    _assert_zero_broken_links(generator.manifestStore, repository_id)


def test_use_case_diagram_shares_one_actor_across_entry_points_of_the_same_kind(tmp_path):
    root, store, graph = _build_cli_and_api_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="cli-and-api-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    use_case_page = next(page for page in doc_set.pages if page.kind == "use-case-diagram")
    # Two CLI commands (run_index, run_serve) and two API routes (get_sessions,
    # get_health) must each connect to one shared actor per kind, not four
    # separate actors.
    assert use_case_page.contentMarkdown.count('(["CLI"])') == 1
    assert use_case_page.contentMarkdown.count('(["API"])') == 1
    assert "cli.run_serve" in use_case_page.contentMarkdown
    assert "api.get_health" in use_case_page.contentMarkdown


def test_plain_function_entry_point_connects_to_generic_fallback_actor(tmp_path):
    """alpha/beta/gamma's entry points (alpha_entry, Child.run, shared_value)
    are plain, undecorated functions - none is CLI/API, so all connect to the
    single generic 'External Caller' actor (FR-004)."""
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    use_case_page = next(page for page in doc_set.pages if page.kind == "use-case-diagram")
    assert '(["External Caller"])' in use_case_page.contentMarkdown
    assert '(["CLI"])' not in use_case_page.contentMarkdown
    assert '(["API"])' not in use_case_page.contentMarkdown
    assert "alpha.alpha_entry" in use_case_page.contentMarkdown


def _build_no_entry_point_repo(tmp_path: Path):
    """a() and b() call each other across modules - both always have a
    caller, so neither qualifies as an entry point (Edge Case)."""
    root = tmp_path / "no-entry-point-repo-usecase"
    root.mkdir()
    (root / "a.py").write_text('"""A module."""\n\nfrom b import b\n\n\ndef a() -> int:\n    return b()\n', encoding="utf-8")
    (root / "b.py").write_text('"""B module."""\n\nfrom a import a\n\n\ndef b() -> int:\n    return a()\n', encoding="utf-8")
    store, graph = _index_repo(tmp_path, root, [root / "a.py", root / "b.py"], "no-entry-point-repo-usecase.sqlite")
    return root, store, graph


def test_repository_with_zero_entry_points_produces_no_use_case_diagram_and_no_broken_links(tmp_path):
    root, store, graph = _build_no_entry_point_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="no-entry-point-repo-usecase.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    assert all(page.kind != "use-case-diagram" for page in doc_set.pages)
    home_page = next(page for page in doc_set.pages if page.kind == "home")
    assert "use-case-overview" not in home_page.contentMarkdown

    repository_id = stable_repository_id(root)
    _assert_zero_broken_links(generator.manifestStore, repository_id)


def test_incremental_regeneration_adds_a_new_use_case_to_the_existing_actor(tmp_path):
    root, store, graph = _build_cli_and_api_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="cli-and-api-repo.sqlite")
    generator.generateRepositoryDocumentation(root, incremental=False)

    api_path = root / "api.py"
    api_path.write_text(
        api_path.read_text(encoding="utf-8") + '\n\n@app.get("/status")\ndef get_status() -> int:\n    return 1\n',
        encoding="utf-8",
    )
    api_inventory = extract_symbols(SourceFile(path=api_path, language="python"))
    graph.ingest_inventory(api_inventory)
    store.store_inventory(
        repository_root=root,
        source_file=SourceFile(path=api_path, language="python"),
        inventory=api_inventory,
        content_hash=compute_content_hash(api_path),
    )

    doc_set = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(api_path)])

    use_case_page = next((page for page in doc_set.pages if page.kind == "use-case-diagram"), None)
    assert use_case_page is not None
    assert "api.get_status" in use_case_page.contentMarkdown
    assert use_case_page.contentMarkdown.count('(["API"])') == 1


def test_use_case_diagram_mermaid_is_well_formed_with_a_sanitized_quote():
    """No supported source language allows a literal `"` inside an
    identifier, so this is exercised at the hand-built-selection level, same
    as 021/022's equivalent tests."""
    selection = UseCaseDiagramSelection(
        actors=(Actor(kind="function", label='External"Caller'),),
        useCases=(UseCase(entryPointStableKey="key1", label='mod.do"Thing', actorKind="function"),),
    )

    result = build_use_case_diagram_mermaid_source(selection)

    assert '"Caller' not in result.sourceText
    assert '"Thing' not in result.sourceText
    assert result.sourceText.startswith("flowchart LR")
    assert result.sourceText.count("[") == result.sourceText.count("]")
    assert result.sourceText.count("(") == result.sourceText.count(")")
