from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))

from _doc_generator_support import build_indexed_repo  # noqa: E402

from doc_generator import DocGenerator, open_doc_manifest_store  # noqa: E402


def test_home_page_presents_architecture_summary(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    docs_root = tmp_path / "docs"
    manifest_store = open_doc_manifest_store(tmp_path / "manifest.sqlite")
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=docs_root,
        repositoryRoot=root,
    )

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)
    home_page = next(page for page in doc_set.pages if page.kind == "home")

    assert "Architecture overview" in home_page.contentMarkdown
    assert "3 documented modules" in home_page.contentMarkdown
    # The architecture table now counts modules per derived section rather than
    # per raw directory name, and each row links to that section's own page.
    assert "| Section | Modules |" in home_page.contentMarkdown
    assert "sections/" in home_page.contentMarkdown
    assert "## Sections" in home_page.contentMarkdown
    # The existing flat module list must still be present alongside the summary.
    assert "## Modules" in home_page.contentMarkdown
