"""A published address must survive the page behind it being re-identified.

**Scope note.** This phase (A2) lands deliberately *before* anything renders a
feature page, because publishing a URL before the alias table exists ships links
that the first refactor breaks. So these tests drive the mechanism through a real
generator, a real manifest and a real removal pass - but on the page kinds that
render today. The feature-page-specific detection is wired in A4, and
`test_section_manifest_migration.py` covers it there.

What is proven here is the part that has to be right before any of that: an
address, once published, keeps working.
"""

from __future__ import annotations

from pathlib import Path

from ._doc_generator_support import build_indexed_repo

from doc_generator import links
from doc_generator.generator import DocGenerator
from doc_generator.manifest_store import open_doc_manifest_store
from doc_generator.models import DocPage


def _generator(tmp_path: Path, root: Path, store, graph) -> DocGenerator:
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=open_doc_manifest_store(tmp_path / "manifest.sqlite"),
        outputRoot=tmp_path / "docs",
        repositoryRoot=root,
    )


def _write_stub_page(generator: DocGenerator, page_id: str, slug: str, title: str) -> DocPage:
    markdown, html = links.feature_output_paths(slug)
    page = DocPage(
        id=page_id,
        title=title,
        contentMarkdown=f"# {title}\n",
        kind="feature",
        sourceEntityId=page_id,
        renderedHtml=f"<h1>{title}</h1>",
        outputPathMarkdown=markdown,
        outputPathHtml=html,
    )
    generator._writer.write_page(page)
    return page


def test_a_moved_page_keeps_its_old_address_working(tmp_path):
    """The scenario the alias table exists for, end to end.

    Two runs: in the first, a feature is anchored on `alpha`; between them the
    anchor moves to `beta`, so the page id and the output path both change. The
    address published by run one must still lead somewhere.
    """
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, root, store, graph)

    old_key = "repo::r::file::/r/alpha.py"
    new_key = "repo::r::file::/r/beta.py"
    old_id, new_id = links.feature_page_id(old_key), links.feature_page_id(new_key)
    old_slug, new_slug = links.feature_slug(old_key), links.feature_slug(new_key)

    # Run 1: the reader bookmarks this.
    _write_stub_page(generator, old_id, old_slug, "Repository Indexing")
    bookmarked = generator.outputRoot / links.feature_output_paths(old_slug)[1]
    assert bookmarked.exists()

    # Run 2: the anchor moved, so the same feature is published at a new address.
    _write_stub_page(generator, new_id, new_slug, "Repository Indexing")
    moved = generator.recordPageMove(
        oldPageId=old_id, newPageId=new_id, title="Repository Indexing"
    )

    assert moved is True
    assert bookmarked.exists(), "the bookmarked address must not simply vanish"
    body = bookmarked.read_text(encoding="utf-8")
    assert f"{new_slug}.html" in body, "and it must lead to where the feature went"


def test_the_removal_pass_does_not_delete_the_redirect(tmp_path):
    """The sequence that makes this hard: move, then an incremental run.

    `impact.removedPageIds` computes that the old page id is no longer current -
    which is true - and asks the writer to unlink it. Without the alias guard
    that deletes the freshly written stub, and the reader's bookmark dies one run
    after being saved rather than immediately. Slower, and harder to notice.
    """
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, root, store, graph)

    old_key = "repo::r::file::/r/alpha.py"
    new_key = "repo::r::file::/r/beta.py"
    old_id, new_id = links.feature_page_id(old_key), links.feature_page_id(new_key)
    old_slug, new_slug = links.feature_slug(old_key), links.feature_slug(new_key)

    _write_stub_page(generator, old_id, old_slug, "Indexing")
    _write_stub_page(generator, new_id, new_slug, "Indexing")
    generator.recordPageMove(oldPageId=old_id, newPageId=new_id, title="Indexing")

    generator._writer.remove_page(old_id)

    stub = generator.outputRoot / links.feature_output_paths(old_slug)[1]
    assert stub.exists(), "the incremental removal pass deleted the redirect"
    assert f"{new_slug}.html" in stub.read_text(encoding="utf-8")


def test_a_retitled_page_keeps_its_address(tmp_path):
    """A title is written by a model and changes between runs; a URL must not.

    This is the invariant `test_section_navigation.py` was built around, carried
    forward: the slug comes from the anchor module, never from the title.
    """
    key = "repo::r::file::/r/alpha.py"

    first = links.feature_slug(key)
    second = links.feature_slug(key)

    assert first == second
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, root, store, graph)
    _write_stub_page(generator, links.feature_page_id(key), first, "Original Title")
    _write_stub_page(generator, links.feature_page_id(key), first, "A Completely New Title")

    entry = generator.manifestStore.load_entry(links.feature_page_id(key))
    assert entry is not None
    assert entry.outputPathHtml == links.feature_output_paths(first)[1]


