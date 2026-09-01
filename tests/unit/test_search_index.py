from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))

from _doc_generator_support import build_indexed_repo  # noqa: E402

from doc_generator import DocGenerator, open_doc_manifest_store  # noqa: E402

_HEADING_ID_PATTERN = re.compile(r'id="([^"]+)"')


def test_build_search_index_anchors_match_rendered_heading_ids(tmp_path):
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

    search_index = _read_search_index(docs_root)
    non_module_entries = [entry for entry in search_index["entries"] if entry["kind"] != "module"]
    assert non_module_entries, "expected at least one class/method/function entry"

    module_pages = {page.outputPathHtml: page for page in doc_set.pages if page.kind == "module"}

    for entry in non_module_entries:
        page_path, _, anchor = entry["pageUrl"].partition("#")
        assert anchor, f"expected an anchor for a non-module entry: {entry}"
        assert page_path in module_pages, f"entry points at an unresolvable page: {entry}"

        rendered_html = module_pages[page_path].renderedHtml
        rendered_ids = set(_HEADING_ID_PATTERN.findall(rendered_html))
        assert anchor in rendered_ids, f"anchor {anchor!r} not found among rendered heading ids for {page_path}"


def test_build_search_index_module_entries_have_no_anchor(tmp_path):
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
    generator.generateRepositoryDocumentation(root, incremental=False)

    search_index = _read_search_index(docs_root)
    module_entries = [entry for entry in search_index["entries"] if entry["kind"] == "module"]
    assert module_entries
    for entry in module_entries:
        assert "#" not in entry["pageUrl"]
        assert (docs_root / entry["pageUrl"]).exists()


def _read_search_index(docs_root: Path) -> dict:
    import json

    return json.loads((docs_root / "assets" / "search-index.json").read_text(encoding="utf-8"))


def test_search_index_anchors_are_readable(tmp_path):
    """The point of 1.5: an anchor a reader can recognise in the URL bar.

    `#alpha-entry` rather than `#function_9c1f...`. The opaque id is still on
    the heading, in `data-symbol-id`, where a machine reads it.
    """
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

    entries = {entry["name"]: entry for entry in _read_search_index(docs_root)["entries"]}
    assert entries["alpha_entry"]["pageUrl"].endswith("#alpha-entry")

    module_pages = {page.outputPathHtml: page for page in doc_set.pages if page.kind == "module"}
    page_path, _, _anchor = entries["alpha_entry"]["pageUrl"].partition("#")
    rendered = module_pages[page_path].renderedHtml
    assert f'data-symbol-id="{entries["alpha_entry"]["symbolId"]}"' in rendered


def test_symbol_anchors_do_not_collide_with_the_pages_own_headings(tmp_path):
    """A README section named "Summary" must not take the page's Summary anchor.

    python-markdown keeps an explicit `attr_list` id verbatim, so the collision
    would not break the symbol's own anchor - it would silently rename the
    template's heading to `summary_1` instead.
    """
    from doc_generator import links

    class _Module:
        name = "readme"

    class _Section:
        def __init__(self, identifier, name):
            self.id = identifier
            self.name = name
            self.methods = ()

    class _Bundle:
        module = _Module()
        classes = (_Section("class_1", "Summary"), _Section("class_2", "Summary"))
        functions = ()

    anchors = links.build_symbol_anchors(_Bundle())
    assert anchors["class_1"] == "summary-2"
    assert anchors["class_2"] == "summary-3"
