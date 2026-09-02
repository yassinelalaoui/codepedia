"""A template edit has to reach every already-written page.

`compute_regeneration_impact` reasons about source files: a template carries no
symbol, appears in no dependency edge, and so produced an impact set of exactly
nothing - while changing what every page should contain. The observable symptom
was a wiki where some pages had the new shell and some the old, decided only by
which source files happened to change afterwards.

Measured before the fix, on the three-module fixture: an incremental pass after a
template edit refreshed 5 of 14 pages.
"""

from __future__ import annotations

from pathlib import Path

from doc_generator import DocGenerator, open_doc_manifest_store
from doc_generator.markdown_render import TEMPLATES_DIR, template_fingerprint

from ._doc_generator_support import build_indexed_repo

LAYOUT = TEMPLATES_DIR / "layout.html.jinja"
MARKER = '<meta name="test-marker" content="present">'


def _generator(tmp_path: Path, root: Path, store, graph) -> DocGenerator:
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=open_doc_manifest_store(tmp_path / "manifest.sqlite"),
        outputRoot=tmp_path / "docs",
        repositoryRoot=root,
    )


def _pages_with_marker(output_root: Path) -> tuple[int, int]:
    pages = sorted(output_root.rglob("*.html"))
    carrying = [p for p in pages if MARKER in p.read_text(encoding="utf-8")]
    return len(carrying), len(pages)


def test_editing_a_template_regenerates_every_page(tmp_path, monkeypatch):
    root, store, graph = build_indexed_repo(tmp_path)
    original = LAYOUT.read_bytes()
    generator = _generator(tmp_path, root, store, graph)
    generator.generateRepositoryDocumentation(root, incremental=False)

    carrying, total = _pages_with_marker(tmp_path / "docs")
    assert total > 1
    assert carrying == 0

    # Edit the shared layout, then run the incremental pass `serve` runs when a
    # single source file changes. Restored via the fixture teardown below.
    try:
        LAYOUT.write_bytes(original.replace(b"<head>", b"<head>\n" + MARKER.encode("utf-8"), 1))
        alpha = root / "alpha.py"
        alpha.write_text(alpha.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")

        _generator(tmp_path, root, store, graph).generateRepositoryDocumentation(
            root, incremental=True, changedPaths=[str(alpha)]
        )

        carrying, total = _pages_with_marker(tmp_path / "docs")
        assert carrying == total, (
            f"only {carrying}/{total} pages picked up the template change; "
            "an edited template must invalidate every page, not just the ones "
            "whose source happened to change"
        )
    finally:
        LAYOUT.write_bytes(original)


def test_an_unchanged_template_still_allows_an_incremental_pass(tmp_path):
    """The fix must not turn every run into a full rebuild.

    Constitution 2.5 - only impacted pages are reprocessed. If an unchanged
    template forced a rebuild, incremental regeneration would be dead.
    """
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, root, store, graph)
    generator.generateRepositoryDocumentation(root, incremental=False)

    alpha = root / "alpha.py"
    alpha.write_text(alpha.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
    result = _generator(tmp_path, root, store, graph).generateRepositoryDocumentation(
        root, incremental=True, changedPaths=[str(alpha)]
    )

    total_pages = len(sorted((tmp_path / "docs").rglob("*.html")))
    assert 0 < len(result.pages) < total_pages, (
        "an unchanged template must leave the incremental path intact"
    )


def test_a_wiki_with_no_recorded_fingerprint_rebuilds_once(tmp_path):
    """An existing wiki predates this tracking, so its renderer is unknown.

    Unknown is treated as stale rather than as unchanged: that single rebuild is
    what repairs a wiki generated before the fix landed.
    """
    root, store, graph = build_indexed_repo(tmp_path)
    manifest_path = tmp_path / "manifest.sqlite"
    generator = _generator(tmp_path, root, store, graph)
    generator.generateRepositoryDocumentation(root, incremental=False)
    total_pages = len(sorted((tmp_path / "docs").rglob("*.html")))

    # Exactly the state an older wiki is in: pages and a manifest, no fingerprint.
    store_handle = open_doc_manifest_store(manifest_path)
    with store_handle.session() as opened:
        with opened._connection() as connection:  # noqa: SLF001 - simulating an older schema
            with connection:
                connection.execute("DELETE FROM doc_render_state")
    assert store_handle.load_template_fingerprint(generator.repositoryId) is None

    alpha = root / "alpha.py"
    alpha.write_text(alpha.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
    result = _generator(tmp_path, root, store, graph).generateRepositoryDocumentation(
        root, incremental=True, changedPaths=[str(alpha)]
    )

    assert len(result.pages) == total_pages, "an unknown fingerprint must force one full rebuild"
    assert (
        open_doc_manifest_store(manifest_path).load_template_fingerprint(generator.repositoryId)
        == template_fingerprint()
    ), "the rebuild must record the fingerprint so the next run is incremental again"


def test_a_partial_pass_does_not_record_the_fingerprint(tmp_path):
    """Recording after a partial pass would claim pages were rendered that were not.

    The remaining stale pages would then never be revisited, which is the
    original bug wearing a different hat.
    """
    root, store, graph = build_indexed_repo(tmp_path)
    manifest_path = tmp_path / "manifest.sqlite"
    generator = _generator(tmp_path, root, store, graph)
    generator.generateRepositoryDocumentation(root, incremental=False)

    recorded = open_doc_manifest_store(manifest_path).load_template_fingerprint(generator.repositoryId)
    assert recorded == template_fingerprint()

    # A partial pass leaves the recorded value untouched rather than rewriting it.
    alpha = root / "alpha.py"
    alpha.write_text(alpha.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
    _generator(tmp_path, root, store, graph).generateRepositoryDocumentation(
        root, incremental=True, changedPaths=[str(alpha)]
    )

    assert (
        open_doc_manifest_store(manifest_path).load_template_fingerprint(generator.repositoryId)
        == recorded
    )


def test_fingerprint_covers_adding_and_removing_a_template(tmp_path):
    """Name and content are both hashed, so a new or deleted template counts."""
    before = template_fingerprint()
    extra = TEMPLATES_DIR / "zz_probe.md.jinja"
    try:
        extra.write_text("probe\n", encoding="utf-8")
        assert template_fingerprint() != before
    finally:
        extra.unlink(missing_ok=True)
    assert template_fingerprint() == before
