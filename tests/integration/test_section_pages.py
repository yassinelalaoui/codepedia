from __future__ import annotations

import re
from pathlib import Path

from doc_generator import DocGenerator, SectionNarrator, open_doc_manifest_store
from parser_engine import SourceFile, extract_symbols
from provider_routing import FailoverExecutor, ProviderRef
from repository_metadata import compute_content_hash
from repository_metadata.sqlite_store import stable_repository_id

from ._doc_generator_support import build_indexed_repo, index_repo


def _build_generator(
    tmp_path: Path, root: Path, store, graph, *, db_name: str = "repo.sqlite", section_narrator=None
) -> DocGenerator:
    manifest_store = open_doc_manifest_store(tmp_path / db_name)
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=root / "docs",
        repositoryRoot=root,
        sectionNarrator=section_narrator,
    )


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _two_section_repo(tmp_path: Path):
    """`core/` and `web/`, with `web` importing `core` so they are neighbours."""
    root = tmp_path / "two-section-repo"
    files = [
        _write(root / "core" / "engine.py", '"""Core engine."""\n\n\ndef engine() -> int:\n    return 1\n'),
        _write(
            root / "core" / "registry.py",
            '"""Core registry."""\n\nfrom engine import engine\n\n\ndef registry() -> int:\n    return engine()\n',
        ),
        _write(root / "web" / "routes.py", '"""Web routes."""\n\n\ndef routes() -> int:\n    return 2\n'),
        _write(
            root / "web" / "server.py",
            '"""Web server."""\n\nfrom registry import registry\n\n\ndef server() -> int:\n    return registry()\n',
        ),
    ]
    store, graph = index_repo(tmp_path, root, files, "two-section-repo.sqlite")
    return root, store, graph


def test_one_section_page_per_section_listing_its_members(tmp_path):
    root, store, graph = _two_section_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-section-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    section_pages = {page.title: page for page in doc_set.pages if page.kind == "section"}
    assert set(section_pages) == {"core", "web"}

    core_page = section_pages["core"]
    assert "[engine](" in core_page.contentMarkdown
    assert "[registry](" in core_page.contentMarkdown
    assert "routes" not in core_page.contentMarkdown.split("## Related sections")[0]
    # `web` imports `core`, so each is listed as the other's neighbour.
    assert "## Related sections" in core_page.contentMarkdown
    assert "[web](" in core_page.contentMarkdown.split("## Related sections")[1]


def test_section_page_diagrams_only_internal_dependencies(tmp_path):
    root, store, graph = _two_section_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-section-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)
    core_page = next(page for page in doc_set.pages if page.kind == "section" and page.title == "core")

    mermaid = core_page.contentMarkdown.split("```mermaid")[1].split("```")[0]
    assert "engine" in mermaid and "registry" in mermaid
    assert "server" not in mermaid, "an edge leaving the section must not be drawn"
    # Nodes link back to the member's own module page.
    assert "click m0 href" in mermaid


def test_home_and_module_pages_are_wired_to_their_section(tmp_path):
    root, store, graph = _two_section_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-section-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    home_page = next(page for page in doc_set.pages if page.kind == "home")
    assert "## Sections" in home_page.contentMarkdown
    assert "| Section | Modules |" in home_page.contentMarkdown

    engine_page = next(page for page in doc_set.pages if page.kind == "module" and page.title == "engine")
    assert "[In section: core]" in engine_page.contentMarkdown

    section_page_ids = {page.id for page in doc_set.pages if page.kind == "section"}
    assert section_page_ids <= set(home_page.links and [link.toPageId for link in home_page.links])


def test_sidebar_nests_modules_under_collapsible_sections(tmp_path):
    root, store, graph = _two_section_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-section-repo.sqlite")

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)
    engine_page = next(page for page in doc_set.pages if page.kind == "module" and page.title == "engine")

    html = engine_page.renderedHtml
    assert html.count("<details class=\"nav-section\"") == 2
    # The section owning the page being rendered is the one left open, and
    # `<details open>` needs no JavaScript to do it.
    assert "<details class=\"nav-section\" open>" in html
    assert html.count("<details class=\"nav-section\" open>") == 1
    compact = re.sub(r"\s+", "", html)
    assert "core</summary>" in compact
    assert "web</summary>" in compact
    assert "sections/core-" in html


