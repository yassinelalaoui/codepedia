from __future__ import annotations

import re

from doc_generator import DocGenerator, open_doc_manifest_store

from ._doc_generator_support import build_indexed_repo

_CLICK_PATTERN = re.compile(r'click (\S+) href "([^"]+)"')


def _build_generator(tmp_path, root, store, graph):
    manifest_store = open_doc_manifest_store(tmp_path / "manifest.sqlite")
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=tmp_path / "docs",
        repositoryRoot=root,
    )


def test_diagram_page_has_working_click_navigation_and_ui_mount_points(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    diagram_page = next(page for page in doc_set.pages if page.kind == "diagram")

    # The click directive lives in the Mermaid source embedded in the raw
    # Markdown (013's own test pattern); the rendered HTML escapes its quotes
    # as part of ordinary fenced-code rendering, so it isn't regex-matchable
    # there the same way.
    clicks = _CLICK_PATTERN.findall(diagram_page.contentMarkdown)
    assert clicks, "expected at least one working Mermaid click directive"

    html = diagram_page.renderedHtml
    assert 'id="wiki-search-root"' in html
    assert 'id="wiki-chat-root"' in html


def test_module_page_has_ui_mount_points_when_opened_directly(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    module_page = next(page for page in doc_set.pages if page.kind == "module")
    html = module_page.renderedHtml

    assert 'id="wiki-search-root"' in html
    assert 'id="wiki-chat-root"' in html
    assert "wiki-ui.js" in html
    assert "wiki-ui.css" in html


def test_no_cdn_reference_and_classic_ui_script_tag(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    for page in doc_set.pages:
        assert "http://" not in page.renderedHtml
        assert "https://" not in page.renderedHtml
        script_tags = re.findall(r"<script[^>]*>", page.renderedHtml)
        ui_script_tags = [tag for tag in script_tags if "wiki-ui.js" in tag]
        assert ui_script_tags, f"expected a wiki-ui script tag on {page.id}"
        for tag in ui_script_tags:
            assert 'type="module"' not in tag, f"wiki-ui script tag must not be a module script: {tag}"

    docs_root = tmp_path / "docs"
    assert (docs_root / "assets" / "wiki-ui.js").exists()
    assert (docs_root / "assets" / "wiki-ui.css").exists()
    assert (docs_root / "assets" / "search-index.json").exists()


def test_wiki_ui_assets_are_not_rewritten_when_unchanged(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    generator.generateRepositoryDocumentation(root, incremental=False)

    docs_root = tmp_path / "docs"
    js_path = docs_root / "assets" / "wiki-ui.js"
    css_path = docs_root / "assets" / "wiki-ui.css"
    search_index_path = docs_root / "assets" / "search-index.json"
    first_mtimes = (js_path.stat().st_mtime_ns, css_path.stat().st_mtime_ns, search_index_path.stat().st_mtime_ns)

    generator.generateRepositoryDocumentation(root, incremental=False)
    second_mtimes = (js_path.stat().st_mtime_ns, css_path.stat().st_mtime_ns, search_index_path.stat().st_mtime_ns)

    assert first_mtimes == second_mtimes, "unchanged wiki-ui assets and search index should not be rewritten"


def test_mermaid_bootstrap_awaits_run_instead_of_start_on_load(tmp_path):
    """The layout must hand the enhancer a completion signal, not auto-render.

    `startOnLoad: true` draws on DOMContentLoaded and marks every element
    `data-processed`, so a later `mermaid.run()` would find nothing and never
    resolve - and `wiki-ui.js` would have no moment at which the SVG is known to
    exist. `suppressErrors` keeps one unparseable diagram from aborting the
    batch, and the whole block stays inline so a failed bundle load costs the
    zoom rather than the diagram.
    """
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    html = next(page for page in doc_set.pages if page.kind == "module").renderedHtml

    assert "startOnLoad: false" in html
    assert "startOnLoad: true" not in html
    assert "mermaid.run(" in html
    assert "suppressErrors" in html
    assert "wiki:mermaid-rendered" in html
