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
# The most ordinary edit there is, and the one the ledger used to miss on:
# every function below moves down a line while its bytes stay identical.
SHIFTED_DOWN_ONE_LINE = "# a note added at the top of the file\n" + THREE_FUNCTIONS


class CountingLLM:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls = 0
        self.prompts: list[str] = []

    def isAvailable(self) -> bool:
        return self.available

    def generate(self, prompt) -> str:
        self.calls += 1
        self.prompts.append(prompt.to_prompt_text())
        return f"summary #{self.calls}"


class Harness:
    def __init__(self, tmp_path: Path, source: str, root: Path | None = None) -> None:
        # `root` is shared when a test needs a second database over the *same*
        # repository, which is what a staging directory is.
        self.root = root if root is not None else tmp_path / "repo"
        self.root.mkdir(exist_ok=True)
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


def test_inserting_a_line_above_a_symbol_no_longer_expires_its_summary(harness: Harness):
    """N4, inverted into a regression.

    `context_hash` excludes `symbolId` precisely because it encodes a line
    range - and then hashed `metadata`, which carried `lineStart`/`lineEnd`.
    The volatility shut out of the front door came back through the window: one
    comment at the top of a file re-bought every summary under it.
    """
    before = {name: symbol.summaryContextHash for name, symbol in harness.functions().items()}

    harness.rewrite(SHIFTED_DOWN_ONE_LINE)
    harness.llm.calls = 0
    fresh, _stale = harness.pipeline.restoreSummariesFromLedger(harness.root, [harness.path])

    functions = harness.functions()
    assert {name: symbol.summaryContextHash for name, symbol in functions.items()} == before
    assert harness.llm.calls == 0
    assert fresh >= 3, "alpha, beta and gamma are byte-identical, only lower down the file"
    assert all(not symbol.summaryIsStale for symbol in functions.values())


def test_a_prompt_never_shows_the_model_a_line_number(harness: Harness):
    """Nothing in the prompt may be volatile for reasons the summary ignores.

    The `Metadata:` block is hashed exactly because it is shown, so this is the
    same assertion as the test above read from the other end.
    """
    assert harness.llm.prompts, "the fixture summarizes the repository once"
    for rendered in harness.llm.prompts:
        assert "lineStart" not in rendered
        assert "lineEnd" not in rendered
        assert "nestedSymbols" not in rendered


def test_prose_does_not_hash_metadata_it_is_never_shown(tmp_path: Path):
    """A documentation prompt has no `Metadata:` block at all.

    Hashing a block the prose prompt never renders can only lose ledger recall -
    2 714 Markdown symbols on this repository were paying for it.
    """
    from repository_metadata.summary_context import SummaryContext, context_hash

    def _context(suffix: str, **metadata):
        return SummaryContext(
            symbolId="sym",
            symbolKind="class",
            symbolName="Installation",
            sourceFileId="file",
            sourceFilePath=f"docs/guide{suffix}",
            sourceText="Run the installer.",
            metadata=metadata,
        )

    assert context_hash(_context(".md", anything="a")) == context_hash(_context(".md", anything="b"))
    # Code prompts do render the block, so there the two must stay distinct.
    assert context_hash(_context(".py", anything="a")) != context_hash(_context(".py", anything="b"))


# ---------------------------------------------------------------------------
# The write path, counted in connections rather than seconds.
#
# Every method of `RepositoryMetadataStore` used to open its own connection and
# close it again - and `connect` replays `ensure_schema` each time, six DDL
# statements plus three introspection-guarded migrations, before the fsync at
# close. The ledger added three of those per symbol summarized and one per
# symbol restored, in the loop the watcher runs on every save: 300 writes
# measured 4.10s that way against 0.02s sharing one connection.
# ---------------------------------------------------------------------------


