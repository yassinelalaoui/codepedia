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