def test_no_alias_is_recorded_when_the_destination_was_never_written(tmp_path):
    """A stub pointing at a page that does not exist is worse than no stub.

    It converts a dead link into a dead link that claims to be a redirect, which
    is harder to diagnose, not easier.
    """
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, root, store, graph)

    old_key = "repo::r::file::/r/alpha.py"
    old_id = links.feature_page_id(old_key)
    _write_stub_page(generator, old_id, links.feature_slug(old_key), "Indexing")

    moved = generator.recordPageMove(
        oldPageId=old_id, newPageId="feature:never-written", title="Indexing"
    )

    assert moved is False
    assert generator.manifestStore.list_aliases(generator.repositoryId) == ()


def test_moving_a_page_onto_itself_is_a_no_op(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, root, store, graph)

    key = "repo::r::file::/r/alpha.py"
    page_id = links.feature_page_id(key)
    _write_stub_page(generator, page_id, links.feature_slug(key), "Indexing")

    assert generator.recordPageMove(oldPageId=page_id, newPageId=page_id, title="Indexing") is False
    assert generator.manifestStore.list_aliases(generator.repositoryId) == ()


def test_a_real_anchor_move_across_two_runs_leaves_a_redirect(tmp_path):
    """The end-to-end case the mechanism was built for, driven by real imports.

    This is the test that was missing. `recordPageMove` was unit-tested and the
    alias table was unit-tested, but nothing asserted that the *generator* calls
    them when an anchor actually moves - so it did not, and the previously
    published URL simply died. Found by regenerating a real wiki twice.

    Two things it pins that the unit tests cannot:

    1. the generator invokes the redirect path on an ordinary run, not only
       while migrating a legacy manifest;
    2. the old output paths come from the `previous_entries` snapshot, because
       the removal pass has already deleted that manifest row by the time
       feature pages are written on an incremental run.
    """
    from dependency_graph import DependencyGraph
    from parser_engine import SourceFile, extract_symbols
    from repository_metadata import RepositoryMetadataStore, compute_content_hash

    root = tmp_path / "repo" / "app"
    root.mkdir(parents=True)
    #  cli -> core -> util,  extra -> core   =>  anchor is `core`
    (root / "cli.py").write_text(
        '"""CLI."""\n\nfrom .core import core_run\n\n\ndef main() -> int:\n    return core_run()\n',
        encoding="utf-8",
    )
    (root / "core.py").write_text(
        '"""Core."""\n\nfrom .util import helper\n\n\ndef core_run() -> int:\n    return helper()\n',
        encoding="utf-8",
    )
    (root / "util.py").write_text('"""Util."""\n\n\ndef helper() -> int:\n    return 1\n', encoding="utf-8")
    (root / "extra.py").write_text(
        '"""Extra."""\n\nfrom .core import core_run\n\n\ndef _e() -> int:\n    return core_run()\n',
        encoding="utf-8",
    )
    repo_root = tmp_path / "repo"

    def index(db_name: str):
        paths = sorted(repo_root.rglob("*.py"))
        inventories = [extract_symbols(SourceFile(path=p, language="python")) for p in paths]
        graph = DependencyGraph.build_from_inventories(inventories, sourceFile=str(repo_root))
        store = RepositoryMetadataStore(tmp_path / db_name)
        store.ensure_repository(repo_root, detected_languages=("python",))
        for inventory in inventories:
            path = Path(inventory.sourceFile)
            store.store_inventory(
                repository_root=repo_root,
                source_file=SourceFile(path=path, language="python"),
                inventory=inventory,
                content_hash=compute_content_hash(path),
            )
        return store, graph

    store, graph = index("meta1.sqlite")
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=open_doc_manifest_store(tmp_path / "manifest.sqlite"),
        outputRoot=tmp_path / "docs",
        repositoryRoot=repo_root,
    )
    first = generator.generateRepositoryDocumentation(repo_root, incremental=False)
    published = [p.outputPathHtml for p in first.pages if p.kind == "feature"]
    assert published, "run 1 must publish at least one feature page"

    #  cli -> util, core -> util, extra -> util  =>  anchor becomes `util`
    (root / "cli.py").write_text(
        '"""CLI."""\n\nfrom .util import helper\n\n\ndef main() -> int:\n    return helper()\n',
        encoding="utf-8",
    )
    (root / "extra.py").write_text(
        '"""Extra."""\n\nfrom .util import helper\n\n\ndef _e() -> int:\n    return helper()\n',
        encoding="utf-8",
    )
    store2, graph2 = index("meta2.sqlite")
    generator.metadataStore, generator.dependencyGraph = store2, graph2
    generator._bundle = None
    generator._features = None
    second = generator.generateRepositoryDocumentation(
        repo_root,
        incremental=True,
        changedPaths=[str(root / "cli.py"), str(root / "extra.py")],
    )
    current = {p.outputPathHtml for p in second.pages if p.kind == "feature"}

    moved = [path for path in published if path not in current]
    assert moved, "the fixture must actually move an anchor, or this proves nothing"

    for path in moved:
        stub = generator.outputRoot / path
        assert stub.exists(), f"{path} died instead of redirecting"
        body = stub.read_text(encoding="utf-8")
        assert 'http-equiv="refresh"' in body
        target = body.split("url=")[1].split('"')[0]
        assert (stub.parent / target).exists(), "the redirect points at a page that is not there"
