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

from ._doc_generator_support import build_indexed_repo, index_repo


class _PlanningEngine:
    """An LLM engine that answers with whatever it is told."""

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

    def generate(self, prompt):
        self.calls += 1
        return self._reply()


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


def _commands(count: int) -> str:
    return "".join(f"\n\n@app.command()\ndef command_{index}() -> int:\n    return {index}\n" for index in range(count))


def _moving_repo(root: Path, *, core_commands: bool, util_commands: int = 0) -> list[Path]:
    """`cli` (a `main`) reaches `core`, which reaches `util`; `extra` imports `core`.

    With `core_commands`, `core` also holds two commands, so under 039 FR-010 it
    outranks `cli` as the feature's anchor: the regrouping the upgrade causes.
    With `util_commands` above two, `util` outranks both.
    """
    sources = {
        "app/cli.py": '"""CLI."""\n\nfrom .core import core_run\n\n\ndef main() -> int:\n    return core_run()\n',
        "app/core.py": '"""Core."""\n\nfrom .util import helper\n\n\ndef core_run() -> int:\n    return helper()\n'
        + _commands(2 if core_commands else 0),
        "app/util.py": '"""Util."""\n\n\ndef helper() -> int:\n    return 1\n' + _commands(util_commands),
        "app/extra.py": '"""Extra."""\n\nfrom .core import core_run\n\n\ndef _e() -> int:\n    return core_run()\n',
    }
    paths = []
    for relative, text in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths


def test_an_address_published_before_regrouping_still_resolves(tmp_path):
    """039 FR-011: an anchor moved by the new anchor rule leaves a redirect (033 FR-020, FR-021).

    Run 1 anchors the one feature at `cli`, its only entry module. Run 2 gives
    `core` two commands, so the same modules are anchored at `core`: a new
    address. The old one must lead to the feature now holding its modules, and
    the alias table must say so.
    """
    root = tmp_path / "moving"
    store, graph = index_repo(tmp_path, root, _moving_repo(root, core_commands=False), "run1.sqlite")
    manifest_store = open_doc_manifest_store(tmp_path / "manifest.sqlite")
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=root / "docs",
        repositoryRoot=root,
    )
    first = generator.generateRepositoryDocumentation(root, incremental=False)
    old_page = next(page for page in first.pages if page.kind == "feature" and "cli" in page.outputPathHtml)

    store, graph = index_repo(tmp_path, root, _moving_repo(root, core_commands=True), "run2.sqlite")
    generator.metadataStore, generator.dependencyGraph = store, graph
    generator._bundle = None
    generator._features = None
    second = generator.generateRepositoryDocumentation(root, incremental=False)

    new_page = next(page for page in second.pages if page.kind == "feature")
    assert new_page.outputPathHtml != old_page.outputPathHtml, "the fixture must move the anchor"
    assert "core" in new_page.outputPathHtml

    stub = root / "docs" / old_page.outputPathHtml
    body = stub.read_text(encoding="utf-8")
    assert 'http-equiv="refresh"' in body
    target = body.split("url=")[1].split('"')[0]
    assert (stub.parent / target).resolve() == (root / "docs" / new_page.outputPathHtml).resolve()

    aliases = generator.manifestStore.list_aliases(generator.repositoryId)
    assert any(alias.oldPageId == old_page.id and alias.newPageId == new_page.id for alias in aliases), aliases


def _stub_target(stub: Path) -> Path:
    body = stub.read_text(encoding="utf-8")
    assert 'http-equiv="refresh"' in body, f"{stub.name} is not a redirect"
    return (stub.parent / body.split("url=")[1].split('"')[0]).resolve()


def test_every_published_address_survives_repeated_full_rebuilds(tmp_path):
    """039 T036a (SC-008, FR-011): what `codepedia index` does, three times.

    `index` builds each wiki into a fresh directory and carries only the page
    manifest forward. Measured at T036: the second full re-index after a regroup
    lost every redirect stub the first one wrote, and an alias whose target moved
    again kept pointing at a page that no longer existed. Here the anchor moves
    twice - `cli`, then `core`, then `util` - and both earlier addresses must
    lead to the page live now.
    """
    import shutil

    root = tmp_path / "moving"
    states = [
        {"core_commands": False},
        {"core_commands": True},
        {"core_commands": True, "util_commands": 3},
    ]
    published: list[str] = []
    generator = None
    for run, state in enumerate(states):
        store, graph = index_repo(tmp_path, root, _moving_repo(root, **state), f"run{run}.sqlite")
        manifest_path = tmp_path / f"manifest-{run}.sqlite"
        if run:
            shutil.copy2(tmp_path / f"manifest-{run - 1}.sqlite", manifest_path)
        generator = DocGenerator(
            metadataStore=store,
            dependencyGraph=graph,
            manifestStore=open_doc_manifest_store(manifest_path),
            outputRoot=tmp_path / f"docs-{run}",
            repositoryRoot=root,
        )
        result = generator.generateRepositoryDocumentation(root, incremental=False)
        feature_pages = [page for page in result.pages if page.kind == "feature"]
        assert len(feature_pages) == 1, "the fixture holds one feature"
        published.append(feature_pages[0].outputPathHtml)

    assert len(set(published)) == 3, f"the fixture must move the anchor twice: {published}"
    docs = tmp_path / "docs-2"
    live = (docs / published[-1]).resolve()
    for old in published[:-1]:
        stub = docs / old
        assert stub.exists(), f"{old} was lost by a later full rebuild"
        assert _stub_target(stub) == live, f"{old} does not lead to the page live now"

    aliases = {alias.oldPageId: alias.newPageId for alias in generator.manifestStore.list_aliases(generator.repositoryId)}
    assert len(set(aliases.values())) == 1, f"a chain of moves collapses to where it ended: {aliases}"
