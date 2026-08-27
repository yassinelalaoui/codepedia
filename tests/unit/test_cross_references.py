from __future__ import annotations

import re

from doc_generator.cross_references import (
    build_reference_href,
    build_symbol_lookup,
    resolve_reference,
)
from doc_generator.html_render import render_page_html
from doc_generator.search_index import SearchIndexDocument, SearchIndexEntry


def _fenced_blocks(html: str) -> list[str]:
    """Every <pre>...</pre> region, which is what must never be rewritten."""
    return re.findall(r"<pre.*?</pre>", html, re.S)


def _index(*entries: SearchIndexEntry) -> SearchIndexDocument:
    return SearchIndexDocument(generatedAt="2026-01-01T00:00:00+00:00", entries=entries)


GAMMA_MODULE = SearchIndexEntry(
    name="gamma", kind="module", symbolId="mod-gamma",
    filePath="src/pkg/gamma.py", pageUrl="modules/gamma-1.html",
)
BASE_THING = SearchIndexEntry(
    name="BaseThing", kind="class", symbolId="cls-base",
    filePath="src/pkg/gamma.py", pageUrl="modules/gamma-1.html#cls-base",
)
BASE_THING_RUN = SearchIndexEntry(
    name="BaseThing.run", kind="method", symbolId="fn-run",
    filePath="src/pkg/gamma.py", pageUrl="modules/gamma-1.html#fn-run",
)
CONFIG_IN_A = SearchIndexEntry(
    name="Config", kind="class", symbolId="cls-config-a",
    filePath="src/pkg/a.py", pageUrl="modules/a-1.html#cls-config-a",
)
CONFIG_IN_B = SearchIndexEntry(
    name="Config", kind="class", symbolId="cls-config-b",
    filePath="src/pkg/b.py", pageUrl="modules/b-1.html#cls-config-b",
)

LOOKUP = build_symbol_lookup(
    _index(GAMMA_MODULE, BASE_THING, BASE_THING_RUN, CONFIG_IN_A, CONFIG_IN_B)
)


def test_a_unique_bare_name_resolves_to_its_symbol():
    assert resolve_reference(LOOKUP, "BaseThing") is BASE_THING


def test_a_qualified_class_method_name_resolves_directly():
    assert resolve_reference(LOOKUP, "BaseThing.run") is BASE_THING_RUN


def test_a_file_path_resolves_to_its_module_page():
    assert resolve_reference(LOOKUP, "src/pkg/gamma.py") is GAMMA_MODULE


def test_a_repository_relative_path_resolves_against_a_stored_absolute_path():
    """Summaries write `src/pkg/gamma.py`; the scanner may have stored it absolute."""
    lookup = build_symbol_lookup(
        _index(
            SearchIndexEntry(
                name="gamma", kind="module", symbolId="mod-gamma",
                filePath="C:/work/repo/src/pkg/gamma.py", pageUrl="modules/gamma-1.html",
            )
        )
    )

    assert resolve_reference(lookup, "src/pkg/gamma.py") is not None


def test_the_explicit_path_double_colon_symbol_form_resolves_by_symbol_id():
    assert resolve_reference(LOOKUP, "src/pkg/gamma.py :: cls-base") is BASE_THING


def test_the_explicit_form_falls_back_to_the_module_when_the_symbol_id_is_unknown():
    assert resolve_reference(LOOKUP, "src/pkg/gamma.py :: gone") is GAMMA_MODULE


def test_an_ambiguous_bare_name_is_left_unresolved():
    """A wrong link costs more reader trust than a missing one."""
    assert resolve_reference(LOOKUP, "Config") is None


def test_an_ambiguous_bare_name_resolves_when_the_current_module_claims_it():
    resolved = resolve_reference(LOOKUP, "Config", current_file_path="src/pkg/b.py")

    assert resolved is CONFIG_IN_B


def test_an_unknown_name_is_left_unresolved():
    assert resolve_reference(LOOKUP, "NotARealSymbol") is None


def test_a_multiline_or_oversized_span_is_never_treated_as_a_reference():
    assert resolve_reference(LOOKUP, "BaseThing\nBaseThing") is None
    assert resolve_reference(LOOKUP, "x" * 200) is None


def test_a_target_on_the_current_page_becomes_a_bare_fragment():
    href = build_reference_href(BASE_THING, output_path_html="modules/gamma-1.html")

    assert href == "#cls-base"


def test_a_target_on_another_page_is_linked_relative_to_the_current_one():
    href = build_reference_href(BASE_THING, output_path_html="diagrams/beta-2.html")

    assert href == "../modules/gamma-1.html#cls-base"


def test_inline_code_is_rewritten_but_fenced_blocks_are_left_verbatim():
    markdown_text = (
        "# page\n\n"
        "Inline `BaseThing` and ambiguous `Config`.\n\n"
        "```mermaid\nflowchart LR\n  n0[\"BaseThing\"] --> n1[\"x\"]\n```\n\n"
        "```python\nx = BaseThing()\n```\n"
    )
    kwargs = dict(
        title="page", content_markdown=markdown_text, output_path_html="modules/page.html"
    )

    without = render_page_html(**kwargs)
    with_links = render_page_html(**kwargs, symbol_lookup=LOOKUP)

    assert '<a class="symbol-ref" href="gamma-1.html#cls-base"><code>BaseThing</code></a>' in with_links
    assert "<code>Config</code>" in with_links
    # Every fenced block must survive byte-for-byte: the treeprocessor sees the
    # element tree, so a `<pre><code>` is structurally out of reach.
    assert _fenced_blocks(with_links) == _fenced_blocks(without)
    assert all("symbol-ref" not in block for block in _fenced_blocks(with_links))
