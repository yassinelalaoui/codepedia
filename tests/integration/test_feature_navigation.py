"""A renamed feature has to reach the pages that did not otherwise change.

The planner names features, and the sidebar carrying those names is rendered
into every page. So a rename is a repository-wide event even though it moves no
page id - which is precisely the case the incremental path used to miss.

Carried over from `test_section_navigation.py`. The invariant is unchanged; what
changed is that one call now names the *whole* set rather than one call per
group, and the cache is keyed on the repository's structure rather than on one
group's membership.
"""

from __future__ import annotations

import json
from pathlib import Path

from doc_generator import DocGenerator, FeaturePlanner, open_doc_manifest_store

from ._doc_generator_support import build_indexed_repo


class _PlanningEngine:
    """A `FailoverExecutor`-shaped engine that answers with whatever it is told."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.calls = 0

    def isAvailable(self) -> bool:
        return True

    def _reply(self) -> str:
        # Two features, because a plan that collapses to one is rejected
        # wholesale - `MIN_PLANNED_FEATURES`.
        return json.dumps(
            [
                {
                    "title": self.title,
                    "description": "Whatever this area does.",
                    "kind": "capability",
                    "memberCandidateIds": ["c0"],
                },
                {
                    "title": f"{self.title} Support",
                    "description": "The rest of it.",
                    "kind": "tooling",
                    "memberCandidateIds": ["c1", "c2", "c3", "c4"],
                },
            ]
        )

    def run(self, call):
        outer = self

        class _Inner:
            def generate(self, prompt):
                outer.calls += 1
                return outer._reply()

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
        featurePlanner=FeaturePlanner(engine, cache=manifest_store),
    )


def test_a_renamed_feature_reaches_pages_that_did_not_change(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    engine = _PlanningEngine("Area One")
    generator = _generator(tmp_path, root, store, graph, engine)

    first = generator.generateRepositoryDocumentation(root, incremental=False)
    assert engine.calls == 1, "one call for the whole plan, not one per feature"

    untouched_page = next(
        page for page in first.pages if page.kind == "module" and "gamma" in page.outputPathHtml
    )
    assert "Area One" in (root / "docs" / untouched_page.outputPathHtml).read_text(encoding="utf-8")

    # What a re-plan looks like from the planner's side: the cached plan no
    # longer matches the structure being rendered, so the model is asked again
    # and can answer with different names.
    generator.manifestStore.save_feature_plan(generator.repositoryId, "a-stale-plan-key", [])
    engine.title = "Area Two"

    generator.generateRepositoryDocumentation(
        root, incremental=True, changedPaths=[str(root / "alpha.py")]
    )

    html = (root / "docs" / untouched_page.outputPathHtml).read_text(encoding="utf-8")
    assert "Area Two" in html
    assert "Area One" not in html, "gamma.py did not change, and its sidebar still has to be right"


def test_regenerating_an_unchanged_repository_consults_no_model(tmp_path):
    """The cache is what turns "one call per plan" into "one call per structure".

    Without it, the two regenerations `doc_generator` performs per index - once
    for structure, once after summaries land - would each spend a call, and so
    would every incremental run afterwards.
    """
    root, store, graph = build_indexed_repo(tmp_path)
    engine = _PlanningEngine("Area One")
    generator = _generator(tmp_path, root, store, graph, engine)

    generator.generateRepositoryDocumentation(root, incremental=False)
    calls_after_first = engine.calls

    generator._features = None  # a fresh run over the same, unchanged repository
    generator.generateRepositoryDocumentation(root, incremental=False)

    assert engine.calls == calls_after_first, "the second pass must reuse the cached plan"
