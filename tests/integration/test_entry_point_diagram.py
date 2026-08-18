from __future__ import annotations

from pathlib import Path

from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, open_doc_manifest_store
from doc_generator.entry_point_diagram import EntryPoint, build_entry_point_call_sequence
from doc_generator.mermaid_diagram import build_sequence_diagram_mermaid_source
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


def test_alpha_entry_sequence_diagram_shows_beta_helper_with_correct_module_and_module_page_links_to_it(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    alpha_entry_page = next(page for page in doc_set.pages if page.kind == "sequence-diagram" and page.title.startswith("alpha_entry"))
    assert "sequenceDiagram" in alpha_entry_page.contentMarkdown
    assert "alpha.alpha_entry" in alpha_entry_page.contentMarkdown
    assert "beta.beta_helper" in alpha_entry_page.contentMarkdown
    assert "beta_helper()" in alpha_entry_page.contentMarkdown

    alpha_module_page = next(page for page in doc_set.pages if page.kind == "module" and page.title == "alpha")
    assert alpha_entry_page.outputPathMarkdown.split("/")[-1] in alpha_module_page.contentMarkdown

    # beta_helper is called by both alpha_entry and Child.run, so it does not
    # itself qualify as an entry point (Research Decision 2) - no page, no link.
    assert all(not page.title.startswith("beta_helper") for page in doc_set.pages if page.kind == "sequence-diagram")

    repository_id = stable_repository_id(root)
    _assert_zero_broken_links(generator.manifestStore, repository_id)


def test_leaf_entry_point_renders_minimal_one_participant_diagram(tmp_path):
    """gamma.py's shared_value() is never called by anything and calls
    nothing itself (Acceptance Scenario 4, SC-004)."""
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    shared_value_page = next(page for page in doc_set.pages if page.kind == "sequence-diagram" and page.title.startswith("shared_value"))
    mermaid_block = shared_value_page.contentMarkdown.split("```mermaid")[1].split("```")[0]
    assert mermaid_block.count("participant ") == 1
    assert "->>" not in mermaid_block


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


def _build_no_entry_point_repo(tmp_path: Path):
    """a() and b() call each other across modules - both always have a
    caller, so neither qualifies as an entry point (Edge Case 5)."""
    root = tmp_path / "no-entry-point-repo"
    root.mkdir()
    (root / "a.py").write_text('"""A module."""\n\nfrom b import b\n\n\ndef a() -> int:\n    return b()\n', encoding="utf-8")
    (root / "b.py").write_text('"""B module."""\n\nfrom a import a\n\n\ndef b() -> int:\n    return a()\n', encoding="utf-8")
    store, graph = _index_repo(tmp_path, root, [root / "a.py", root / "b.py"], "no-entry-point-repo.sqlite")
    return root, store, graph


def test_repository_with_zero_entry_points_produces_zero_sequence_diagram_pages_and_no_broken_links(tmp_path):
    root, store, graph = _build_no_entry_point_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="no-entry-point-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    assert all(page.kind != "sequence-diagram" for page in doc_set.pages)
    for page in doc_set.pages:
        assert "sequence:" not in page.contentMarkdown

    repository_id = stable_repository_id(root)
    _assert_zero_broken_links(generator.manifestStore, repository_id)


def _build_cli_command_repo(tmp_path: Path):
    """A Typer-style `@app.command()`-decorated function that something else
    in the fixture also calls - still an entry point (FR-002)."""
    root = tmp_path / "cli-command-repo"
    root.mkdir()
    (root / "cli.py").write_text(
        '"""CLI module."""\n\nimport typer\n\napp = typer.Typer()\n\n\n'
        '@app.command()\ndef run_index() -> int:\n    return 1\n\n\n'
        'def caller() -> int:\n    return run_index()\n',
        encoding="utf-8",
    )
    store, graph = _index_repo(tmp_path, root, [root / "cli.py"], "cli-command-repo.sqlite")
    return root, store, graph


def test_cli_decorated_function_is_an_entry_point_even_when_called_by_something_else(tmp_path):
    root, store, graph = _build_cli_command_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="cli-command-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    sequence_pages = [page for page in doc_set.pages if page.kind == "sequence-diagram"]
    assert any(page.title.startswith("run_index") for page in sequence_pages)


def test_incremental_regeneration_propagates_a_change_two_hops_down_the_call_chain(tmp_path):
    """A change to beta_helper (one hop below alpha_entry) must still
    regenerate alpha_entry's sequence diagram (SC-005, research.md
    Decision 8)."""
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    generator.generateRepositoryDocumentation(root, incremental=False)

    beta_path = root / "beta.py"
    beta_path.write_text(
        beta_path.read_text(encoding="utf-8").replace("return number + 1", "return number + 2"),
        encoding="utf-8",
    )
    beta_inventory = extract_symbols(SourceFile(path=beta_path, language="python"))
    graph.ingest_inventory(beta_inventory)
    store.store_inventory(
        repository_root=root,
        source_file=SourceFile(path=beta_path, language="python"),
        inventory=beta_inventory,
        content_hash=compute_content_hash(beta_path),
    )

    doc_set = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(beta_path)])

    regenerated_titles = {page.title for page in doc_set.pages if page.kind == "sequence-diagram"}
    assert any(title.startswith("alpha_entry") for title in regenerated_titles)


def test_sequence_diagram_mermaid_is_well_formed_with_a_sanitized_semicolon_and_quote():
    """No supported source language allows a literal `;`/`"` inside an
    identifier, so this is exercised at the hand-built-selection level, same
    as 021's equivalent test for the class diagram."""
    entry_point = EntryPoint(
        symbolId="ep1",
        stableKey="file1::module::entry",
        name='Foo;Bar"Baz',
        moduleKey="file1",
        moduleName="mod",
        className=None,
        kind="function",
    )
    graph = DependencyGraph(id="g1", sourceFile="repo")
    from dependency_graph import DependencyNode

    graph.add_node(DependencyNode(id="ep1", kind="symbol", name=entry_point.name, sourceFile="mod.py", symbolType="function"))
    graph.add_node(DependencyNode(id="c1", kind="symbol", name='do;It"Now', sourceFile="mod.py", symbolType="function"))
    graph.addEdge("ep1", "c1", "call")

    selection = build_entry_point_call_sequence(graph, entry_point)
    result = build_sequence_diagram_mermaid_source(selection)

    assert ";" not in result.sourceText
    assert '"' not in result.sourceText
    assert result.sourceText.startswith("sequenceDiagram")
