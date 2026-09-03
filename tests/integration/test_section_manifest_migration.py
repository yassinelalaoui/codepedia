"""A wiki built by the previous navigation scheme must survive the upgrade.

Every `sections/*.html` address this project ever published has to keep working.
The migration runs once, forced by finding a `kind="section"` row in the
manifest, and pins each old address at the feature that inherited most of that
section's modules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from doc_generator import DocGenerator, open_doc_manifest_store
from doc_generator.models import PageManifestEntry

from ._doc_generator_support import build_indexed_repo


def _generator(tmp_path: Path, root: Path, store, graph) -> DocGenerator:
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=open_doc_manifest_store(tmp_path / "manifest.sqlite"),
        outputRoot=root / "docs",
        repositoryRoot=root,
    )


def _seed_legacy_section_page(generator: DocGenerator, module_keys, *, slug="root-8f2c1a30"):
    """Write what the previous version left on disk and in the manifest.

    A section page stored its member module keys in `sourceSymbolIds` - the
    generator passed `contentSymbolIds=section.moduleKeys` - which is exactly
    what makes the migration computable.
    """
    markdown, html = f"sections/{slug}.md", f"sections/{slug}.html"
    for relative, body in ((markdown, "# Root\n"), (html, "<h1>Root</h1>")):
        path = generator.outputRoot / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    generator.manifestStore.save_entry(
        generator.repositoryId,
        PageManifestEntry(
            pageId="section:.",
            kind="section",
            sourceSymbolIds=tuple(module_keys),
            contentHash="legacy",
            outputPathMarkdown=markdown,
            outputPathHtml=html,
            lastGeneratedAt=datetime.now(timezone.utc).isoformat(),
        ),
    )
    return markdown, html


def test_an_old_section_address_still_resolves(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, root, store, graph)
    bundle = generator._ensure_bundle()
    module_keys = [fb.module.sourceFileId for fb in bundle.files]
    _markdown, html = _seed_legacy_section_page(generator, module_keys)

    generator.generateRepositoryDocumentation(root, incremental=True)

    stub = generator.outputRoot / html
    assert stub.exists(), "the published section address must not simply vanish"
    body = stub.read_text(encoding="utf-8")
    assert "http-equiv=\"refresh\"" in body
    assert "features/" in body, "and it must lead to a feature page"


def test_the_old_address_lands_on_the_feature_holding_most_of_its_modules(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, root, store, graph)
    bundle = generator._ensure_bundle()

    # A section that held only alpha: whichever feature now owns alpha is where
    # its address has to land.
    alpha_key = next(
        fb.module.sourceFileId for fb in bundle.files if fb.module.name == "alpha"
    )
    _markdown, html = _seed_legacy_section_page(generator, [alpha_key], slug="alpha-only-1234abcd")

    generator.generateRepositoryDocumentation(root, incremental=True)

    owning = generator._feature_by_module_key()[alpha_key]
    expected_html = Path(generator._feature_identity(owning)[2]).name
    assert expected_html in (generator.outputRoot / html).read_text(encoding="utf-8")


def test_the_migration_forces_one_full_rebuild(tmp_path):
    """No per-page impact set can express "the whole grouping changed"."""
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, root, store, graph)
    bundle = generator._ensure_bundle()
    _seed_legacy_section_page(generator, [fb.module.sourceFileId for fb in bundle.files])

    doc_set = generator.generateRepositoryDocumentation(root, incremental=True)

    kinds = {page.kind for page in doc_set.pages}
    assert "home" in kinds and "module" in kinds and "feature" in kinds, (
        "an incremental run over a legacy manifest must still rewrite everything"
    )


def test_the_previous_schemes_cached_names_are_dropped(tmp_path):
    """Left behind, an old section title could surface in a feature's sidebar."""
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, root, store, graph)
    bundle = generator._ensure_bundle()
    _seed_legacy_section_page(generator, [fb.module.sourceFileId for fb in bundle.files])

    with generator.manifestStore._connection() as connection:
        with connection:
            connection.execute(
                "INSERT INTO doc_section_narrations (repository_id, section_key, membership_hash,"
                " title, description, generated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (generator.repositoryId, ".", "h", "An Old Name", "", "now"),
            )

    generator.generateRepositoryDocumentation(root, incremental=True)

    with generator.manifestStore._connection() as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) AS n FROM doc_section_narrations WHERE repository_id = ?",
            (generator.repositoryId,),
        ).fetchone()["n"]
    assert remaining == 0


def test_a_second_run_is_incremental_again(tmp_path):
    """The migration happens once, not on every run afterwards."""
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, root, store, graph)
    bundle = generator._ensure_bundle()
    _seed_legacy_section_page(generator, [fb.module.sourceFileId for fb in bundle.files])

    generator.generateRepositoryDocumentation(root, incremental=True)
    generator._features = None
    second = generator.generateRepositoryDocumentation(root, incremental=True)

    assert len(second.pages) < 16, (
        "the second run found no section rows, so it must not rebuild everything"
    )


def test_a_section_whose_modules_all_vanished_is_not_redirected_anywhere(tmp_path):
    """A stub pointing nowhere is worse than no stub."""
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, root, store, graph)
    _markdown, html = _seed_legacy_section_page(
        generator, ["repo::gone::file::/gone/deleted.py"], slug="ghost-00000000"
    )

    generator.generateRepositoryDocumentation(root, incremental=True)

    aliases = generator.manifestStore.list_aliases(generator.repositoryId)
    assert all(alias.oldOutputPathHtml != html for alias in aliases)
