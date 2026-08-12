from __future__ import annotations

from pathlib import Path

from doc_generator import DocGenerator, open_doc_manifest_store
from repository_metadata import CodeSummaryPipeline
from repository_metadata.sqlite_store import stable_repository_id

from ._doc_generator_support import RecordingLLMEngine, build_indexed_repo


def _assert_zero_broken_links(manifest_store, repository_id: str) -> None:
    entries = manifest_store.list_entries(repository_id)
    known_page_ids = {entry.pageId for entry in entries}
    assert known_page_ids, "expected at least one generated page in the manifest"
    for entry in entries:
        for target_page_id in entry.linkedPageIds:
            assert target_page_id in known_page_ids, (
                f"{entry.pageId} links to {target_page_id}, which does not exist in the documentation set"
            )


def _build_generator(tmp_path: Path, root: Path, store, graph) -> DocGenerator:
    manifest_store = open_doc_manifest_store(tmp_path / "repo.sqlite")
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=root / "docs",
        repositoryRoot=root,
    )


def test_full_generation_produces_accurate_pages_with_zero_broken_links(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    engine = RecordingLLMEngine()
    CodeSummaryPipeline(metadataStore=store, dependencyGraph=graph, llmEngine=engine).summarizeRepository(
        root, incremental=False
    )

    generator = _build_generator(tmp_path, root, store, graph)
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    assert len(doc_set.pages) == 7  # 1 home + 3 modules + 3 diagrams
    home_page = next(page for page in doc_set.pages if page.kind == "home")
    assert "alpha" in home_page.contentMarkdown
    assert "beta" in home_page.contentMarkdown
    assert "gamma" in home_page.contentMarkdown

    alpha_page = next(page for page in doc_set.pages if page.kind == "module" and page.title == "alpha")
    assert "alpha_entry" in alpha_page.contentMarkdown
    assert "alpha_entry summary" in alpha_page.contentMarkdown

    beta_page = next(page for page in doc_set.pages if page.kind == "module" and page.title == "beta")
    assert "beta summary" in beta_page.contentMarkdown
    assert "run summary" in beta_page.contentMarkdown
    assert "beta_helper summary" in beta_page.contentMarkdown
    assert "Child" in beta_page.contentMarkdown

    alpha_diagram_page = next(
        page for page in doc_set.pages if page.kind == "diagram" and page.title.startswith("alpha")
    )
    assert any(link.label == "beta" for link in alpha_diagram_page.links)
    assert "import" in alpha_diagram_page.contentMarkdown

    repository_id = stable_repository_id(root)
    _assert_zero_broken_links(generator.manifestStore, repository_id)

    for page in doc_set.pages:
        assert (root / "docs" / page.outputPathMarkdown).exists()
        assert (root / "docs" / page.outputPathHtml).exists()


def test_incremental_regeneration_touches_only_impacted_pages_and_keeps_links_valid(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    engine = RecordingLLMEngine()
    CodeSummaryPipeline(metadataStore=store, dependencyGraph=graph, llmEngine=engine).summarizeRepository(
        root, incremental=False
    )

    generator = _build_generator(tmp_path, root, store, graph)
    generator.generateRepositoryDocumentation(root, incremental=False)

    output_root = root / "docs"
    before_mtimes = {path: path.stat().st_mtime_ns for path in output_root.rglob("*") if path.is_file()}

    # Change beta.py's function body (not its imports), then re-index it.
    beta_path = root / "beta.py"
    beta_path.write_text(
        beta_path.read_text(encoding="utf-8").replace("return number + 1", "return number + 2"),
        encoding="utf-8",
    )
    from parser_engine import SourceFile, extract_symbols
    from repository_metadata import compute_content_hash

    beta_inventory = extract_symbols(SourceFile(path=beta_path, language="python"))
    graph.ingest_inventory(beta_inventory)
    store.store_inventory(
        repository_root=root,
        source_file=SourceFile(path=beta_path, language="python"),
        inventory=beta_inventory,
        content_hash=compute_content_hash(beta_path),
    )
    CodeSummaryPipeline(metadataStore=store, dependencyGraph=graph, llmEngine=engine).summarizeSourceFile(
        root, beta_path
    )

    doc_set = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(beta_path)])

    regenerated_kinds = {page.kind for page in doc_set.pages}
    assert regenerated_kinds == {"module"}
    assert len(doc_set.pages) == 1
    assert doc_set.pages[0].title == "beta"

    after_mtimes = {path: path.stat().st_mtime_ns for path in output_root.rglob("*") if path.is_file()}
    changed_paths = {path for path in before_mtimes if before_mtimes[path] != after_mtimes.get(path)}
    assert changed_paths == {
        output_root / "modules" / Path(doc_set.pages[0].outputPathMarkdown).name,
        output_root / "modules" / Path(doc_set.pages[0].outputPathHtml).name,
    }

    repository_id = stable_repository_id(root)
    _assert_zero_broken_links(generator.manifestStore, repository_id)
