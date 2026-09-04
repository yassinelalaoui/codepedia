from __future__ import annotations

import re

from doc_generator import DocGenerator, open_doc_manifest_store

from ._doc_generator_support import build_indexed_repo


def _build_generator(tmp_path, root, store, graph):
    manifest_store = open_doc_manifest_store(tmp_path / "manifest.sqlite")
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=tmp_path / "docs",
        repositoryRoot=root,
    )


def _generate(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    return generator.generateRepositoryDocumentation(root, incremental=False)


def _module_page(doc_set, title):
    return next(page for page in doc_set.pages if page.kind == "module" and page.title == title)


def test_a_symbol_from_another_module_is_linked_to_its_own_page(tmp_path):
    """`beta` declares `class Child(BaseThing)`, and `BaseThing` lives in `gamma`."""
    beta = _module_page(_generate(tmp_path), "beta")

    links = re.findall(
        r'<a class="symbol-ref" href="([^"]+)"><code>([^<]+)</code></a>', beta.renderedHtml
    )
    targets = {name: href for href, name in links}

    assert "BaseThing" in targets
    assert targets["BaseThing"].startswith("gamma-")
    assert "#" in targets["BaseThing"]


def test_cross_reference_links_never_reach_the_markdown_written_to_disk(tmp_path):
    """The .md artifacts stay link-free so they never churn when the index moves.

    This is also what keeps the rendered HTML *derived from* the Markdown rather
    than authored independently (contracts/doc-generator.md).
    """
    doc_set = _generate(tmp_path)

    for page in doc_set.pages:
        assert '<a class="symbol-ref"' not in page.contentMarkdown


def test_every_generated_page_carries_the_toc_mount_container(tmp_path):
    """ui-mount-points.md: containers are present on every page, unconditionally."""
    doc_set = _generate(tmp_path)

    for page in doc_set.pages:
        assert 'id="wiki-toc-root"' in page.renderedHtml


def test_a_module_page_renders_its_section_rail(tmp_path):
    beta = _module_page(_generate(tmp_path), "beta")

    assert re.search(r'class="nav-group page-toc[^"]*"', beta.renderedHtml)
    assert re.search(
        r'class="page-toc-link[^"]*" href="#classes">Classes</a>',
        beta.renderedHtml,
    )


def test_an_inline_reference_is_recorded_as_a_link_in_the_manifest(tmp_path):
    """B3, end to end.

    `beta` mentions `BaseThing`, which lives on `gamma`'s page, and the
    treeprocessor turns that mention into a link. Until this was recorded, only
    the links the generator built itself reached `linkedPageIds`, so removing
    `gamma` left `beta` unregenerated and pointing at a deleted file.
    """
    root, store, graph = build_indexed_repo(tmp_path)
    manifest_store = open_doc_manifest_store(tmp_path / "manifest.sqlite")
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=tmp_path / "docs",
        repositoryRoot=root,
    )
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    beta = _module_page(doc_set, "beta")
    gamma = _module_page(doc_set, "gamma")

    assert gamma.id in beta.referencedPageIds
    entry = manifest_store.load_entry(beta.id)
    assert entry is not None
    assert gamma.id in entry.linkedPageIds
    # The links the generator builds itself are still there.
    assert set(link.toPageId for link in beta.links) <= set(entry.linkedPageIds)
