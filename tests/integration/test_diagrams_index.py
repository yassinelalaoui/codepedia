from __future__ import annotations

import re
from pathlib import Path

from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, open_doc_manifest_store
from parser_engine import SourceFile, extract_symbols
from repository_metadata import RepositoryMetadataStore, compute_content_hash

from ._doc_generator_support import build_indexed_repo, index_repo


def _build_generator(tmp_path: Path, root: Path, store, graph, *, db_name: str = "repo.sqlite") -> DocGenerator:
    manifest_store = open_doc_manifest_store(tmp_path / db_name)
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=root / "docs",
        repositoryRoot=root,
    )


def test_diagrams_index_lists_every_diagram_category_and_no_module_pages(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    diagrams_page = next(page for page in doc_set.pages if page.kind == "diagrams-index")
    assert "## Class diagram" in diagrams_page.contentMarkdown
    assert "## Use-case diagram" in diagrams_page.contentMarkdown
    assert "## Entry point sequence diagrams" in diagrams_page.contentMarkdown
    assert "## Module dependency diagrams" in diagrams_page.contentMarkdown

    kind_by_page_id = {page.id: page.kind for page in doc_set.pages}
    linked_kinds = [kind_by_page_id[link.toPageId] for link in diagrams_page.links]
    assert linked_kinds.count("class-diagram") == 1
    assert linked_kinds.count("use-case-diagram") == 1
    assert linked_kinds.count("sequence-diagram") == 3  # alpha_entry, Child.run, shared_value
    assert linked_kinds.count("diagram") == 3  # one dependency diagram per module (alpha, beta, gamma)
    assert "module" not in linked_kinds


def test_diagrams_link_present_and_resolvable_from_every_page_kind(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    kinds_seen = set()
    for page in doc_set.pages:
        kinds_seen.add(page.kind)
        # Compared with whitespace collapsed: the nav link's label and its
        # closing tag sit on separate template lines, which says nothing about
        # whether the link is present.
        compact_html = re.sub(r"\s+", "", page.renderedHtml)
        assert "Diagrams</a>" in compact_html, f"no Diagrams nav link on {page.id} ({page.kind})"
        assert "diagrams-index.html" in page.renderedHtml, f"Diagrams nav link doesn't target diagrams-index.html on {page.id}"

    assert kinds_seen == {
        "home",
        "module",
        "section",
        "diagram",
        "class-diagram",
        "sequence-diagram",
        "use-case-diagram",
        "diagrams-index",
    }


def _build_no_class_no_entry_point_repo(tmp_path: Path):
    """a() and b() call each other across modules - no classes, and neither
    function qualifies as an entry point (always has a caller)."""
    root = tmp_path / "no-class-no-entry-point-repo"
    root.mkdir()
    (root / "a.py").write_text('"""A module."""\n\nfrom b import b\n\n\ndef a() -> int:\n    return b()\n', encoding="utf-8")
    (root / "b.py").write_text('"""B module."""\n\nfrom a import a\n\n\ndef b() -> int:\n    return a()\n', encoding="utf-8")
    store, graph = index_repo(tmp_path, root, [root / "a.py", root / "b.py"], "no-class-no-entry-point-repo.sqlite")
    return root, store, graph


def test_diagrams_index_omits_class_and_use_case_sections_when_neither_exists(tmp_path):
    root, store, graph = _build_no_class_no_entry_point_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="no-class-no-entry-point-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    diagrams_page = next(page for page in doc_set.pages if page.kind == "diagrams-index")
    assert "## Class diagram" not in diagrams_page.contentMarkdown
    assert "## Use-case diagram" not in diagrams_page.contentMarkdown
    assert "## Entry point sequence diagrams" not in diagrams_page.contentMarkdown
    assert "## Module dependency diagrams" in diagrams_page.contentMarkdown


def _build_zero_module_repo(tmp_path: Path):
    root = tmp_path / "zero-module-repo"
    root.mkdir()
    store = RepositoryMetadataStore(tmp_path / "zero-module-repo.sqlite")
    store.ensure_repository(root, detected_languages=())
    graph = DependencyGraph(id="empty-graph", sourceFile=str(root))
    return root, store, graph


def test_diagrams_index_shows_no_diagrams_yet_message_when_repository_is_empty(tmp_path):
    root, store, graph = _build_zero_module_repo(tmp_path)
    manifest_store = open_doc_manifest_store(tmp_path / "zero-module-repo-manifest.sqlite")
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=root / "docs",
        repositoryRoot=root,
    )

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    diagrams_page = next(page for page in doc_set.pages if page.kind == "diagrams-index")
    assert "No diagrams yet" in diagrams_page.contentMarkdown
    assert (root / "docs" / diagrams_page.outputPathMarkdown).exists()
    assert (root / "docs" / diagrams_page.outputPathHtml).exists()


def _build_single_module_repo(tmp_path: Path, *, content: str):
    root = tmp_path / "single-module-repo"
    root.mkdir()
    (root / "main.py").write_text(content, encoding="utf-8")
    store, graph = index_repo(tmp_path, root, [root / "main.py"], "single-module-repo.sqlite")
    return root, store, graph


_ONE_CLASS_ONE_ENTRY_POINT = '"""Main module."""\n\n\nclass OnlyClass:\n    pass\n\n\ndef entry_fn() -> int:\n    return 1\n'
_NO_CLASS_ONE_ENTRY_POINT = '"""Main module."""\n\n\ndef entry_fn() -> int:\n    return 1\n'
_NO_CLASS_TWO_ENTRY_POINTS = (
    '"""Main module."""\n\n\ndef entry_fn() -> int:\n    return 1\n\n\ndef entry_fn2() -> int:\n    return 2\n'
)
_NO_CLASS_NO_ENTRY_POINT = '"""Main module."""\n'


def _reindex_main(root: Path, store, graph, content: str) -> None:
    main_path = root / "main.py"
    main_path.write_text(content, encoding="utf-8")
    inventory = extract_symbols(SourceFile(path=main_path, language="python"))
    graph.ingest_inventory(inventory)
    store.store_inventory(
        repository_root=root,
        source_file=SourceFile(path=main_path, language="python"),
        inventory=inventory,
        content_hash=compute_content_hash(main_path),
    )


def test_incremental_regeneration_covers_all_four_diagrams_index_trigger_branches(tmp_path):
    root, store, graph = _build_single_module_repo(tmp_path, content=_ONE_CLASS_ONE_ENTRY_POINT)
    generator = _build_generator(tmp_path, root, store, graph, db_name="single-module-repo.sqlite")
    generator.generateRepositoryDocumentation(root, incremental=False)

    # (a) Module-page-set branch: add a second, empty module.
    helper_path = root / "helper.py"
    helper_path.write_text('"""Helper module."""\n', encoding="utf-8")
    helper_inventory = extract_symbols(SourceFile(path=helper_path, language="python"))
    graph.ingest_inventory(helper_inventory)
    store.store_inventory(
        repository_root=root,
        source_file=SourceFile(path=helper_path, language="python"),
        inventory=helper_inventory,
        content_hash=compute_content_hash(helper_path),
    )
    doc_set_a = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(helper_path)])
    diagrams_page_a = next((page for page in doc_set_a.pages if page.kind == "diagrams-index"), None)
    assert diagrams_page_a is not None, "diagrams-index page must regenerate when the module set changes"
    assert "helper dependencies" in diagrams_page_a.contentMarkdown

    # (b) Class-diagram-existence branch: remove the fixture's only class.
    _reindex_main(root, store, graph, _NO_CLASS_ONE_ENTRY_POINT)
    doc_set_b = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(root / "main.py")])
    diagrams_page_b = next((page for page in doc_set_b.pages if page.kind == "diagrams-index"), None)
    assert diagrams_page_b is not None, "diagrams-index page must regenerate when class-diagram existence changes"
    assert "## Class diagram" not in diagrams_page_b.contentMarkdown

    # (c) Sequence-diagram-page-set branch: add a second entry point.
    _reindex_main(root, store, graph, _NO_CLASS_TWO_ENTRY_POINTS)
    doc_set_c = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(root / "main.py")])
    diagrams_page_c = next((page for page in doc_set_c.pages if page.kind == "diagrams-index"), None)
    assert diagrams_page_c is not None, "diagrams-index page must regenerate when the sequence-diagram set changes"
    sequence_pages_c = [page for page in doc_set_c.pages if page.kind == "sequence-diagram"]
    assert {page.title.split(" ")[0] for page in sequence_pages_c} >= {"entry_fn2"}

    # (d) Use-case-diagram-existence branch: remove every remaining entry point.
    _reindex_main(root, store, graph, _NO_CLASS_NO_ENTRY_POINT)
    doc_set_d = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(root / "main.py")])
    diagrams_page_d = next((page for page in doc_set_d.pages if page.kind == "diagrams-index"), None)
    assert diagrams_page_d is not None, "diagrams-index page must regenerate when use-case-diagram existence changes"
    assert "## Use-case diagram" not in diagrams_page_d.contentMarkdown
    assert "## Entry point sequence diagrams" not in diagrams_page_d.contentMarkdown
