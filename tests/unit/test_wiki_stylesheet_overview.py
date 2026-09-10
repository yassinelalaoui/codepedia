"""The built wiki stylesheet carries the Overview's two layout rules (spec 038).

Both are CSS-only behaviours no rendering test can see, and both regressed or
were introduced by the Overview's new shape, so they are pinned against the
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


def test_consecutive_generated_paragraphs_share_one_badge(wiki_css):
    """The narrative lead is several `.ai-generated` paragraphs in a row; they
    must read as one marked block with one badge (research Decision 10)."""
    assert ".ai-generated+.ai-generated:before{content:none}" in wiki_css


def test_generated_prose_wraps_long_code_spans(wiki_css):
    """The lead cites full file paths; a Java package path has no break
    opportunity and ran out of the marked block at narrow widths."""
    rule = wiki_css.split(".ai-generated{", 1)[1].split("}", 1)[0]
    assert "overflow-wrap:anywhere" in rule


def test_a_row_holding_only_its_title_link_is_not_styled_as_the_trailing_link(wiki_css):
    """The Features list is titles only (FR-012a), so each row's one link is both
    first and last child. Selecting the trailing "(dependencies)" link by
    `:last-child` alone pushed every feature title right and greyed it."""
    assert "a:last-child:not(:first-child){" in wiki_css
    assert "ul:has(>li.module-list) a:last-child{" not in wiki_css
