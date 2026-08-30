"""The freshness ledger: what a summary was generated from, and what that buys.

Re-parsing a file deletes and re-inserts every symbol in it, so an edit to one
function used to blank - and then re-buy - the summary of every other function
in the same file. The ledger is keyed on the *content* a model was shown rather
than on symbol identity, which is what makes an unchanged symbol reusable even
though its row was destroyed and its id may have moved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dependency_graph import DependencyGraph
from parser_engine import SourceFile, extract_symbols
from provider_routing import FailoverExecutor, ProviderRef
from repository_metadata import CodeSummaryPipeline, RepositoryMetadataStore, compute_content_hash
from repository_metadata.summary_pipeline import LocalLLMUnavailableError

THREE_FUNCTIONS = (
    'def alpha():\n    """A."""\n    return 1\n\n\n'
    'def beta():\n    """B."""\n    return 2\n\n\n'
    'def gamma():\n    """G."""\n    return 3\n'
)
ONLY_ALPHA_CHANGED = THREE_FUNCTIONS.replace("return 1", "return 999")


class CountingLLM:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls = 0

    def isAvailable(self) -> bool:
        return self.available

    def generate(self, prompt) -> str:
        self.calls += 1
        return f"summary #{self.calls}"


class Harness:
    def __init__(self, tmp_path: Path, source: str) -> None:
        self.root = tmp_path / "repo"
        self.root.mkdir()
        self.path = self.root / "app.py"
        self.path.write_text(source, encoding="utf-8")
        self.store = RepositoryMetadataStore(tmp_path / "meta.sqlite")
        self.store.ensure_repository(self.root, detected_languages=("python",))
        self.llm = CountingLLM()
        graph = self.reparse()
        self.pipeline = CodeSummaryPipeline(
            metadataStore=self.store,
            dependencyGraph=graph,
            llmEngine=FailoverExecutor("summary", [(ProviderRef(kind="groq", model="m"), self.llm)]),
            maxWorkers=1,
        )

    def reparse(self) -> DependencyGraph:
        inventory = extract_symbols(SourceFile(path=self.path, language="python"))
        self.store.store_inventory(
            repository_root=self.root,
            source_file=SourceFile(path=self.path, language="python"),
            inventory=inventory,
            dependency_edges=[],
            content_hash=compute_content_hash(self.path),
        )
        graph = DependencyGraph.build_from_inventories([inventory], sourceFile=str(self.root))
        if hasattr(self, "pipeline"):
            self.pipeline.dependencyGraph = graph
        return graph

    def rewrite(self, source: str) -> None:
        self.path.write_text(source, encoding="utf-8")
        self.reparse()

    def functions(self):
        bundle = self.store.load_source_file(repository_root=self.root, path=self.path)
        return {symbol.name: symbol for symbol in bundle.functions}


@pytest.fixture()
def harness(tmp_path: Path) -> Harness:
    built = Harness(tmp_path, THREE_FUNCTIONS)
    built.pipeline.summarizeRepository(built.root, incremental=False)
    return built


def test_reparsing_blanks_every_summary_in_the_file(harness: Harness):
    """The behaviour the ledger exists to repair, pinned so it stays visible."""
    harness.rewrite(ONLY_ALPHA_CHANGED)
    assert all(symbol.generatedSummary == "" for symbol in harness.functions().values())


def test_unchanged_symbols_are_restored_without_calling_a_model(harness: Harness):
    harness.rewrite(ONLY_ALPHA_CHANGED)
    harness.llm.calls = 0

    fresh, stale = harness.pipeline.restoreSummariesFromLedger(harness.root, [harness.path])

    assert harness.llm.calls == 0, "restoring from the ledger must never reach a provider"
    assert fresh == 2, "beta and gamma are byte-identical and come back fresh"
    functions = harness.functions()
    assert functions["beta"].generatedSummary != ""
    assert functions["beta"].summaryIsStale is False
    assert functions["gamma"].summaryIsStale is False
    assert stale >= 1


def test_a_changed_symbol_comes_back_marked_stale(harness: Harness):
    harness.rewrite(ONLY_ALPHA_CHANGED)
    harness.pipeline.restoreSummariesFromLedger(harness.root, [harness.path])

    alpha = harness.functions()["alpha"]
    assert alpha.generatedSummary != "", "a stale summary still beats a blank page"
    assert alpha.summaryIsStale is True


def test_summarizing_after_a_restore_only_pays_for_what_changed(harness: Harness):
    harness.rewrite(ONLY_ALPHA_CHANGED)
    harness.pipeline.restoreSummariesFromLedger(harness.root, [harness.path])
    harness.llm.calls = 0

    harness.pipeline.summarizeRepository(harness.root, incremental=True, changed_paths=[str(harness.path)])

    # alpha and the module both changed; beta and gamma are served by the ledger.
    assert harness.llm.calls == 2
    assert all(not symbol.summaryIsStale for symbol in harness.functions().values())


def test_re_summarizing_unchanged_content_costs_nothing(harness: Harness):
    harness.llm.calls = 0
    harness.pipeline.summarizeRepository(harness.root, incremental=False)
    assert harness.llm.calls == 0


def test_an_unreachable_provider_no_longer_blanks_the_file(harness: Harness):
    harness.rewrite(ONLY_ALPHA_CHANGED)
    harness.llm.available = False

    fresh, stale = harness.pipeline.restoreSummariesFromLedger(harness.root, [harness.path])
    with pytest.raises(LocalLLMUnavailableError):
        harness.pipeline.summarizeRepository(harness.root, incremental=True, changed_paths=[str(harness.path)])

    assert fresh + stale > 0
    assert all(symbol.generatedSummary != "" for symbol in harness.functions().values())


def test_a_summary_records_the_content_it_was_generated_from(harness: Harness):
    beta = harness.functions()["beta"]
    assert beta.summaryContextHash != ""
    assert beta.summaryIsStale is False


def test_the_context_hash_ignores_the_store_timestamp(tmp_path: Path):
    """Re-storing an unchanged file must not change what its symbols hash to.

    `SourceFile.lastModified` is `datetime.now()` on every store and used to be
    part of the hashed context, which silently made every ledger lookup a miss.
    """
    built = Harness(tmp_path, THREE_FUNCTIONS)
    built.pipeline.summarizeRepository(built.root, incremental=False)
    before = {name: symbol.summaryContextHash for name, symbol in built.functions().items()}

    built.reparse()  # same bytes, new lastModified
    built.pipeline.restoreSummariesFromLedger(built.root, [built.path])

    after = {name: symbol.summaryContextHash for name, symbol in built.functions().items()}
    assert after == before
    assert all(not symbol.summaryIsStale for symbol in built.functions().values())
