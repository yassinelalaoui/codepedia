from __future__ import annotations

from pathlib import Path

from doc_generator import links
from doc_generator.manifest_store import open_doc_manifest_store
from doc_generator.models import DocPage
from doc_generator.writer import DocumentationWriter

REPOSITORY_ID = "repo::test"


def _writer(tmp_path: Path) -> DocumentationWriter:
    store = open_doc_manifest_store(tmp_path / "manifest.sqlite")
    return DocumentationWriter(
        outputRoot=tmp_path / "docs", manifestStore=store, repositoryId=REPOSITORY_ID
    )


def _page(page_id: str, markdown: str, html: str, title: str = "A Page") -> DocPage:
    return DocPage(
        id=page_id,
        title=title,
        contentMarkdown=f"# {title}\n",
        kind="feature",
        renderedHtml=f"<h1>{title}</h1>",
        outputPathMarkdown=markdown,
        outputPathHtml=html,
    )


# --------------------------------------------------------------------------
# The alias record itself
# --------------------------------------------------------------------------


def test_alias_is_recorded_and_read_back(tmp_path):
    writer = _writer(tmp_path)

    writer.manifestStore.record_alias(
        REPOSITORY_ID,
        old_page_id="feature:old",
        new_page_id="feature:new",
        old_output_path_markdown="features/old-1234abcd.md",
        old_output_path_html="features/old-1234abcd.html",
    )

    aliases = writer.manifestStore.list_aliases(REPOSITORY_ID)
    assert len(aliases) == 1
    assert aliases[0].oldPageId == "feature:old"
    assert aliases[0].newPageId == "feature:new"
    assert aliases[0].recordedAt


def test_recording_the_same_address_twice_collapses_to_the_endpoint(tmp_path):
    """A page that moves twice leaves one alias, not a chain nobody walks."""
    writer = _writer(tmp_path)

    for destination in ("feature:middle", "feature:final"):
        writer.manifestStore.record_alias(
            REPOSITORY_ID,
            old_page_id="feature:old",
            new_page_id=destination,
            old_output_path_markdown="features/old.md",
            old_output_path_html="features/old.html",
        )

    aliases = writer.manifestStore.list_aliases(REPOSITORY_ID)
    assert len(aliases) == 1
    assert aliases[0].newPageId == "feature:final"


def test_aliases_are_scoped_to_their_repository(tmp_path):
    writer = _writer(tmp_path)
    writer.manifestStore.record_alias(
        REPOSITORY_ID,
        old_page_id="feature:old",
        new_page_id="feature:new",
        old_output_path_markdown="features/old.md",
        old_output_path_html="features/old.html",
    )

    assert writer.manifestStore.list_aliases("repo::somewhere-else") == ()


# --------------------------------------------------------------------------
# The removal guard - the reason the table exists
# --------------------------------------------------------------------------


def test_removal_skips_a_path_an_alias_points_through(tmp_path):
    """The load-bearing assertion of this whole phase.

    Written so it can only pass if the file survives - asserting that
    `list_aliases` was *called* would pass against an implementation that reads
    the answer and ignores it.
    """
    writer = _writer(tmp_path)
    page = _page("feature:old", "features/old.md", "features/old.html")
    writer.write_page(page)

    # The anchor moved: the old address becomes a redirect to the new page.
    writer.manifestStore.record_alias(
        REPOSITORY_ID,
        old_page_id="feature:old",
        new_page_id="feature:new",
        old_output_path_markdown="features/old.md",
        old_output_path_html="features/old.html",
    )
    writer.write_redirect_stub(
        old_paths=("features/old.md", "features/old.html"),
        new_paths=("features/new.md", "features/new.html"),
        title="New Home",
    )

    # ...and then an incremental run decides `feature:old` no longer exists.
    writer.remove_page("feature:old")

    stub = writer.outputRoot / "features" / "old.html"
    assert stub.exists(), "the incremental run deleted the file the redirect points at"
    assert "New Home" in stub.read_text(encoding="utf-8")


def test_removal_still_deletes_a_page_with_no_alias(tmp_path):
    """The guard must not turn removal into a no-op for ordinary pages."""
    writer = _writer(tmp_path)
    writer.write_page(_page("feature:gone", "features/gone.md", "features/gone.html"))

    writer.remove_page("feature:gone")

    assert not (writer.outputRoot / "features" / "gone.html").exists()
    assert not (writer.outputRoot / "features" / "gone.md").exists()
    assert writer.manifestStore.load_entry("feature:gone") is None


def test_removal_deletes_a_page_aliased_in_another_repository(tmp_path):
    """An alias protects one repository's paths, not every wiki's."""
    writer = _writer(tmp_path)
    writer.write_page(_page("feature:gone", "features/gone.md", "features/gone.html"))
    writer.manifestStore.record_alias(
        "repo::elsewhere",
        old_page_id="feature:gone",
        new_page_id="feature:new",
        old_output_path_markdown="features/gone.md",
        old_output_path_html="features/gone.html",
    )

    writer.remove_page("feature:gone")

    assert not (writer.outputRoot / "features" / "gone.html").exists()


