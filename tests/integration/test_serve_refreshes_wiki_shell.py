"""Serving an already-generated wiki brings its shell up to date first.

A generated wiki is a snapshot: the HTML came from the templates as they were
when it was written, and `assets/wiki-ui.js` is a copy of the bundle from that
same day. The watcher only runs when a *source file* changes, so a repository
whose code has not moved since it was analysed was served from its original
shell forever - which is how a wiki generated before the homepage existed ended
up with no link back to it, and a wiki generated before a bundle fix kept the
old behaviour with nothing to indicate it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.index_command import run_index
from cli.serve_command import run_serve
from doc_generator.markdown_render import template_fingerprint

from integration.test_cli import (  # noqa: F401 - imported for their fixture side effect
    _copy_fixture_repo,
    _local_config,
    cli_home,
    fake_engines,
)

CURRENT_BUNDLE = Path("src/doc_generator/assets/wiki-ui.js").resolve()


def docs_dir(result) -> Path:
    return Path(result.docsRoot)


def close(result) -> None:
    if result.watcher is not None:
        result.watcher.stop()
    result.vectorIndex.close()


def test_a_stale_bundle_is_replaced_when_the_repository_is_served(tmp_path, cli_home, fake_engines):
    """The symptom: an old wiki carries an old wiki-ui.js and nothing updates it."""
    root = _copy_fixture_repo(tmp_path)
    indexed = run_index(root, config=_local_config())
    docs = docs_dir(indexed)
    indexed.vectorIndex.close()

    bundle = docs / "assets" / "wiki-ui.js"
    assert bundle.exists()
    # Stand in for a bundle written by an older build.
    bundle.write_text("// an older build's bundle\n", encoding="utf-8")

    served = run_serve(root, config=_local_config())
    try:
        assert bundle.read_bytes() == CURRENT_BUNDLE.read_bytes(), (
            "serving the repository left it on an out-of-date wiki bundle"
        )
    finally:
        close(served)


def test_a_stale_shell_is_rebuilt_when_the_templates_have_moved(tmp_path, cli_home, fake_engines):
    """A template edit makes every page stale, and no source file changed.

    The generator already forces a full rebuild when its template fingerprint
    differs; what was missing was anything calling it on a repository whose code
    had not moved.
    """
    root = _copy_fixture_repo(tmp_path)
    indexed = run_index(root, config=_local_config())
    docs = docs_dir(indexed)
    indexed.vectorIndex.close()

    home = docs / "index.html"
    original = home.read_text(encoding="utf-8")
    # Every generated wiki now carries the back-to-the-homepage marker.
    assert "data-hub-home" in original

    # Simulate a wiki written by an older set of templates: damage the page and
    # record a fingerprint that cannot match the current one.
    home.write_text("<html><body>an older shell</body></html>", encoding="utf-8")
    from cli import paths as cli_paths
    from doc_generator import open_doc_manifest_store
    from repository_metadata.sqlite_store import stable_repository_id

    state_dir = cli_paths.repo_state_dir(root)
    store = open_doc_manifest_store(cli_paths.doc_manifest_db_path(state_dir))
    with store.session():
        store.save_template_fingerprint(stable_repository_id(root), "a-fingerprint-from-an-older-build")

    served = run_serve(root, config=_local_config())
    try:
        rebuilt = home.read_text(encoding="utf-8")
        assert "an older shell" not in rebuilt, "the stale page survived being served"
        assert "data-hub-home" in rebuilt, "the rebuilt page is missing the homepage link"
    finally:
        close(served)


def test_the_fingerprint_is_recorded_so_the_rebuild_happens_once(tmp_path, cli_home, fake_engines):
    """A repeat serve of an up-to-date wiki must not rebuild anything."""
    root = _copy_fixture_repo(tmp_path)
    indexed = run_index(root, config=_local_config())
    docs = docs_dir(indexed)
    indexed.vectorIndex.close()

    home = docs / "index.html"
    first = run_serve(root, config=_local_config())
    close(first)
    after_first = home.stat().st_mtime_ns

    second = run_serve(root, config=_local_config())
    close(second)

    assert home.stat().st_mtime_ns == after_first, "an up-to-date wiki was rewritten needlessly"


def test_serving_needs_no_provider_to_refresh_the_shell(tmp_path, cli_home, fake_engines, monkeypatch):
    """The refresh reads summaries from the store and the feature plan from the
    manifest, so it still works where no chain can be reached - which is the
    situation the wikis most in need of it are sitting in."""
    root = _copy_fixture_repo(tmp_path)
    indexed = run_index(root, config=_local_config())
    docs = docs_dir(indexed)
    indexed.vectorIndex.close()

    (docs / "assets" / "wiki-ui.js").write_text("// stale\n", encoding="utf-8")

    import repository_metadata as metadata

    def refuse(*args, **kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("the shell refresh consulted a model")

    monkeypatch.setattr(metadata.CodeSummaryPipeline, "summarizeRepository", refuse, raising=False)

    served = run_serve(root, config=_local_config())
    try:
        assert (docs / "assets" / "wiki-ui.js").read_bytes() == CURRENT_BUNDLE.read_bytes()
    finally:
        close(served)