def _count_connections(monkeypatch) -> list[object]:
    """Record every connection the store opens, without changing what it does."""
    import repository_metadata.store as store_module

    opened: list[object] = []
    real_connect = store_module.connect

    def counting_connect(db_path, **kwargs):
        opened.append(db_path)
        return real_connect(db_path, **kwargs)

    monkeypatch.setattr(store_module, "connect", counting_connect)
    return opened


def test_restoring_a_file_opens_one_connection_not_one_per_symbol(harness: Harness, monkeypatch):
    harness.rewrite(ONLY_ALPHA_CHANGED)
    opened = _count_connections(monkeypatch)

    fresh, stale = harness.pipeline.restoreSummariesFromLedger(harness.root, [harness.path])

    assert fresh + stale >= 3, "the restore really did write for several symbols"
    assert len(opened) == 1, "one connection for the pass, not one per ledger call"


def test_a_summary_pass_opens_one_connection_for_every_symbol_it_writes(harness: Harness, monkeypatch):
    harness.rewrite(ONLY_ALPHA_CHANGED)
    opened = _count_connections(monkeypatch)

    harness.pipeline.summarizeRepository(
        harness.root, incremental=True, changed_paths=[str(harness.path)]
    )

    # `load_repository` runs before the pass opens its session, so one call
    # outside it is expected; the pass itself must add exactly one more.
    assert len(opened) == 2, f"expected one pre-pass call plus one session, got {len(opened)}"


def test_outside_a_session_a_call_still_opens_its_own_connection(harness: Harness, monkeypatch):
    """The fallback has to stay intact: no caller is required to open a session."""
    opened = _count_connections(monkeypatch)

    harness.store.recall_summary(context_hash="nothing")
    harness.store.recall_summary(context_hash="nothing either")

    assert len(opened) == 2


def test_a_session_is_reentrant(harness: Harness, monkeypatch):
    """The incremental pipeline nests them - restore, then summarize."""
    opened = _count_connections(monkeypatch)

    with harness.store.session():
        with harness.store.session():
            harness.store.recall_summary(context_hash="nothing")
        # Still usable after the inner one exits: the connection belongs to the
        # outermost session, and closing it early would break the caller.
        harness.store.recall_summary(context_hash="nothing either")

    assert len(opened) == 1


def test_the_ledger_carries_into_a_fresh_database(tmp_path: Path):
    """What makes a full `index` affordable after the id scheme changed.

    A full run builds into an empty staging directory, so without this every
    symbol in the repository is re-summarized at the model however unchanged
    the code is. The ledger is keyed on the material the model was shown, not
    on the symbol's id, so it survives a re-keying intact.
    """
    from repository_metadata.sqlite_store import connect, copy_summary_ledger

    previous = Harness(tmp_path, THREE_FUNCTIONS)
    previous.pipeline.summarizeRepository(previous.root, incremental=False)
    assert previous.llm.calls > 0

    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    staging = Harness(staging_dir, THREE_FUNCTIONS, root=previous.root)

    connection = connect(staging_dir / "meta.sqlite")
    try:
        copied = copy_summary_ledger(connection, source_db_path=tmp_path / "meta.sqlite")
    finally:
        connection.close()
    assert copied > 0

    staging.pipeline.summarizeRepository(staging.root, incremental=False)
    assert staging.llm.calls == 0, "a carried-forward ledger must answer every symbol"


def test_copying_a_ledger_twice_adds_nothing_and_raises_nothing(tmp_path: Path):
    from repository_metadata.sqlite_store import connect, copy_summary_ledger

    previous = Harness(tmp_path, THREE_FUNCTIONS)
    previous.pipeline.summarizeRepository(previous.root, incremental=False)

    connection = connect(tmp_path / "staging.sqlite")
    try:
        first = copy_summary_ledger(connection, source_db_path=tmp_path / "meta.sqlite")
        second = copy_summary_ledger(connection, source_db_path=tmp_path / "meta.sqlite")
    finally:
        connection.close()

    assert first > 0
    assert second == 0
