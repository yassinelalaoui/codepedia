"""The Overview page with a narrative, without one, and across reruns (038 US1).

Real generator, real manifest store, real `FailoverExecutor` around scripted
engines - the only fake is what the model says. The two tests the runbook
requires by name are `test_no_engine_page_has_the_same_outline` and
`test_unchanged_repository_regenerates_identical_markdown`.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from dependency_graph import DependencyGraph
from parser_engine import SourceFile, extract_symbols
from repository_metadata import DependencyEdge, RepositoryMetadataStore, compute_content_hash
from repository_metadata.sqlite_store import stable_repository_id, stable_source_file_id

from doc_generator import DocGenerator, OverviewNarrator, open_doc_manifest_store

from ._doc_generator_support import build_indexed_repo, wrap_llm

OPENING = "The sample repository is used through `alpha_entry` in `alpha.py`, which hands work to [[f0]]."
FLOW = "Work then reaches `beta_helper` in `beta.py`, and values come from `shared_value` in `gamma.py`."


class ScriptedEngine:
    """An engine whose reply is fixed and whose calls are counted."""

    def __init__(self, reply: str = "", *, available: bool = True, raises: Exception | None = None) -> None:
        self.reply = reply
        self.available = available
        self.raises = raises
        self.calls = 0
        self.modelName = "scripted"

    def isAvailable(self) -> bool:
        return self.available

    def generate(self, prompt) -> str:
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.reply


def _reply(*lead: str) -> str:
    return json.dumps({"lead": list(lead)})


def _full_reply(*lead: str) -> str:
    """A lead plus a paragraph for each of the fixture's three subsystems, so
    nothing asked for is left unwritten (research Decision 19)."""
    subsystems = {f"f{index}": "Its code sits in `alpha.py`." for index in range(3)}
    return json.dumps({"lead": list(lead), "subsystems": subsystems})


def _generator(tmp_path: Path, name: str, root, store, graph, engine=None, *, narrator=True, notices=None):
    manifest = open_doc_manifest_store(tmp_path / f"{name}-manifest.sqlite")
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest,
        outputRoot=tmp_path / f"{name}-docs",
        repositoryRoot=root,
        overviewNarrator=OverviewNarrator(wrap_llm(engine), cache=manifest) if narrator else None,
        onNotice=notices.append if notices is not None else None,
    )


def _home(doc_set):
    return next(page for page in doc_set.pages if page.kind == "home")


class _Outline(HTMLParser):
    """Headings, and every href outside a generated block."""

    def __init__(self) -> None:
        super().__init__()
        self.headings: list[str] = []
        self.hrefs: set[str] = set()
        self.generated_blocks = 0
        self._stack: list[tuple[str, bool]] = []
        self._heading: list[str] | None = None

    @property
    def _inside_generated(self) -> bool:
        return any(generated for _, generated in self._stack)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        generated = "ai-generated" in (attributes.get("class") or "").split()
        if generated:
            self.generated_blocks += 1
        if tag not in {"br", "img", "meta", "link", "input", "hr"}:
            self._stack.append((tag, generated))
        if tag == "a" and "href" in attributes and not self._inside_generated:
            self.hrefs.add(attributes["href"])
        if re.fullmatch(r"h[1-6]", tag):
            self._heading = []

    def handle_endtag(self, tag):
        if self._heading is not None and re.fullmatch(r"h[1-6]", tag):
            self.headings.append("".join(self._heading).strip())
            self._heading = None
        while self._stack:
            open_tag, _ = self._stack.pop()
            if open_tag == tag:
                break

    def handle_data(self, data):
        if self._heading is not None:
            self._heading.append(data)


def _outline(html: str) -> _Outline:
    parser = _Outline()
    parser.feed(html)
    return parser


def _reindex(tmp_path: Path, root: Path, store: RepositoryMetadataStore) -> DependencyGraph:
    files = [root / "alpha.py", root / "beta.py", root / "gamma.py"]
    inventories = [extract_symbols(SourceFile(path=path, language="python")) for path in files]
    graph = DependencyGraph.build_from_inventories(inventories, sourceFile=str(root))
    repository_id = stable_repository_id(root)
    edges = [
        DependencyEdge(
            sourceId=edge.sourceId,
            targetId=edge.targetId,
            type=edge.type,
            sourceFileId=stable_source_file_id(repository_id, edge.sourceFile or root),
            metadata=dict(edge.metadata),
        )
        for edge in graph.edges.values()
    ]
    for inventory in inventories:
        source_path = Path(inventory.sourceFile)
        store.store_inventory(
            repository_root=root,
            source_file=SourceFile(path=source_path, language="python"),
            inventory=inventory,
            dependency_edges=edges,
            content_hash=compute_content_hash(source_path),
        )
    return graph


# --------------------------------------------------------------------------
# FR-014 / SC-004 — no provider: same outline, prose absent, nothing in its place
# --------------------------------------------------------------------------


NO_PROVIDER_CASES = {
    "not-configured": dict(narrator=False),
    "unreachable": dict(engine=ScriptedEngine(_reply(OPENING), available=False)),
    "chain-exhausted": dict(engine=ScriptedEngine(raises=RuntimeError("every provider failed"))),
    "refused": dict(engine=ScriptedEngine("")),
    "unusable": dict(engine=ScriptedEngine("I cannot help with that.")),
}


@pytest.mark.parametrize("case", sorted(NO_PROVIDER_CASES))
def test_no_engine_page_has_the_same_outline(tmp_path, case):
    """Each no-provider page is built on a fresh manifest with no narrative row.

    Otherwise the narrator would rightly answer from its cache (FR-015/016) or
    from the earlier narrative (FR-017a), and prose would appear.
    """
    root, store, graph = build_indexed_repo(tmp_path)
    with_provider = _home(
        _generator(tmp_path, "with", root, store, graph, ScriptedEngine(_reply(OPENING, FLOW))).generateRepositoryDocumentation(
            root, incremental=False
        )
    )
    options = NO_PROVIDER_CASES[case]
    without = _home(
        _generator(tmp_path, f"without-{case}", root, store, graph, options.get("engine"), narrator=options.get("narrator", True))
        .generateRepositoryDocumentation(root, incremental=False)
    )

    reference, degraded = _outline(with_provider.renderedHtml), _outline(without.renderedHtml)
    assert reference.generated_blocks == 2, "the reference page must actually carry prose"
    assert degraded.headings == reference.headings
    assert degraded.hrefs == reference.hrefs
    assert degraded.generated_blocks == 0
    assert "ai-generated" not in without.contentMarkdown
    assert "summary-stale" not in without.contentMarkdown
    # Nothing stands where the prose was: the title is followed by the facts.
    body = [line for line in without.contentMarkdown.splitlines() if line.strip()]
    assert body[1].startswith("- Repository root:")


def test_an_already_narrated_unchanged_repository_keeps_its_prose_without_a_provider(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    engine = ScriptedEngine(_reply(OPENING, FLOW))
    generator = _generator(tmp_path, "g", root, store, graph, engine)
    first = _home(generator.generateRepositoryDocumentation(root, incremental=False)).contentMarkdown
    engine.available = False

    second = _home(generator.generateRepositoryDocumentation(root, incremental=False)).contentMarkdown

    assert second == first
    assert engine.calls == 1


# --------------------------------------------------------------------------
# FR-015 / SC-005 — an unchanged repository regenerates identical Markdown
# --------------------------------------------------------------------------


def test_unchanged_repository_regenerates_identical_markdown(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    engine = ScriptedEngine(_reply(OPENING, FLOW))
    generator = _generator(tmp_path, "g", root, store, graph, engine)
    index_md = tmp_path / "g-docs" / "index.md"

    generator.generateRepositoryDocumentation(root, incremental=False)
    first = index_md.read_bytes()
    generator.generateRepositoryDocumentation(root, incremental=False)
    second = index_md.read_bytes()

    assert second == first
    assert engine.calls == 1, "the second run must answer from the cache, not the model"
    assert b"ai-generated" in first


def test_incremental_pass_on_an_unchanged_repository_does_not_rewrite_home(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, "g", root, store, graph, ScriptedEngine(_reply(OPENING, FLOW)))
    generator.generateRepositoryDocumentation(root, incremental=False)
    index_html = tmp_path / "g-docs" / "index.html"
    before = index_html.stat().st_mtime_ns

    doc_set = generator.generateRepositoryDocumentation(root, incremental=True)

    assert all(page.kind != "home" for page in doc_set.pages)
    assert index_html.stat().st_mtime_ns == before


# --------------------------------------------------------------------------
# FR-017 / FR-017a — the page follows the repository
# --------------------------------------------------------------------------


def test_removed_symbol_drops_its_paragraph_on_the_next_incremental_pass(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _generator(tmp_path, "g", root, store, graph, ScriptedEngine(_reply(OPENING, FLOW)))
    first = _home(generator.generateRepositoryDocumentation(root, incremental=False)).contentMarkdown
    assert "shared\\_value" in first or "shared_value" in first

    gamma = root / "gamma.py"
    gamma.write_text('"""Gamma module."""\n\n\nclass BaseThing:\n    """Base thing."""\n', encoding="utf-8")
    generator.dependencyGraph = _reindex(tmp_path, root, store)

    doc_set = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[gamma])
    home = _home(doc_set)

    assert "shared_value" not in home.contentMarkdown
    assert "alpha\\_entry" in home.contentMarkdown or "alpha_entry" in home.contentMarkdown


def test_changed_repository_without_provider_shows_the_earlier_narrative_marked_stale(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    notices: list[str] = []
    generator = _generator(tmp_path, "g", root, store, graph, ScriptedEngine(_reply(OPENING, FLOW)), notices=notices)
    generator.generateRepositoryDocumentation(root, incremental=False)

    (root / "README.md").write_text("# Sample\n\nThe sample repository demonstrates imports.\n", encoding="utf-8")
    generator.overviewNarrator.llmEngine = wrap_llm(ScriptedEngine(available=False))
    home = _home(generator.generateRepositoryDocumentation(root, incremental=False))

    assert home.contentMarkdown.count("{: .ai-generated }") == 2
    assert "{: .summary-stale }" in home.contentMarkdown
    assert notices[-1] == (
        "  overview: showing the narrative from an earlier version (no provider could answer); 2 of 2 paragraphs still apply"
    )


def test_a_prompt_change_on_an_unchanged_repository_is_not_marked_stale(tmp_path, monkeypatch):
    """Analyze finding I2. A new format version or a reworded prompt misses the
    cache for a repository that did not change; with no provider, its narrative
    still describes it exactly, so no "earlier version" caveat is shown."""
    import doc_generator.overview.narrator as narrator_module

    root, store, graph = build_indexed_repo(tmp_path)
    notices: list[str] = []
    generator = _generator(tmp_path, "g", root, store, graph, ScriptedEngine(_reply(OPENING, FLOW)), notices=notices)
    first = _home(generator.generateRepositoryDocumentation(root, incremental=False)).contentMarkdown

    monkeypatch.setattr(narrator_module, "NARRATIVE_FORMAT_VERSION", "next")
    generator.overviewNarrator.llmEngine = wrap_llm(ScriptedEngine(available=False))
    second = _home(generator.generateRepositoryDocumentation(root, incremental=False)).contentMarkdown

    assert second == first
    assert "summary-stale" not in second
    assert notices[-1] == (
        "  overview: showing the narrative written for an earlier prompt (no provider could answer); "
        "2 of 2 paragraphs still apply"
    )


def test_the_structure_pass_does_not_narrate(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    engine = ScriptedEngine(_reply(OPENING))
    notices: list[str] = []
    home = _home(
        _generator(tmp_path, "g", root, store, graph, engine, notices=notices).generateRepositoryDocumentation(
            root, incremental=False, narrateOverview=False
        )
    )

    assert engine.calls == 0
    assert "ai-generated" not in home.contentMarkdown
    assert notices == []


# --------------------------------------------------------------------------
# FR-018 — the terminal says what the page cannot (contract §7)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("engine", "narrator", "expected"),
    [
        (None, False, "  overview: narrative omitted (no provider configured)"),
        (ScriptedEngine(available=False), True, "  overview: narrative omitted (no provider could answer)"),
        (ScriptedEngine(raises=RuntimeError("down")), True, "  overview: narrative omitted (no provider could answer)"),
        (ScriptedEngine("nope"), True, "  overview: narrative omitted (the reply could not be read)"),
        (
            ScriptedEngine(_reply(OPENING, "It stores loans with `LoanStore`.")),
            True,
            "  overview: 1 of 2 narrative paragraphs dropped (named something not in the repository); "
            "3 of 3 subsystem paragraphs not written",
        ),
        (
            ScriptedEngine(_reply("It begins in `NoSuchThing`.", FLOW)),
            True,
            "  overview: narrative lead withheld (its opening paragraph named something not in the repository); "
            "3 of 3 subsystem paragraphs not written",
        ),
        (ScriptedEngine(_reply(OPENING, FLOW)), True, "  overview: 3 of 3 subsystem paragraphs not written"),
        (ScriptedEngine(_full_reply(OPENING, FLOW)), True, None),
    ],
    ids=["not-configured", "unreachable", "failed", "unparseable", "partial", "opening-withheld", "lead-only", "clean"],
)
def test_on_notice_receives_the_contract_line_for_each_outcome(tmp_path, engine, narrator, expected):
    root, store, graph = build_indexed_repo(tmp_path)
    notices: list[str] = []
    _generator(tmp_path, "g", root, store, graph, engine, narrator=narrator, notices=notices).generateRepositoryDocumentation(
        root, incremental=False
    )

    assert notices == ([expected] if expected else [])


def test_no_subsystems_means_no_lead_and_a_skip_notice(tmp_path):
    root = tmp_path / "empty-repo"
    root.mkdir()
    store = RepositoryMetadataStore(tmp_path / "repo.sqlite")
    store.ensure_repository(root, detected_languages=("python",))
    graph = DependencyGraph.build_from_inventories([], sourceFile=str(root))
    engine = ScriptedEngine(_reply(OPENING))
    notices: list[str] = []

    home = _home(_generator(tmp_path, "g", root, store, graph, engine, notices=notices).generateRepositoryDocumentation(root, incremental=False))

    assert "ai-generated" not in home.contentMarkdown
    assert engine.calls == 0
    assert notices == ["  overview: narrative skipped (no subsystems to describe)"]


# --------------------------------------------------------------------------
# Page shape — FR-001, FR-003b, FR-012a, FR-011
# --------------------------------------------------------------------------


def test_the_lead_precedes_every_list_table_and_diagram(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    home = _home(_generator(tmp_path, "g", root, store, graph, ScriptedEngine(_reply(OPENING, FLOW))).generateRepositoryDocumentation(root, incremental=False))
    lines = [line for line in home.contentMarkdown.splitlines() if line.strip()]

    assert lines[0].startswith("# ")
    assert lines[1].startswith("The sample repository is used through")
    assert lines[2] == "{: .ai-generated }"
    first_structure = next(index for index, line in enumerate(lines) if line.startswith(("- ", "|", "```", "[View")))
    last_lead = max(index for index, line in enumerate(lines) if line == "{: .ai-generated }")
    assert last_lead < first_structure


def test_every_backticked_name_in_the_lead_renders_as_a_link(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    home = _home(_generator(tmp_path, "g", root, store, graph, ScriptedEngine(_reply(OPENING, FLOW))).generateRepositoryDocumentation(root, incremental=False))
    paragraphs = re.findall(r'<p class="ai-generated">(.*?)</p>', home.renderedHtml, re.DOTALL)

    assert len(paragraphs) == 2
    for paragraph in paragraphs:
        codes = paragraph.count("<code>")
        assert codes > 0
        assert len(re.findall(r'<a class="symbol-ref"[^>]*><code>', paragraph)) == codes, paragraph
    # The subsystem handle became a link to that feature's page.
    assert re.search(r'<a href="features/[^"]+">', paragraphs[0])


def test_home_has_no_inline_mermaid_and_no_last_indexed_line(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    home = _home(_generator(tmp_path, "g", root, store, graph, ScriptedEngine(_reply(OPENING))).generateRepositoryDocumentation(root, incremental=False))

    assert "```mermaid" not in home.contentMarkdown
    assert "Last indexed" not in home.contentMarkdown
    assert "[View the repository class diagram]" in home.contentMarkdown
