from __future__ import annotations

from doc_generator.html_render import _build_page_toc, render_page_html

MODULE_PAGE = """# beta

## Summary

Prose.

## Classes

### Child {: #cls-child }

#### Child.run(self) {: #fn-run }

## Functions

### beta_helper(value) {: #fn-helper }

## Related modules
"""


def _toc_of(markdown_text: str) -> list[dict]:
    """Render a page and hand back the section rail it produced."""
    import markdown as markdown_lib

    from doc_generator.html_render import _MARKDOWN_EXTENSIONS

    md = markdown_lib.Markdown(extensions=list(_MARKDOWN_EXTENSIONS))
    md.convert(markdown_text)
    return _build_page_toc(md.toc_tokens)


def test_page_toc_keeps_h2_sections_in_document_order():
    sections = _toc_of(MODULE_PAGE)

    assert [section["name"] for section in sections] == [
        "Summary",
        "Classes",
        "Functions",
        "Related modules",
    ]


def test_page_toc_nests_h3_symbols_under_their_section():
    sections = _toc_of(MODULE_PAGE)
    by_name = {section["name"]: section for section in sections}

    assert [child["name"] for child in by_name["Classes"]["children"]] == ["Child"]
    assert [child["name"] for child in by_name["Functions"]["children"]] == ["beta_helper(value)"]
    assert by_name["Summary"]["children"] == []


def test_page_toc_excludes_the_h4_method_level():
    """H4 is the per-method level; including it would swamp a large module."""
    names = {
        child["name"]
        for section in _toc_of(MODULE_PAGE)
        for child in section["children"]
    }

    assert "Child.run(self)" not in names


def test_page_toc_uses_the_explicit_attr_list_anchor_when_one_is_pinned():
    by_name = {section["name"]: section for section in _toc_of(MODULE_PAGE)}

    assert by_name["Classes"]["children"][0]["id"] == "cls-child"
    assert by_name["Summary"]["id"] == "summary"


def test_page_toc_is_empty_for_a_page_with_no_sections():
    assert _toc_of("# lonely title\n\nJust prose, no sections.\n") == []


def test_rendered_page_omits_the_rail_entirely_when_there_are_no_sections():
    html = render_page_html(
        title="lonely",
        content_markdown="# lonely\n\nJust prose.\n",
        output_path_html="modules/lonely.html",
    )

    assert 'class="nav-group page-toc"' not in html
    # The mount container stays on every page so the bundle never has to
    # special-case which kind of page it is running on.
    assert 'id="wiki-toc-root"' in html


def test_rendered_page_links_each_rail_entry_to_its_heading_anchor():
    html = render_page_html(
        title="beta",
        content_markdown=MODULE_PAGE,
        output_path_html="modules/beta.html",
    )

    assert '<a class="page-toc-link" href="#summary">Summary</a>' in html
    assert '<a class="page-toc-link child" href="#cls-child">Child</a>' in html


def test_a_signature_heading_is_not_double_escaped_in_the_rail():
    """`toc_tokens` names arrive with entities; the layout autoescapes on top."""
    html = render_page_html(
        title="m",
        content_markdown="# m\n\n## Functions\n\n### f(x) -> int {: #fx }\n",
        output_path_html="modules/m.html",
    )

    assert '<a class="page-toc-link child" href="#fx">f(x) -&gt; int</a>' in html
    assert "-&amp;gt;" not in html
