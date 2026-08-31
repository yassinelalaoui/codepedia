"""Raw HTML carried through Markdown must not become executable.

`layout.html.jinja` inserts the rendered Markdown with `| safe`, and that
Markdown is built from docstrings read out of the documented repository and
from LLM-written summaries. These tests pin both halves: the attack shapes are
neutralized, and the markup a real README legitimately uses still renders.
"""

from __future__ import annotations

from doc_generator.html_render import render_page_html
from doc_generator.html_sanitizer import is_safe_url, sanitize_fragment


def _render(markdown_text: str) -> str:
    return render_page_html(
        title="t", content_markdown=markdown_text, output_path_html="modules/m.html"
    )


def test_a_script_tag_in_a_docstring_is_not_executable():
    html = _render("# M\n\n<script>alert(document.domain)</script>\n")
    assert "<script>alert(document.domain)</script>" not in html
    assert "&lt;script&gt;alert(document.domain)&lt;/script&gt;" in html


def test_an_event_handler_attribute_is_dropped():
    html = _render('# M\n\nText <img src="x" onerror="steal()"> end\n')
    assert "onerror" not in html
    assert "steal()" not in html


def test_a_javascript_url_is_dropped_but_the_link_text_survives():
    html = _render('# M\n\n<a href="javascript:go()">click</a>\n')
    assert "javascript:" not in html
    assert "click" in html


def test_an_obfuscated_javascript_url_is_still_dropped():
    assert is_safe_url("java\tscript:alert(1)") is False
    assert is_safe_url("JaVaScRiPt:alert(1)") is False
    assert is_safe_url("  javascript:alert(1)") is False


def test_an_entity_encoded_javascript_url_is_dropped_end_to_end():
    # The entity is resolved by HTMLParser, so this only holds through the full
    # render path - `is_safe_url` alone never sees the encoded form.
    html = _render('# M\n\n<a href="javascript&#58;go()">click</a>\n')
    assert "javascript" not in html.lower().split("<footer")[0].replace("javascript:void", "")
    assert "click" in html


def test_relative_and_http_urls_are_allowed():
    assert is_safe_url("../modules/other.html#anchor") is True
    assert is_safe_url("https://example.com/x.svg") is True
    assert is_safe_url("mailto:someone@example.com") is True
    assert is_safe_url("data:text/html;base64,PHNjcmlwdD4=") is False


def test_a_readme_badge_still_renders():
    html = _render('# M\n\n<img src="https://img.shields.io/badge/build-ok.svg" alt="build">\n')
    assert 'src="https://img.shields.io/badge/build-ok.svg"' in html
    assert 'alt="build"' in html


def test_a_details_block_still_renders():
    html = _render("# M\n\n<details>\n<summary>More</summary>\n\nHidden prose.\n\n</details>\n")
    assert "<details>" in html
    assert "<summary>More</summary>" in html


def test_inline_emphasis_written_as_raw_html_survives():
    # Inline tags reach the stash unbalanced - `<em>` and `</em>` arrive as
    # separate fragments - so this is the case a balancing sanitizer would break.
    html = _render("# M\n\nSome <em>emphasis</em> here.\n")
    assert "<em>emphasis</em>" in html


def test_an_unbalanced_fragment_is_sanitized_on_its_own():
    assert sanitize_fragment("<em>") == "<em>"
    assert sanitize_fragment("</em>") == "</em>"
    assert sanitize_fragment("<script>") == "&lt;script&gt;"
    assert sanitize_fragment("</script>") == "&lt;/script&gt;"


def test_generated_markup_is_never_touched():
    # A markdown-authored link and code span produce no stash entry at all, so
    # sanitizing cannot reach them.
    html = _render("# M\n\n[link](https://example.com) and `inline code`\n")
    assert '<a href="https://example.com">link</a>' in html
    assert "<code>inline code</code>" in html


def test_a_mermaid_fence_is_left_intact():
    html = _render("# M\n\n```mermaid\nflowchart LR\n  A --> B\n```\n")
    assert '<pre class="mermaid">' in html
    assert "A --&gt; B" in html or "A --> B" in html


# The tests above all write raw HTML. Two Markdown constructions become HTML
# without ever passing through the stash - `attr_list`'s `{: ... }` and a link's
# own URL - and the tests below pin those, plus the generated markup the second
# pass must leave alone.


def test_an_event_handler_written_as_an_attr_list_is_dropped():
    html = _render('# M\n\n## Section {: onmouseover="steal()" #keep }\n')
    assert "onmouseover" not in html
    assert "steal()" not in html
    # The anchor `attr_list` is enabled for in the first place still lands.
    assert 'id="keep"' in html


def test_an_event_handler_on_a_paragraph_attr_list_is_dropped():
    html = _render('# M\n\nParagraph.\n{: onclick="steal()" }\n')
    assert "onclick" not in html
    assert "<p>Paragraph.</p>" in html


def test_a_style_written_as_an_attr_list_is_dropped():
    html = _render('# M\n\nParagraph.\n{: style="background:url(http://x/y)" }\n')
    assert "background:url" not in html


def test_a_javascript_url_in_a_markdown_link_is_dropped_but_the_text_survives():
    html = _render("# M\n\n[click](javascript:steal())\n")
    assert "javascript:steal" not in html
    assert "click" in html


def test_a_javascript_url_in_a_markdown_image_is_dropped_but_the_alt_survives():
    html = _render("# M\n\n![shot](javascript:steal())\n")
    assert "javascript:steal" not in html
    assert 'alt="shot"' in html


def test_generated_table_alignment_survives_the_tree_pass():
    # `tables` renders column alignment as an inline style - the one attribute
    # python-markdown generates that no allowlist above covers.
    html = _render("# M\n\n| a | b |\n|:--|--:|\n| 1 | 2 |\n")
    assert 'style="text-align: left;"' in html
    assert 'style="text-align: right;"' in html


def test_a_style_smuggled_onto_a_table_cell_is_still_dropped():
    html = _render('# M\n\nParagraph.\n{: style="text-align: left; background:url(http://x/y)" }\n')
    assert "background:url" not in html


def test_symbol_anchors_and_template_classes_survive():
    html = _render("# M\n\n## Klass {: #klass-id }\n\nSome prose.\n{: .ai-generated }\n")
    assert 'id="klass-id"' in html
    assert 'class="ai-generated"' in html


def test_a_mermaid_fence_still_reaches_its_pre_class():
    # The `class="language-mermaid"` the fence produces is what
    # `_MERMAID_FENCE_PATTERN` keys on downstream; dropping it in the tree pass
    # would silently stop every diagram from rendering.
    html = _render("# M\n\n```mermaid\nflowchart LR\n  A --> B\n```\n")
    assert '<pre class="mermaid">' in html


def test_ordinary_markdown_links_and_images_are_untouched():
    html = _render("# M\n\n[other](other.md) and ![badge](https://example.com/b.svg)\n")
    assert 'href="other.html"' in html  # rewritten .md -> .html, still present
    assert 'src="https://example.com/b.svg"' in html