def test_every_page_kind_carries_the_section_navigation(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    for page in doc_set.pages:
        assert "nav-section" in page.renderedHtml, f"no section navigation on {page.id} ({page.kind})"


def test_member_change_regenerates_the_section_page_but_not_the_whole_wiki(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    generator.generateRepositoryDocumentation(root, incremental=False)

    beta_path = root / "beta.py"
    beta_path.write_text(
        beta_path.read_text(encoding="utf-8").replace("return number + 1", "return number + 2"), encoding="utf-8"
    )
    inventory = extract_symbols(SourceFile(path=beta_path, language="python"))
    graph.ingest_inventory(inventory)
    store.store_inventory(
        repository_root=root,
        source_file=SourceFile(path=beta_path, language="python"),
        inventory=inventory,
        content_hash=compute_content_hash(beta_path),
    )

    doc_set = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(beta_path)])

    assert "section" in {page.kind for page in doc_set.pages}
    # The section's membership is unchanged, so navigation keeps its shape and
    # the untouched module pages are left alone.
    regenerated_module_titles = {page.title for page in doc_set.pages if page.kind == "module"}
    assert regenerated_module_titles == {"beta"}


def test_a_new_module_reshapes_navigation_and_regenerates_every_page(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    first_run = generator.generateRepositoryDocumentation(root, incremental=False)
    page_count = len(first_run.pages)

    delta_path = _write(root / "delta.py", '"""Delta module."""\n\n\ndef delta() -> int:\n    return 4\n')
    inventory = extract_symbols(SourceFile(path=delta_path, language="python"))
    graph.ingest_inventory(inventory)
    store.store_inventory(
        repository_root=root,
        source_file=SourceFile(path=delta_path, language="python"),
        inventory=inventory,
        content_hash=compute_content_hash(delta_path),
    )

    doc_set = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(delta_path)])

    # The sidebar lists every module on every page, so a module that appears
    # leaves every already-written page stale - all of them must be rewritten.
    assert len(doc_set.pages) > page_count
    assert {page.kind for page in doc_set.pages} >= {"home", "module", "section", "diagram"}
    for page in doc_set.pages:
        assert "delta" in page.renderedHtml or page.kind in {"class-diagram", "sequence-diagram", "use-case-diagram"}


def test_narrated_titles_do_not_move_a_module_or_change_a_page_path(tmp_path):
    class _Engine:
        def isAvailable(self) -> bool:
            return True

        def generate(self, prompt) -> str:
            return "Title: Sample Domain\nDescription: The sample repository's only area."

    # Wrapped in the real executor rather than passed raw: the CLI hands the
    # narrator a `FailoverExecutor`, which has no `generate` of its own, and a
    # double shaped like the engine instead of the chain is what let a narrator
    # that never once ran look tested.
    engine = FailoverExecutor("summary", ((ProviderRef("local", "test-model"), _Engine()),))

    root, store, graph = build_indexed_repo(tmp_path)
    plain = _build_generator(tmp_path, root, store, graph).generateRepositoryDocumentation(root, incremental=False)
    plain_section = next(page for page in plain.pages if page.kind == "section")

    narrated_root, narrated_store, narrated_graph = build_indexed_repo(tmp_path / "second")
    narrated = _build_generator(
        tmp_path,
        narrated_root,
        narrated_store,
        narrated_graph,
        db_name="narrated.sqlite",
        section_narrator=SectionNarrator(engine),
    ).generateRepositoryDocumentation(narrated_root, incremental=False)
    narrated_section = next(page for page in narrated.pages if page.kind == "section")

    assert narrated_section.title == "Sample Domain"
    assert "The sample repository's only area." in narrated_section.contentMarkdown
    # The page's own path is keyed on the directory, so renaming the section in
    # prose never orphans the file or the links pointing at it.
    assert narrated_section.outputPathHtml == plain_section.outputPathHtml
    # ...and it never moves a module: both runs group the same three modules.
    def _member_names(page):
        listing = page.contentMarkdown.split("## Modules in this section")[1]
        return sorted(re.findall(r"^- \[([^\]]+)\]", listing, flags=re.MULTILINE))

    assert _member_names(narrated_section) == _member_names(plain_section) == ["alpha", "beta", "gamma"]


def test_removed_module_removes_its_orphaned_section_page(tmp_path):
    root, store, graph = _two_section_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, db_name="two-section-repo.sqlite")
    generator.generateRepositoryDocumentation(root, incremental=False)

    docs_root = root / "docs"
    section_files_before = sorted(path.name for path in (docs_root / "sections").glob("*.html"))
    assert len(section_files_before) == 2

    for name in ("routes.py", "server.py"):
        (root / "web" / name).unlink()
        store.delete_source_file(root, root / "web" / name)
        graph.remove_source_file(str(root / "web" / name))

    generator.generateRepositoryDocumentation(
        root, incremental=True, changedPaths=[str(root / "web" / "routes.py"), str(root / "web" / "server.py")]
    )

    section_files_after = sorted(path.name for path in (docs_root / "sections").glob("*.html"))
    assert len(section_files_after) == 1

    repository_id = stable_repository_id(root)
    entries = generator.manifestStore.list_entries(repository_id)
    known_page_ids = {entry.pageId for entry in entries}
    for entry in entries:
        for target_page_id in entry.linkedPageIds:
            assert target_page_id in known_page_ids, f"{entry.pageId} links to the removed {target_page_id}"
