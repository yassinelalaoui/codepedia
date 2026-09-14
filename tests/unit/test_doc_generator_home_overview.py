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
    # 038 User Story 2: the table says what each subsystem is for and where to
    # start, not how many modules it has, and it replaces the Features list.
    # No planner here, so no description is shown and the column is unlabelled.
    assert "| Feature | Modules |" not in home_page.contentMarkdown
    assert "| Subsystem | Responsibility | Start with |" in home_page.contentMarkdown
    assert "features/" in home_page.contentMarkdown
    assert "## Features" not in home_page.contentMarkdown
    # The existing flat module list must still be present alongside the summary.
    assert "## Modules" in home_page.contentMarkdown
    # 038: the run timestamp left the page's content (it made reruns differ),
    # and the class diagram is reached by its link rather than drawn inline.
    assert "Last indexed" not in home_page.contentMarkdown
    assert "```mermaid" not in home_page.contentMarkdown
    # With no narrator the page opens straight onto the repository facts.
    assert home_page.contentMarkdown.split("\n", 2)[2].lstrip().startswith("- Repository root:")
