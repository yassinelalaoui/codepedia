"""Feature pages, and the two doors a module has left.

Replaces `test_section_pages.py`. Most of its assertions carry over unchanged in
intent; two do not, and are deliberately inverted rather than deleted:

- the sidebar used to nest modules under collapsible sections. It now lists
  features only, so the test asserts the *absence* of module links there.
- a "section" was a directory. A feature is not, so nothing here asserts on
  directory paths.

The assertions that matter most are `test_every_member_is_listed...` and
`test_every_module_has_a_search_entry`: with modules gone from the sidebar, the
feature page's member list and the search index are all a reader has left.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from doc_generator import DocGenerator, FeaturePlanner, open_doc_manifest_store

from ._doc_generator_support import build_indexed_repo, index_repo


def _build_generator(
    tmp_path: Path, root: Path, store, graph, *, db_name: str = "repo.sqlite", planner=None
) -> DocGenerator:
    manifest_store = open_doc_manifest_store(tmp_path / db_name)
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=root / "docs",
        repositoryRoot=root,
        featurePlanner=planner,
    )


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _two_area_repo(tmp_path: Path):
    """`core/` and `web/`, with `web` importing `core` so they are neighbours."""
    root = tmp_path / "two-area-repo"
    files = [
        _write(root / "core" / "engine.py", '"""Core engine."""\n\n\ndef engine() -> int:\n    return 1\n'),
        _write(
            root / "core" / "registry.py",
            '"""Core registry."""\n\nfrom .engine import engine\n\n\ndef registry() -> int:\n    return engine()\n',
        ),
        _write(root / "web" / "routes.py", '"""Web routes."""\n\n\ndef routes() -> int:\n    return 2\n'),
        _write(
            root / "web" / "server.py",
            '"""Web server."""\n\nfrom ..core.registry import registry\n\n\ndef server() -> int:\n    return registry()\n',
        ),
    ]
    store, graph = index_repo(tmp_path, root, files, "two-area-repo.sqlite")
    return root, store, graph


def _feature_pages(doc_set):
    return [page for page in doc_set.pages if page.kind == "feature"]


# --------------------------------------------------------------------------
# The page itself
# --------------------------------------------------------------------------


def test_a_feature_page_is_written_for_every_feature(tmp_path):
    root, store, graph = _two_area_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-area-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    pages = _feature_pages(doc_set)
    assert pages, "a repository with entry points must produce feature pages"
    for page in pages:
        assert page.outputPathHtml.startswith("features/")
        assert (root / "docs" / page.outputPathHtml).exists()
        assert not (root / "docs" / "sections").exists(), "the previous scheme must be gone"


def test_every_member_is_listed_on_its_feature_page(tmp_path):
    """The assertion standing between a module and being unreachable.

    The sidebar no longer lists modules. If a feature page ever truncated its
    member list, the modules past the cut would have exactly one door left -
    search - and nothing in the wiki would say so.
    """
    root, store, graph = _two_area_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-area-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    for page in _feature_pages(doc_set):
        feature = next(
            f for f in generator._ensure_features() if f.key == page.sourceEntityId
        )
        listed = re.findall(r"^- \[([^\]]+)\]\(", page.contentMarkdown, re.MULTILINE)
        assert len(listed) == len(feature.members), (
            f"{page.title}: {len(listed)} links rendered for {len(feature.members)} members"
        )


def test_every_module_appears_on_exactly_one_feature_page(tmp_path):
    root, store, graph = _two_area_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-area-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    claimed = [key for page in _feature_pages(doc_set) for key in page.relatedSymbols]
    bundle = generator._ensure_bundle()
    assert len(claimed) == len(set(claimed))
    assert set(claimed) == {fb.module.sourceFileId for fb in bundle.files}


def test_a_feature_diagram_draws_only_internal_dependencies(tmp_path):
    root, store, graph = _two_area_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-area-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    for page in _feature_pages(doc_set):
        if "```mermaid" not in page.contentMarkdown:
            continue
        feature = next(f for f in generator._ensure_features() if f.key == page.sourceEntityId)
        member_names = {member.name for member in feature.members}
        drawn = set(re.findall(r'm\d+\["([^"]+)"\]', page.contentMarkdown))
        assert drawn <= member_names, "a feature diagram must not draw a non-member"


def test_feature_diagram_click_directives_survive_into_rendered_html(tmp_path):
    """Click navigation is an existing shipped capability, not a new one."""
    root, store, graph = _two_area_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-area-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    with_diagram = [p for p in _feature_pages(doc_set) if "```mermaid" in p.contentMarkdown]
    if not with_diagram:
        return
    for page in with_diagram:
        assert 'click m' in page.contentMarkdown
        assert 'click m' in page.renderedHtml, "the directive must reach the browser"


# --------------------------------------------------------------------------
# The sidebar, and what left it
# --------------------------------------------------------------------------


def test_the_sidebar_lists_features_and_no_modules(tmp_path):
    root, store, graph = _two_area_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-area-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)
    page = next(p for p in doc_set.pages if p.kind == "module")
    nav = page.renderedHtml.split('<div class="nav-label">Features</div>')[1].split("</nav>")[0]

    assert 'class="nav-link feature' in nav
    assert "features/" in nav
    assert "<details" not in nav, "the collapsible tree is gone"
    assert "modules/" not in nav, "a module link in the sidebar means the tree came back"


def test_every_page_kind_carries_the_feature_navigation(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    for page in doc_set.pages:
        assert '<div class="nav-label">Features</div>' in page.renderedHtml, page.id


def test_home_and_module_pages_are_wired_to_their_feature(tmp_path):
    root, store, graph = _two_area_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-area-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    home = next(p for p in doc_set.pages if p.kind == "home")
    assert "## Features" in home.contentMarkdown
    assert "features/" in home.contentMarkdown

    module_page = next(p for p in doc_set.pages if p.kind == "module")
    assert any(link.toPageId.startswith("feature:") for link in module_page.links)


def test_every_module_has_a_search_entry(tmp_path):
    """A pinning test. `search_index.py` must not change for this to pass.

    With modules out of the sidebar, this is a module's second and last door.
    """
    root, store, graph = _two_area_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-area-repo.sqlite")

    generator.generateRepositoryDocumentation(root, incremental=False)

    index = json.loads((root / "docs" / "assets" / "search-index.json").read_text(encoding="utf-8"))
    module_entries = [e for e in index["entries"] if e["kind"] in ("module", "document")]
    bundle = generator._ensure_bundle()
    assert len(module_entries) == len(bundle.files)


# --------------------------------------------------------------------------
# Incremental behaviour
# --------------------------------------------------------------------------


def test_a_member_change_regenerates_its_feature_page(tmp_path):
    root, store, graph = _two_area_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-area-repo.sqlite")
    generator.generateRepositoryDocumentation(root, incremental=False)

    changed = root / "core" / "engine.py"
    changed.write_text('"""Core engine, revised."""\n\n\ndef engine() -> int:\n    return 9\n', encoding="utf-8")
    generator._features = None
    doc_set = generator.generateRepositoryDocumentation(
        root, incremental=True, changedPaths=[str(changed)]
    )

    assert any(page.kind == "feature" for page in doc_set.pages), (
        "the feature holding the changed module must regenerate"
    )


def test_a_planned_title_does_not_move_a_page_path(tmp_path):
    """A title is model-written and changes between runs; a URL must not."""

    class _Engine:
        def __init__(self, title):
            self.title = title

        def isAvailable(self):
            return True

        def run(self, call):
            outer = self

            class _Inner:
                def generate(self, prompt):
                    return json.dumps(
                        [
                            {"title": outer.title, "kind": "capability", "memberCandidateIds": ["c0"]},
                            {"title": f"{outer.title} Two", "kind": "tooling", "memberCandidateIds": ["c1"]},
                        ]
                    )

            class _Result:
                value = call(_Inner())

            return _Result()

    root, store, graph = _two_area_repo(tmp_path)
    manifest = open_doc_manifest_store(tmp_path / "two-area-repo.sqlite")
    generator = _build_generator(
        tmp_path, root, store, graph, db_name="two-area-repo.sqlite",
        planner=FeaturePlanner(_Engine("First Name")),
    )

    first = generator.generateRepositoryDocumentation(root, incremental=False)
    first_paths = {p.sourceEntityId: p.outputPathHtml for p in _feature_pages(first)}

    generator.featurePlanner = FeaturePlanner(_Engine("Second Name"))
    generator._features = None
    second = generator.generateRepositoryDocumentation(root, incremental=False)
    second_paths = {p.sourceEntityId: p.outputPathHtml for p in _feature_pages(second)}

    assert first_paths == second_paths, "renaming a feature must not move its page"


def test_a_module_page_names_the_feature_it_belongs_to(tmp_path):
    """The chip at the top of every module page.

    It read `section_link` while the generator had started passing
    `feature_link`, so it silently rendered nothing - a Jinja undefined is empty,
    not an error. Found by the completeness grep rather than by a test, which is
    why there is now a test.
    """
    root, store, graph = _two_area_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-area-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    for page in (p for p in doc_set.pages if p.kind == "module"):
        assert "[In feature:" in page.contentMarkdown, page.title
        assert "features/" in page.contentMarkdown
