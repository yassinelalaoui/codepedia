"""Nothing from the homepage leaked into a generated wiki (spec FR-045).

The hub may talk to its own origin; a generated wiki may not talk to anything.
That leniency is one-directional, and the two bundles share a source project, so
the separation is worth asserting rather than assuming - a stray import in a
shared module would carry hub code into every wiki ever generated after it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WIKI_ASSETS = REPO_ROOT / "src" / "doc_generator" / "assets"
HUB_ASSETS = REPO_ROOT / "src" / "hub_server" / "assets"

WIKI_JS = WIKI_ASSETS / "wiki-ui.js"
WIKI_CSS = WIKI_ASSETS / "wiki-ui.css"


@pytest.fixture(scope="module")
def wiki_js() -> str:
    if not WIKI_JS.exists():
        pytest.skip("wiki bundle not built")
    return WIKI_JS.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def wiki_css() -> str:
    if not WIKI_CSS.exists():
        pytest.skip("wiki bundle not built")
    return WIKI_CSS.read_text(encoding="utf-8", errors="replace")


@pytest.mark.parametrize(
    "marker",
    [
        "/api/runs",
        "/api/repositories",
        "/api/run-log",
        "runStreamUrl",
        "hubApi",
    ],
)
def test_the_wiki_bundle_contains_no_hub_endpoint(wiki_js, marker):
    assert marker not in wiki_js, f"the wiki bundle references the hub's {marker}"


def test_the_wiki_bundle_opens_no_event_source(wiki_js):
    """A generated wiki is opened from the filesystem with no server. A live
    connection is meaningless there and would be a runtime error on every page."""
    assert "new EventSource" not in wiki_js


@pytest.mark.parametrize("marker", ["index-bar", "run-progress", "history-menu", "run-outcome", "hub__"])
def test_the_wiki_stylesheet_contains_no_homepage_styles(wiki_css, marker):
    """`hub.css` is imported only from `hub.tsx`, which is what keeps it out of
    here. If this fails, someone imported it from a shared module."""
    assert marker not in wiki_css


def test_the_hub_bundle_exists_and_is_separate():
    hub_js = HUB_ASSETS / "hub-ui.js"
    if not hub_js.exists():
        pytest.skip("hub bundle not built")

    assert hub_js.read_bytes() != WIKI_JS.read_bytes()


def test_the_hub_build_did_not_write_into_the_wiki_assets_directory():
    """The two builds share a source project but must never share an output."""
    assert not (WIKI_ASSETS / "hub-ui.js").exists()
    assert not (WIKI_ASSETS / "hub-ui.css").exists()
    assert not (WIKI_ASSETS / "index.html").exists()