# --------------------------------------------------------------------------
# The stub a reader actually lands on
# --------------------------------------------------------------------------


def test_redirect_stub_carries_a_visible_link_not_only_a_refresh(tmp_path):
    """A reader whose browser blocks the refresh must still get there.

    And must be able to tell *where* they were sent - spec acceptance 3.4.
    """
    writer = _writer(tmp_path)

    writer.write_redirect_stub(
        old_paths=("features/old.md", "features/old.html"),
        new_paths=("features/new.md", "features/new.html"),
        title="Repository Indexing",
    )

    body = (writer.outputRoot / "features" / "old.html").read_text(encoding="utf-8")
    assert 'http-equiv="refresh"' in body
    assert 'rel="canonical"' in body
    assert '<a href="new.html">Repository Indexing</a>' in body


def test_redirect_target_is_relative_so_it_works_over_file_urls(tmp_path):
    """An absolute or `http://` target would break `file://` reading.

    It would also be the feature's only outbound network request, against
    constitution 2.2.
    """
    writer = _writer(tmp_path)

    writer.write_redirect_stub(
        old_paths=("features/old.md", "features/old.html"),
        new_paths=("modules/deep/new.md", "modules/deep/new.html"),
        title="Elsewhere",
    )

    body = (writer.outputRoot / "features" / "old.html").read_text(encoding="utf-8")
    assert "http://" not in body and "https://" not in body
    assert 'content="0; url=../modules/deep/new.html"' in body


def test_redirect_stub_escapes_its_title(tmp_path):
    """Titles are model-written; one containing markup must not become markup."""
    writer = _writer(tmp_path)

    writer.write_redirect_stub(
        old_paths=("features/old.md", "features/old.html"),
        new_paths=("features/new.md", "features/new.html"),
        title='Chat & <script>alert("x")</script>',
    )

    body = (writer.outputRoot / "features" / "old.html").read_text(encoding="utf-8")
    assert "<script>" not in body
    assert "&amp;" in body


def test_markdown_stub_is_one_line_pointing_at_the_markdown_page(tmp_path):
    writer = _writer(tmp_path)

    writer.write_redirect_stub(
        old_paths=("features/old.md", "features/old.html"),
        new_paths=("features/new.md", "features/new.html"),
        title="New Home",
    )

    body = (writer.outputRoot / "features" / "old.md").read_text(encoding="utf-8")
    assert body.strip() == "This page has moved to [New Home](new.md)."


# --------------------------------------------------------------------------
# Feature page identity
# --------------------------------------------------------------------------


def test_feature_slug_takes_one_argument_and_is_readable(tmp_path):
    key = "repo::/r::file::/r/src/chat/session.py"

    slug = links.feature_slug(key)

    assert slug.startswith("session-")
    assert links.feature_output_paths(slug) == (
        f"features/{slug}.md",
        f"features/{slug}.html",
    )
    assert links.feature_page_id(key) == f"feature:{key}"


def test_two_anchors_sharing_a_module_name_get_different_slugs(tmp_path):
    """Eleven files in this repository are called `models.py`."""
    left = links.feature_slug("repo::/r::file::/r/src/chat/models.py")
    right = links.feature_slug("repo::/r::file::/r/src/doc_generator/models.py")

    assert left != right
    assert left.startswith("models-") and right.startswith("models-")


def test_feature_slug_is_stable_across_calls():
    key = "repo::/r::file::/r/src/chat/session.py"

    assert links.feature_slug(key) == links.feature_slug(key)


# --------------------------------------------------------------------------
# Module page identity
# --------------------------------------------------------------------------


def test_two_modules_sharing_a_name_get_different_page_slugs():
    """`page_slug` must disambiguate, and it used not to.

    Its suffix was the last eight alphanumeric characters of the entity id. A
    module key ends in its own file path, so that suffix was the *filename* -
    identical for every `models.py` in the repository. Measured on this
    repository: 10 slugs claimed by more than one module, 24 of 139 module pages
    silently overwritten by a namesake.
    """
    left = links.page_slug("models", "repo::/r::file::/r/src/chat/models.py")
    right = links.page_slug("models", "repo::/r::file::/r/src/doc_generator/models.py")

    assert left != right
    assert left.startswith("models-") and right.startswith("models-")


def test_page_slug_is_stable_across_calls():
    key = "repo::/r::file::/r/src/chat/models.py"

    assert links.page_slug("models", key) == links.page_slug("models", key)


def test_every_module_in_a_repository_gets_a_distinct_slug():
    """The property that actually matters, stated as a property."""
    keys = [
        f"repo::/r::file::/r/src/{package}/models.py"
        for package in ("chat", "cli", "doc_generator", "local_llm", "vector_index")
    ]

    slugs = {links.page_slug("models", key) for key in keys}

    assert len(slugs) == len(keys)
