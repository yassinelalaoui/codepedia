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
