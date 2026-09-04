"""Brand mark and tab icon in the generated wiki (036 spec FR-014..FR-021).

The visual questions these cannot answer - that the mark renders at 24 px, and
that the artwork is unmodified to the eye - are settled by measurement and
review instead (quickstart.md §5).
"""

from __future__ import annotations

import re
from pathlib import Path

from doc_generator.html_render import render_page_html
from doc_generator.manifest_store import DocPageManifestStore
from doc_generator.writer import (
    FAVICON_OUTPUT_PATH,
    FAVICON_SOURCE_PATH,
    DocumentationWriter,
)

BRAND_SOURCE_DIR = Path(__file__).resolve().parents[2] / "docs" / "brand"

PAGE_KINDS = (
    "index.html",
    "modules/example.html",
    "diagrams/example-diagram.html",
)

SIMPLE_PAGE = "# title\n\nSome prose.\n"


def _render(output_path_html: str) -> str:
    return render_page_html(
        title="fixture",
        content_markdown=SIMPLE_PAGE,
        output_path_html=output_path_html,
        repository_id="repo::/tmp/alpha",
    )


def _brand_slot(html: str) -> str:
    match = re.search(r'<span class="brand-mark.*?</span>', html, re.S)
    assert match is not None, "no brand slot in the rendered page"
    return match.group(0)


# --------------------------------------------------------------- tab icon


def test_every_page_kind_declares_a_tab_icon():
    for output_path_html in PAGE_KINDS:
        assert re.search(r'<link rel="icon" href="[^"]+">', _render(output_path_html)), output_path_html


def test_the_tab_icon_href_is_relative_to_the_page():
    """A diagram page sits one directory deeper, so an href that works at the
    root and nowhere else is the failure mode worth guarding."""
    assert 'href="assets/favicon.ico"' in _render("index.html")
    assert 'href="../assets/favicon.ico"' in _render("modules/example.html")


def test_the_favicon_is_copied_into_the_wiki_byte_for_byte(tmp_path):
    writer = DocumentationWriter(
        outputRoot=tmp_path,
        manifestStore=DocPageManifestStore(db_path=tmp_path / "manifest.sqlite"),
        repositoryId="repo::/tmp/alpha",
    )
    writer.ensure_wiki_ui_assets()

    written = tmp_path / FAVICON_OUTPUT_PATH
    assert written.exists()
    assert written.read_bytes() == FAVICON_SOURCE_PATH.read_bytes()


def test_the_bundled_favicon_matches_the_brand_kit():
    """The copy under assets/ is the one that ships; docs/brand/ is where it is
    edited. A drift between them means wikis carry a stale icon."""
    assert FAVICON_SOURCE_PATH.read_bytes() == (BRAND_SOURCE_DIR / "favicon.ico").read_bytes()


# --------------------------------------------------------------- self-containment


def test_no_generated_page_references_the_brand_kit_directory():
    """A wiki must stay complete when copied away from this repository."""
    for output_path_html in PAGE_KINDS:
        html = _render(output_path_html)
        assert "docs/brand" not in html, output_path_html
        assert "docs\\brand" not in html, output_path_html


def test_no_generated_page_makes_an_absolute_or_remote_reference():
    for output_path_html in PAGE_KINDS:
        html = _render(output_path_html)
        for attribute in re.findall(r'(?:href|src)="([^"]+)"', html):
            assert not attribute.startswith("http://"), (output_path_html, attribute)
            assert not attribute.startswith("https://"), (output_path_html, attribute)
            assert not attribute.startswith("//"), (output_path_html, attribute)


# --------------------------------------------------------------- the mark


def test_the_placeholder_is_gone():
    html = _render("index.html")
    assert ">CP</span>" not in html


def test_both_variants_are_inlined_on_every_page_kind():
    for output_path_html in PAGE_KINDS:
        slot = _brand_slot(_render(output_path_html))
        assert 'data-brand-variant="light"' in slot, output_path_html
        assert 'data-brand-variant="dark"' in slot, output_path_html


def test_the_marks_are_inline_svg_not_an_image_reference():
    """An <img> cannot respond to a data-theme attribute on an ancestor, and
    would be a runtime fetch besides."""
    slot = _brand_slot(_render("index.html"))
    assert "<svg" in slot
    assert "<img" not in slot


