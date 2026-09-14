"""The Overview's subsystems section: the table, and one paragraph per major subsystem (038 US2).

A small repository of its own, because the shared alpha/beta/gamma fixture has
one module per subsystem and so cannot show "the member with the most entry
points". The planner is a stub that returns a fixed plan - the planner is 033's,
and this story only reads what it produced - and the narrator's only fake is,
as in `test_overview_page.py`, what the model says.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from doc_generator import DocGenerator, OverviewNarrator, open_doc_manifest_store
from doc_generator.features.validate import FeaturePlan, PlannedFeature

from ._doc_generator_support import index_repo, wrap_llm

SOURCES = {
    "core.py": (
        '"""Runs the work."""\n\nfrom helpers import help_one\n\n\n'
        "def run_a():\n    return help_one()\n\n\n"
        "def run_b():\n    return help_one()\n\n\n"
        "def run_c():\n    return 3\n"
    ),
    "helpers.py": '"""Small helpers."""\n\n\ndef help_one():\n    return 1\n\n\ndef help_two():\n    return 2\n',
    "store.py": '"""Keeps results."""\n\n\ndef save():\n    return 0\n',
}

CORE_TEXT = "Work starts in `run_a` in `core.py`, which calls `help_one` in `helpers.py`."
STORE_TEXT = "Results are kept by `save` in `store.py`."
OPENING = "The repository runs its work through `core.py` and keeps results in `store.py`."


class ScriptedEngine:
    def __init__(self, reply: str = "", *, available: bool = True) -> None:
        self.reply = reply
        self.available = available
        self.calls = 0
        self.modelName = "scripted"

    def isAvailable(self) -> bool:
        return self.available

    def generate(self, prompt) -> str:
        self.calls += 1
        return self.reply


class StubPlanner:
    """Groups `core` and `helpers` as one planned subsystem, `store` as another."""

    def __init__(self, descriptions: dict[str, str], kinds: dict[str, str] | None = None) -> None:
        self.descriptions = descriptions
        self.kinds = kinds or {}
        self.repositoryId = ""

    def plan(self, candidates, evidence):
        names = evidence.by_module_key()
        groups: dict[str, list[str]] = {"Core": [], "Storage": []}
        for index, candidate in enumerate(candidates):
            members = {names[key].moduleName for key in candidate.memberKeys}
            groups["Storage" if members == {"store"} else "Core"].append(f"c{index}")
        return FeaturePlan(
            features=tuple(
                PlannedFeature(
                    title=title,
                    description=self.descriptions.get(title, ""),
                    kind=self.kinds.get(title, "subsystem"),
                    memberCandidateIds=tuple(ids),
                )
                for title, ids in groups.items()
                if ids
            )
        )


def _repo(tmp_path: Path):
    root = tmp_path / "subsystems-repo"
    root.mkdir(parents=True)
    for name, text in SOURCES.items():
        (root / name).write_text(text, encoding="utf-8")
    store, graph = index_repo(tmp_path, root, [root / name for name in SOURCES], "subsystems.sqlite")
    return root, store, graph


DESCRIPTIONS = {"Core": "Runs the work through `run_a` and its helpers.", "Storage": "You keep results in `NoSuchStore`."}


def _home(tmp_path, *, reply=None, descriptions=DESCRIPTIONS, planner=True, narrator=True, name="g", engine=None, repo=None):
    root, store, graph = repo or _repo(tmp_path / name)
    manifest = open_doc_manifest_store(tmp_path / f"{name}-manifest.sqlite")
    engine = engine or ScriptedEngine(reply or json.dumps({"lead": [OPENING]}))
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest,
        outputRoot=tmp_path / f"{name}-docs",
        repositoryRoot=root,
        featurePlanner=StubPlanner(descriptions) if planner else None,
        overviewNarrator=OverviewNarrator(wrap_llm(engine), cache=manifest) if narrator else None,
    )
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)
    home = next(page for page in doc_set.pages if page.kind == "home")
    return home, generator


def _rows(markdown: str) -> list[list[str]]:
    table = markdown.split("| Subsystem |", 1)[1].split("\n\n", 1)[0]
    rows = [line for line in table.splitlines()[2:] if line.startswith("|")]
    return [[cell.strip() for cell in re.split(r"(?<!\\)\|", row)[1:-1]] for row in rows]


def _paragraphs(markdown: str) -> list[str]:
    after_table = markdown.split("| Subsystem |", 1)[1].split("## Modules", 1)[0]
    lines = after_table.splitlines()
    return [lines[index - 1] for index, line in enumerate(lines) if line == "{: .ai-generated }"]


def _reply(**subsystems: str) -> str:
    return json.dumps({"lead": [OPENING], "subsystems": subsystems})


def test_subsystems_table_lists_every_feature_once_in_navigation_order(tmp_path):
    home, generator = _home(tmp_path)
    titles = [re.match(r"\[([^\]]+)\]", row[0]).group(1) for row in _rows(home.contentMarkdown)]

    assert titles == [feature.title for feature in generator._ensure_features()]
    assert sorted(titles) == ["Core", "Storage"]
    assert "| Feature | Modules |" not in home.contentMarkdown


def test_start_with_module_belongs_to_its_subsystem_and_prefers_the_most_entry_points(tmp_path):
    home, generator = _home(tmp_path)
    features = {feature.title: feature for feature in generator._ensure_features()}
    rows = {re.match(r"\[([^\]]+)\]", row[0]).group(1): row for row in _rows(home.contentMarkdown)}

    for title, row in rows.items():
        label = re.match(r"\[([^\]]+)\]\((modules/[^)]+)\)", row[2])
        assert label, row
        assert label.group(1) in {member.name for member in features[title].members}
    # core.py has three uncalled functions, helpers.py one: core wins whatever the anchor.
    assert rows["Core"][2].startswith("[core](modules/")


def test_the_table_is_complete_without_a_provider(tmp_path):
    repo = _repo(tmp_path / "shared")
    with_provider, _ = _home(tmp_path, name="with", repo=repo, reply=_reply(f0=CORE_TEXT, f1=STORE_TEXT))
    without, _ = _home(tmp_path, name="without", repo=repo, narrator=False)

    assert with_provider.contentMarkdown.count("{: .ai-generated }") == 3, "the reference page must carry prose"

    assert _rows(without.contentMarkdown) == _rows(with_provider.contentMarkdown)
    assert "ai-generated" not in without.contentMarkdown


def test_each_paragraph_ends_with_its_subsystem_link(tmp_path):
    home, generator = _home(tmp_path, reply=_reply(f0=CORE_TEXT, f1=STORE_TEXT))
    order = [feature.title for feature in generator._ensure_features()]
    paragraphs = _paragraphs(home.contentMarkdown)

    assert len(paragraphs) == 2
    for title, paragraph in zip(order, paragraphs):
        # Set apart by an arrow: run on after the last sentence, the bare link
        # read as a stray fragment (research Decision 19).
        assert re.search(rf"\\\. → \[{title}\]\(features/[^)]+\.md\)$", paragraph), paragraph


def test_the_counts_sentence_directly_precedes_the_table_and_is_marked(tmp_path):
    """The stylesheet sets the Responsibility column in the UI font through
    `.architecture-counts + table`, so only this table changes (research
    Decision 19). This pins the sibling relationship that rule depends on."""
    home, _ = _home(tmp_path)

    assert "{: .architecture-counts }" in home.contentMarkdown
    assert re.search(r'<p class="architecture-counts">This repository has [^<]*</p>\s*<table>', home.renderedHtml)


def test_a_paragraph_for_a_subsystem_not_asked_for_is_neither_shown_nor_reported(tmp_path):
    """Tooling gets no paragraph (FR-025). When the model writes one anyway it
    is ignored, not reported as dropped (research Decision 19)."""
    root, store, graph = _repo(tmp_path / "u")
    manifest = open_doc_manifest_store(tmp_path / "u-manifest.sqlite")
    notices: list[str] = []
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest,
        outputRoot=tmp_path / "u-docs",
        repositoryRoot=root,
        featurePlanner=StubPlanner(DESCRIPTIONS, kinds={"Storage": "tooling"}),
        overviewNarrator=OverviewNarrator(wrap_llm(ScriptedEngine(_reply(f0=CORE_TEXT, f1=STORE_TEXT))), cache=manifest),
        onNotice=notices.append,
    )
    home = next(page for page in generator.generateRepositoryDocumentation(root, incremental=False).pages if page.kind == "home")

    assert [feature.title for feature in generator._ensure_features()] == ["Core", "Storage"]
    paragraphs = _paragraphs(home.contentMarkdown)
    assert len(paragraphs) == 1 and "[Core](features/" in paragraphs[0]
    assert notices == []


def _notices_for(tmp_path, reply: str) -> list[str]:
    root, store, graph = _repo(tmp_path / "n")
    manifest = open_doc_manifest_store(tmp_path / "n-manifest.sqlite")
    notices: list[str] = []
    DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest,
        outputRoot=tmp_path / "n-docs",
        repositoryRoot=root,
        featurePlanner=StubPlanner(DESCRIPTIONS),
        overviewNarrator=OverviewNarrator(wrap_llm(ScriptedEngine(reply)), cache=manifest),
        onNotice=notices.append,
    ).generateRepositoryDocumentation(root, incremental=False)
    return notices


def test_a_subsystem_paragraph_the_model_never_wrote_is_reported(tmp_path):  # FR-018
    """Asked for eight, the sample repository's reply wrote three, and nothing
    said so (research Decision 19)."""
    assert _notices_for(tmp_path, _reply(f0=CORE_TEXT)) == ["  overview: 1 of 2 subsystem paragraphs not written"]


def test_unwritten_paragraphs_share_the_line_with_dropped_ones(tmp_path):  # contract §7: one line per pass
    notices = _notices_for(tmp_path, _reply(f1="It is priced by `NoSuchEngine`."))

    assert notices == [
        "  overview: 1 of 2 narrative paragraphs dropped (named something not in the repository); "
        "1 of 2 subsystem paragraphs not written"
    ]


def test_a_withheld_paragraph_keeps_its_table_row(tmp_path):
    home, _ = _home(tmp_path, reply=_reply(f0="It is priced by `NoSuchEngine`.", f1=STORE_TEXT))

    assert len(_paragraphs(home.contentMarkdown)) == 1
    assert len(_rows(home.contentMarkdown)) == 2


def test_a_failing_description_renders_a_dash(tmp_path):
    home, _ = _home(tmp_path)
    rows = {re.match(r"\[([^\]]+)\]", row[0]).group(1): row for row in _rows(home.contentMarkdown)}

    assert rows["Storage"][1] == "—"
    assert rows["Core"][1] == "Runs the work through `run_a` and its helpers\\."


def test_generated_column_header_is_labelled_only_when_a_planned_description_is_shown(tmp_path):
    planned, _ = _home(tmp_path, name="planned")
    unplanned, _ = _home(tmp_path, name="unplanned", planner=False)
    all_failing, _ = _home(tmp_path, name="failing", descriptions={"Core": "You run it.", "Storage": "You keep it."})

    assert "| Subsystem | Responsibility (AI-generated) | Start with |" in planned.contentMarkdown
    assert "| Subsystem | Responsibility | Start with |" in unplanned.contentMarkdown
    assert "| Subsystem | Responsibility | Start with |" in all_failing.contentMarkdown


def test_the_features_list_is_gone_and_every_subsystem_is_still_reachable(tmp_path):
    home, generator = _home(tmp_path)
    feature_links = {link.relativePath for link in home.links if link.relativePath.startswith("features/")}
    table = home.contentMarkdown.split("| Subsystem |", 1)[1].split("\n\n", 1)[0]

    assert "## Features" not in home.contentMarkdown
    assert len(feature_links) == len(generator._ensure_features())
    assert all(f"]({path})" in table for path in feature_links)


def test_a_stale_page_with_a_withheld_lead_puts_the_caveat_under_the_last_subsystem_paragraph(tmp_path):
    root, store, graph = _repo(tmp_path / "s")
    manifest = open_doc_manifest_store(tmp_path / "s-manifest.sqlite")
    reply = json.dumps({"lead": ["It starts in `NoSuchThing`."], "subsystems": {"f0": CORE_TEXT, "f1": STORE_TEXT}})
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest,
        outputRoot=tmp_path / "s-docs",
        repositoryRoot=root,
        featurePlanner=StubPlanner(DESCRIPTIONS),
        overviewNarrator=OverviewNarrator(wrap_llm(ScriptedEngine(reply)), cache=manifest),
    )
    generator.generateRepositoryDocumentation(root, incremental=False)
    (root / "README.md").write_text("# Subsystems\n\nA changed self-description.\n", encoding="utf-8")
    generator.overviewNarrator.llmEngine = wrap_llm(ScriptedEngine(available=False))

    markdown = next(page for page in generator.generateRepositoryDocumentation(root, incremental=False).pages if page.kind == "home").contentMarkdown
    lines = [line for line in markdown.splitlines() if line.strip()]
    last_paragraph = max(index for index, line in enumerate(lines) if line == "{: .ai-generated }")

    assert markdown.count("{: .summary-stale }") == 1
    assert lines[last_paragraph + 2] == "{: .summary-stale }"
    assert lines.index("{: .summary-stale }") > lines.index(next(line for line in lines if line.startswith("| Subsystem |")))
