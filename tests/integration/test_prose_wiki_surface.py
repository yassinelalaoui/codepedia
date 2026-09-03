"""What the wiki shows for a documentation file, as opposed to a code file.

`parser_engine` maps a Markdown file onto the same module/class/function symbol
types the code uses - that mapping is what lets prose reuse the whole pipeline
with no new plumbing, and it is also why every consumer that renders a symbol's
*kind* or *name* has to be told the difference. These tests pin the three
consumers that were publishing headings as classes: the search index, the
sidebar, and the home page's counters.
"""

from __future__ import annotations

import json
from pathlib import Path

from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, open_doc_manifest_store
from parser_engine import SourceFile, extract_symbols
from repository_metadata import RepositoryMetadataStore, compute_content_hash

CODE = '''\
"""Alpha module."""


class Engine:
    """An engine."""

    def start(self):
        """Start it."""
        return True


def helper():
    """A helper."""
    return 1
'''

PROSE = """\
# Architecture Overview

What this project is.

## Storage

How storage works.

### Indexes

How indexes work.
"""


def _build_repo(tmp_path: Path) -> tuple[Path, RepositoryMetadataStore, DependencyGraph]:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    files = {
        root / "alpha.py": ("python", CODE),
        root / "docs" / "architecture.md": ("Markdown", PROSE),
    }
    inventories = []
    for path, (language, text) in files.items():
        path.write_text(text, encoding="utf-8")
        inventories.append((path, language, extract_symbols(SourceFile(path=path, language=language))))

    graph = DependencyGraph.build_from_inventories([item[2] for item in inventories], sourceFile=str(root))
    store = RepositoryMetadataStore(tmp_path / "repo.sqlite")
    store.ensure_repository(root, detected_languages=("python", "Markdown"))
    for path, language, inventory in inventories:
        store.store_inventory(
            repository_root=root,
            source_file=SourceFile(path=path, language=language),
            inventory=inventory,
            content_hash=compute_content_hash(path),
        )
    return root, store, graph


def _generate(tmp_path: Path):
    root, store, graph = _build_repo(tmp_path)
    docs_root = tmp_path / "out"
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=open_doc_manifest_store(tmp_path / "manifest.sqlite"),
        outputRoot=docs_root,
        repositoryRoot=root,
    )
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)
    return root, docs_root, doc_set


def _search_entries(docs_root: Path) -> list[dict]:
    payload = json.loads((docs_root / "assets" / "search-index.json").read_text(encoding="utf-8"))
    return payload["entries"]


def test_documentation_is_published_as_document_and_section_not_class(tmp_path):
    _root, docs_root, _doc_set = _generate(tmp_path)
    entries = _search_entries(docs_root)

    prose = {entry["name"]: entry["kind"] for entry in entries if entry["filePath"].endswith(".md")}
    assert prose["docs/architecture"] == "document"
    assert prose["Storage"] == "section"
    assert "Storage \u203a Indexes" in prose and prose["Storage \u203a Indexes"] == "section"
    assert "class" not in set(prose.values())


def test_code_keeps_its_own_kinds(tmp_path):
    _root, docs_root, _doc_set = _generate(tmp_path)
    entries = _search_entries(docs_root)

    code = {entry["name"]: entry["kind"] for entry in entries if entry["filePath"].endswith(".py")}
    assert code["alpha"] == "module"
    assert code["Engine"] == "class"
    assert code["Engine.start"] == "method"
    assert code["helper"] == "function"


def test_a_prose_page_is_labelled_by_its_path_not_its_stem(tmp_path):
    # Documentation filenames repeat by convention: a repository of
    # `specs/001-x/spec.md`, `specs/002-y/spec.md` would produce entries all
    # reading "spec", whose URLs differ but whose labels do not.
    #
    # This used to also assert the label appeared in every page's sidebar. It no
    # longer can, and that is by design rather than a regression: feature
    # navigation removed the module tree from the sidebar (033 FR-024). The
    # label still does the work it was introduced for - it names the page and it
    # names the search result - so the assertion moved to where the label now
    # lives rather than being dropped.
    _root, docs_root, doc_set = _generate(tmp_path)

    prose_page = next(page for page in doc_set.pages if page.title.endswith("architecture"))
    assert prose_page.title == "docs/architecture"
    assert any(page.title == "alpha" for page in doc_set.pages), "code keeps its stem"

    assert "docs/architecture" in prose_page.renderedHtml, "the page names itself by its path"

    index = json.loads((docs_root / "assets" / "search-index.json").read_text(encoding="utf-8"))
    document_names = {entry["name"] for entry in index["entries"] if entry["kind"] == "document"}
    assert "docs/architecture" in document_names, (
        "search is now one of a document's two doors, so its label has to be right there"
    )


def test_prose_pages_do_not_inflate_the_home_page_counters(tmp_path):
    # `## Storage` is stored as a ClassSymbol and `### Indexes` as a
    # FunctionSymbol, so counting them here would answer "how many classes does
    # this repository have?" with three times the truth.
    _root, docs_root, _doc_set = _generate(tmp_path)
    home = (docs_root / "index.md").read_text(encoding="utf-8")

    assert "1 documented module, 1 class, and 1 top-level function" in home
    assert "1 documentation page" in home


def test_the_prose_page_url_is_unchanged_by_the_new_label(tmp_path):
    # The label is display-only: slugs, page ids and anchors still derive from
    # `module.name`, so relabelling costs no reindex and breaks no stored link.
    _root, _docs_root, doc_set = _generate(tmp_path)

    prose_page = next(page for page in doc_set.pages if page.title == "docs/architecture")
    assert prose_page.outputPathHtml.startswith("modules/architecture-")
