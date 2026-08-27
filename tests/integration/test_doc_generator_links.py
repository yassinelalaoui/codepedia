from __future__ import annotations

from pathlib import Path

from doc_generator import DocGenerator, open_doc_manifest_store
from repository_metadata import CodeSummaryPipeline
from repository_metadata.sqlite_store import stable_repository_id

from ._doc_generator_support import RecordingLLMEngine, build_indexed_repo, wrap_llm


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
    CodeSummaryPipeline(metadataStore=store, dependencyGraph=graph, llmEngine=wrap_llm(engine)).summarizeRepository(
        root, incremental=False
    )

    generator = _build_generator(tmp_path, root, store, graph)
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    # 1 home + 3 modules + 3 diagrams + 1 class diagram + 3 entry-point sequence
    # diagrams (alpha_entry, Child.run, shared_value - beta_helper is called by
    # both alpha_entry and Child.run, so it does not itself qualify) + 1
    # repository-wide use-case diagram + 1 diagrams-index page + 1 section page
    # (the fixture repository is flat, so its three modules form a single
    # section rooted at the repository directory).
    assert len(doc_set.pages) == 14
    section_pages = [page for page in doc_set.pages if page.kind == "section"]
    assert len(section_pages) == 1
    section_markdown = section_pages[0].contentMarkdown
    assert "## Modules in this section" in section_markdown
    for module_name in ("alpha", "beta", "gamma"):
        assert f"[{module_name}](" in section_markdown
    home_page = next(page for page in doc_set.pages if page.kind == "home")
    assert "alpha" in home_page.contentMarkdown
    assert "beta" in home_page.contentMarkdown
    assert "gamma" in home_page.contentMarkdown
    assert "diagrams/class-overview.md" in home_page.contentMarkdown
    assert "diagrams/use-case-overview.md" in home_page.contentMarkdown

    class_diagram_page = next(page for page in doc_set.pages if page.kind == "class-diagram")
    assert "Child" in class_diagram_page.contentMarkdown
    assert "BaseThing" in class_diagram_page.contentMarkdown
    assert "<|--" in class_diagram_page.contentMarkdown

    use_case_diagram_page = next(page for page in doc_set.pages if page.kind == "use-case-diagram")
    assert "flowchart LR" in use_case_diagram_page.contentMarkdown
    assert "External Caller" in use_case_diagram_page.contentMarkdown

    diagrams_index_page = next(page for page in doc_set.pages if page.kind == "diagrams-index")
    assert "Class diagram" in diagrams_index_page.contentMarkdown
    assert "Use-case diagram" in diagrams_index_page.contentMarkdown
    assert "Entry point sequence diagrams" in diagrams_index_page.contentMarkdown
    assert "Module dependency diagrams" in diagrams_index_page.contentMarkdown

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
    CodeSummaryPipeline(metadataStore=store, dependencyGraph=graph, llmEngine=wrap_llm(engine)).summarizeRepository(
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
    CodeSummaryPipeline(metadataStore=store, dependencyGraph=graph, llmEngine=wrap_llm(engine)).summarizeSourceFile(
        root, beta_path
    )

    doc_set = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(beta_path)])

    # beta.py contains a class (Child), so this change also touches the
    # repository-wide class diagram, which always refreshes on any qualifying
    # change (research.md Decision 3) - not just the module page. It also
    # touches every entry-point sequence diagram whose recorded call sequence
    # includes a symbol from beta.py: Child.run (its own body changed) and
    # alpha_entry (its sequence includes beta_helper, which beta.py's edit
    # also touches, per research.md Decision 8). The repository-wide use-case
    # diagram refreshes too, for the same "any qualifying change" reason as
    # the class diagram (research.md Decision 6 of 023).
    #
    # beta.py's owning section page also refreshes: unlike a module page, a
    # section page embeds its members' docstrings and summaries, so a member's
    # change really does make it stale. Its *set* of members is unchanged, so
    # the navigation tree keeps its shape and nothing else is dragged in.
    regenerated_kinds = {page.kind for page in doc_set.pages}
    assert regenerated_kinds == {"module", "section", "class-diagram", "sequence-diagram", "use-case-diagram"}
    assert len(doc_set.pages) == 6
    module_page = next(page for page in doc_set.pages if page.kind == "module")
    assert module_page.title == "beta"
    sequence_diagram_pages = [page for page in doc_set.pages if page.kind == "sequence-diagram"]
    assert {page.title.split(" ")[0] for page in sequence_diagram_pages} == {"run", "alpha_entry"}

    after_mtimes = {path: path.stat().st_mtime_ns for path in output_root.rglob("*") if path.is_file()}
    changed_paths = {path for path in before_mtimes if before_mtimes[path] != after_mtimes.get(path)}
    class_diagram_page = next(page for page in doc_set.pages if page.kind == "class-diagram")
    use_case_diagram_page = next(page for page in doc_set.pages if page.kind == "use-case-diagram")
    section_page = next(page for page in doc_set.pages if page.kind == "section")
    expected_changed_paths = {
        output_root / "modules" / Path(module_page.outputPathMarkdown).name,
        output_root / "modules" / Path(module_page.outputPathHtml).name,
        output_root / Path(section_page.outputPathMarkdown),
        output_root / Path(section_page.outputPathHtml),
        output_root / Path(class_diagram_page.outputPathMarkdown),
        output_root / Path(class_diagram_page.outputPathHtml),
        output_root / Path(use_case_diagram_page.outputPathMarkdown),
        output_root / Path(use_case_diagram_page.outputPathHtml),
    }
    for sequence_diagram_page in sequence_diagram_pages:
        expected_changed_paths.add(output_root / Path(sequence_diagram_page.outputPathMarkdown))
        expected_changed_paths.add(output_root / Path(sequence_diagram_page.outputPathHtml))
    assert changed_paths == expected_changed_paths

    repository_id = stable_repository_id(root)
    _assert_zero_broken_links(generator.manifestStore, repository_id)