def test_the_brand_slot_is_hidden_from_assistive_technology():
    """The slot sits beside a visible "codepedia" wordmark; announcing the
    graphic too would say the name twice (FR-019)."""
    slot = _brand_slot(_render("index.html"))
    assert 'aria-hidden="true"' in slot


def test_the_inlined_marks_carry_no_competing_accessible_name():
    slot = _brand_slot(_render("index.html"))
    assert "role=" not in slot
    assert "aria-label" not in slot
    assert "<title>" not in slot


def test_the_visible_wordmark_still_carries_the_name():
    assert ">codepedia</span>" in _render("index.html")


def test_the_published_fills_are_unmodified():
    """The brand README forbids recolouring the lens; the two-tone contrast is
    what keeps the mark readable at 24 px."""
    slot = _brand_slot(_render("index.html"))
    for colour in ("#14274A", "#FFFFFF", "#3F73BC", "#8FB8EA"):
        assert colour in slot, colour


def test_the_mark_carries_no_shadow_gradient_or_outline():
    slot = _brand_slot(_render("index.html"))
    for forbidden in ("filter", "<linearGradient", "<radialGradient", "drop-shadow"):
        assert forbidden not in slot, forbidden


def test_the_slot_is_at_least_the_brand_minimum():
    """24 px is the policy floor for the full mark - below it the magnifier
    handle disappears. `size-6` is Tailwind's 1.5rem, i.e. 24 px."""
    slot = _brand_slot(_render("index.html"))
    assert "size-6" in slot
    assert "size-5" not in slot


def test_the_brand_hook_class_stays_first():
    """Tests and CSS query `.brand-mark`; utilities go after it."""
    match = re.search(r'<span class="([^"]+)"', _brand_slot(_render("index.html")))
    assert match is not None
    assert match.group(1).split()[0] == "brand-mark"


def test_the_inlined_marks_match_the_published_artwork():
    """Guards the copy in _brand.html.jinja against the brand kit drifting.

    Compares the geometry that carries the mark - the tile path and the lens -
    rather than the whole file, because the inlined copy legitimately drops
    role/aria-label/<title>/width/height.
    """
    slot = _brand_slot(_render("index.html"))
    for name in ("codepedia-mark-light.svg", "codepedia-mark-dark.svg"):
        published = (BRAND_SOURCE_DIR / name).read_text(encoding="utf-8")
        tile = re.search(r'd="(M64 34[^"]+)"', published)
        assert tile is not None, name
        assert _squash(tile.group(1)) in _squash(slot), name
        assert 'r="40" stroke-width="14"' in slot


def _squash(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def test_the_inlined_marks_carry_no_namespace_url():
    """An inline <svg> in HTML is namespaced by the parser, so `xmlns` is
    redundant here - and it embeds a literal http:// URL, which the wiki's
    zero-network guards (constitution 2.2) rightly refuse. Never fetched, but
    the guards are blunt on purpose and the attribute buys nothing."""
    slot = _brand_slot(_render("index.html"))
    assert "xmlns" not in slot
    assert "http://" not in slot


def test_the_brand_partial_participates_in_the_template_fingerprint():
    """Invariant 7 of contracts/wiki-theme-shell.md, as an executable guard.

    `template_fingerprint()` globs TEMPLATES_DIR non-recursively for `*.jinja`
    and is what forces a full rebuild when the shell changes. Brand artwork
    moved into a subdirectory, or split out as a `.svg` sidecar, would leave
    that glob - and editing it would then leave every already-generated page
    stale with no signal at all, which is the failure the fingerprint exists to
    prevent.
    """
    from doc_generator.markdown_render import TEMPLATES_DIR, template_fingerprint

    covered = {path.name for path in TEMPLATES_DIR.glob("*.jinja")}
    assert "_brand.html.jinja" in covered
    assert "layout.html.jinja" in covered

    before = template_fingerprint()
    partial = TEMPLATES_DIR / "_brand.html.jinja"
    original = partial.read_bytes()
    try:
        partial.write_bytes(original + b"\n{# fingerprint probe #}\n")
        assert template_fingerprint() != before, (
            "editing the brand partial must change the fingerprint, or "
            "regenerated wikis keep the old mark"
        )
    finally:
        partial.write_bytes(original)
    assert template_fingerprint() == before
