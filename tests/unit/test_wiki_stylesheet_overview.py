"""The built wiki stylesheet carries the Overview's layout rules (spec 038).

Each is a CSS-only behaviour no rendering test can see, and each regressed or
was introduced by the Overview's new shape, so they are pinned against the
built asset that every generated wiki copies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

WIKI_CSS = Path(__file__).resolve().parents[2] / "src" / "doc_generator" / "assets" / "wiki-ui.css"


@pytest.fixture(scope="module")
def wiki_css() -> str:
    if not WIKI_CSS.exists():
        pytest.skip("wiki bundle not built")
    return WIKI_CSS.read_text(encoding="utf-8", errors="replace")


def test_generated_prose_is_styled_like_the_rest_of_the_page(wiki_css):
    """Summaries and the Overview's prose are plain paragraphs: no highlight,
    no border, no label set them apart from the text around them."""
    assert "ai-generated" not in wiki_css
    assert "--generated-" not in wiki_css


def test_prose_wraps_long_code_spans(wiki_css):
    """The lead cites full file paths; a Java package path has no break
    opportunity and ran out of the content column at narrow widths."""
    rule = wiki_css.split(".content-col p{", 1)[1].split("}", 1)[0]
    assert "overflow-wrap:anywhere" in rule


def test_a_row_holding_only_its_title_link_is_not_styled_as_the_trailing_link(wiki_css):
    """The Features list is titles only (FR-012a), so each row's one link is both
    first and last child. Selecting the trailing "(dependencies)" link by
    `:last-child` alone pushed every feature title right and greyed it."""
    assert "a:last-child:not(:first-child){" in wiki_css
    assert "ul:has(>li.module-list) a:last-child{" not in wiki_css


def test_the_subsystems_responsibility_column_uses_the_ui_font(wiki_css):
    """A sentence in the monospace face ran the table tall at narrow widths.
    Scoped through the counts paragraph before it, so no other table changes
    (research Decision 19)."""
    assert ".content-col .architecture-counts+table td:nth-child(2){font-family:var(--wiki-font-ui)}" in wiki_css
