"""A renamed section has to reach the pages that did not otherwise change.

The narrator names sections, and the sidebar carrying those names is rendered
into every page. So a rename is a repository-wide event even though it moves no
page id - which is precisely the case the incremental path used to miss.
"""

from __future__ import annotations

from pathlib import Path

from doc_generator import DocGenerator, SectionNarrator, open_doc_manifest_store

from ._doc_generator_support import build_indexed_repo


class _NamingEngine:
    """A `FailoverExecutor`-shaped engine that answers with whatever it is told."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.calls = 0

    def isAvailable(self) -> bool:
        return True

    def run(self, call):
        class _Inner:
            def generate(inner_self, prompt):  # noqa: N805 - test double
                self.calls += 1
                return f"Title: {self.title}\nDescription: Whatever this area does."

        class _Result:
            value = call(_Inner())

        return _Result()


def _generator(tmp_path: Path, root: Path, store, graph, engine) -> DocGenerator:
    manifest_store = open_doc_manifest_store(tmp_path / "manifest.sqlite")
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=root / "docs",
        repositoryRoot=root,
        sectionNarrator=SectionNarrator(engine, cache=manifest_store),
    )


def test_a_renamed_section_reaches_pages_that_did_not_change(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    engine = _NamingEngine("Area One")
    generator = _generator(tmp_path, root, store, graph, engine)

    first = generator.generateRepositoryDocumentation(root, incremental=False)
    assert engine.calls == 1, "one call per section, and the fixture repo is one flat section"
    untouched_page = next(page for page in first.pages if page.kind == "module" and "gamma" in page.outputPathHtml)
    assert "Area One" in (root / "docs" / untouched_page.outputPathHtml).read_text(encoding="utf-8")

    # What a membership change looks like from the narrator's side: the cached
    # row no longer matches the section being rendered, so the model is asked
    # again and can answer with a different name.
    manifest_store = generator.manifestStore
    for section_key, title in manifest_store.list_section_titles(generator.repositoryId).items():
        manifest_store.save_section_narration(
            generator.repositoryId, section_key, "a-stale-membership-hash", title=title, description=""
        )
    engine.title = "Area Two"

    generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(root / "alpha.py")])

    html = (root / "docs" / untouched_page.outputPathHtml).read_text(encoding="utf-8")
    assert "Area Two" in html
    assert "Area One" not in html, "gamma.py did not change, and its sidebar still has to be right"
