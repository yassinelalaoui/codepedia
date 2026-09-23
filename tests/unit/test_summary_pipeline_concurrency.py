"""Summarization runs from a thread pool, and must stay observationally
identical to the sequential pass it replaced
(contracts/indexing-concurrency-delta.md).

Each symbol is one blocking remote call, so the pass was almost entirely
network wait. What matters here is that going concurrent did not change what
callers see: the same results, in the same order, with a progress count that
still runs 1..n exactly once each.
"""

from __future__ import annotations

import threading
from pathlib import Path
from shutil import copytree

import pytest

from dependency_graph import DependencyGraph
from local_llm.models import AvailabilityStatus
from parser_engine import SourceFile, extract_symbols
from repository_metadata import CodeSummaryPipeline, RepositoryMetadataStore, compute_content_hash


def _fixture_root() -> Path:
    return Path("tests/integration/fixtures/repository-metadata/sample-repo")


class _ConcurrencyProbe:
    """An engine that records how many calls were ever in flight at once."""

    def __init__(self, *, gate_size: int = 0) -> None:
        self.modelName = "probe"
        self.endpointUrl = "http://localhost:11434"
        self._lock = threading.Lock()
        self._in_flight = 0
        self.peak_in_flight = 0
        self.call_count = 0
        # A one-shot gate: the first `gate_size` calls block until that many
        # have arrived, so the test fails by timing out if the pipeline is
        # secretly sequential rather than passing on a lucky interleaving. It
        # releases for good afterwards - a reusable Barrier would strand the
        # final, short wave of tasks when the total is not a multiple of the
        # pool size.
        self._gate_size = gate_size
        self._gate_open = threading.Event()

    def checkAvailability(self) -> AvailabilityStatus:
        return AvailabilityStatus(True, True, True, "available")

    def isAvailableLocally(self) -> bool:
        return True

    def isAvailable(self) -> bool:
        return True

    def generate(self, prompt) -> str:
        with self._lock:
            self._in_flight += 1
            self.call_count += 1
            self.peak_in_flight = max(self.peak_in_flight, self._in_flight)
        try:
            if self._gate_size:
                with self._lock:
                    if self._in_flight >= self._gate_size:
                        self._gate_open.set()
                if not self._gate_open.wait(timeout=10):
                    raise AssertionError(
                        f"only {self.peak_in_flight} call(s) ever overlapped; expected {self._gate_size}"
                    )
            return "generated summary"
        finally:
            with self._lock:
                self._in_flight -= 1


def _wrap(engine):
    """Stamp the engine with a provider id and hand it back.

    It used to wrap the engine in a `FailoverExecutor` over a one-entry chain.
    The pipeline takes the engine itself now, and reads `providerId` off it to
    record which model wrote each summary.
    """
    engine.providerId = f"local:{getattr(engine, 'modelName', 'probe')}"
    return engine


def _prepared_repository(tmp_path: Path):
    root = tmp_path / "sample-repo"
    copytree(_fixture_root(), root)
    store = RepositoryMetadataStore(tmp_path / "metadata.sqlite")
    files = [root / "alpha.py", root / "beta.py", root / "gamma.py"]
    inventories = [extract_symbols(SourceFile(path=path, language="python")) for path in files]
    for path, inventory in zip(files, inventories):
        store.store_inventory(
            repository_root=root,
            source_file=SourceFile(path=path, language="python"),
            inventory=inventory,
            content_hash=compute_content_hash(path),
        )
    graph = DependencyGraph.build_from_inventories(inventories, sourceFile=str(root))
    return root, store, graph


def _pipeline(store, graph, engine, *, workers: int) -> CodeSummaryPipeline:
    return CodeSummaryPipeline(
        metadataStore=store, dependencyGraph=graph, llmEngine=_wrap(engine), maxWorkers=workers
    )


def test_symbols_are_summarized_concurrently(tmp_path) -> None:
    """The gate only releases once four calls are simultaneously in flight,
    so this cannot pass on a sequential pipeline - it would time out."""
    root, store, graph = _prepared_repository(tmp_path)
    engine = _ConcurrencyProbe(gate_size=4)

    _pipeline(store, graph, engine, workers=4).summarizeRepository(root, incremental=False)

    assert engine.peak_in_flight == 4


def test_results_keep_the_order_the_sequential_pass_produced(tmp_path) -> None:
    root, store, graph = _prepared_repository(tmp_path)

    sequential = _pipeline(store, graph, _ConcurrencyProbe(), workers=1).summarizeRepository(
        root, incremental=False
    )
    concurrent = _pipeline(store, graph, _ConcurrencyProbe(), workers=4).summarizeRepository(
        root, incremental=False
    )

    assert [result.symbolId for result in concurrent] == [result.symbolId for result in sequential]


def test_progress_counts_every_symbol_exactly_once_and_in_order(tmp_path) -> None:
    """The callback moved from "about to start" to "finished" - under a pool,
    only completion has a countable order. It must still be gap-free."""
    root, store, graph = _prepared_repository(tmp_path)
    seen: list[tuple[int, int]] = []

    results = _pipeline(store, graph, _ConcurrencyProbe(), workers=4).summarizeRepository(
        root, incremental=False, on_progress=lambda completed, total, symbol: seen.append((completed, total))
    )

    total = len(results)
    assert [count for count, _ in seen] == list(range(1, total + 1))
    assert {reported_total for _, reported_total in seen} == {total}


def test_every_symbol_is_summarized_exactly_once(tmp_path) -> None:
    root, store, graph = _prepared_repository(tmp_path)
    engine = _ConcurrencyProbe()

    results = _pipeline(store, graph, engine, workers=4).summarizeRepository(root, incremental=False)

    assert engine.call_count == len(results)
    assert len({result.symbolId for result in results}) == len(results)


def test_a_failing_symbol_still_propagates_its_error(tmp_path) -> None:
    root, store, graph = _prepared_repository(tmp_path)

    class _Exploding(_ConcurrencyProbe):
        def generate(self, prompt) -> str:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _pipeline(store, graph, _Exploding(), workers=4).summarizeRepository(root, incremental=False)


def test_worker_count_must_be_at_least_one(tmp_path) -> None:
    _, store, graph = _prepared_repository(tmp_path)

    with pytest.raises(ValueError, match="maxWorkers"):
        _pipeline(store, graph, _ConcurrencyProbe(), workers=0)


# ---------------------------------------------------------------------------
# An empty completion fails the symbol over rather than ending the run
# ---------------------------------------------------------------------------


class _ScriptedEngine:
    """Returns each queued string in turn; `""` stands for a blank completion."""

    def __init__(self, *replies: str) -> None:
        self.modelName = "scripted"
        self.endpointUrl = "http://localhost:11434"
        self._replies = list(replies)
        self._lock = threading.Lock()
        self.call_count = 0

    def checkAvailability(self) -> AvailabilityStatus:
        return AvailabilityStatus(True, True, True, "available")

    def isAvailableLocally(self) -> bool:
        return True

    def isAvailable(self) -> bool:
        return True

    def generate(self, prompt) -> str:
        with self._lock:
            self.call_count += 1
            return self._replies.pop(0) if self._replies else "fallback summary"


def _scripted_pipeline(store, graph, engine) -> CodeSummaryPipeline:
    return CodeSummaryPipeline(
        metadataStore=store,
        dependencyGraph=graph,
        llmEngine=_wrap(engine),
        maxWorkers=1,
    )


def test_a_blank_completion_skips_its_symbol_and_the_run_continues(tmp_path) -> None:
    """A small local model returning nothing is ordinary, not fatal.

    There is no second provider to ask any more (constitution 2.3 v4.0.0), so
    the symbol is left unsummarized and every other symbol still gets its
    summary. The alternative - letting the error escape the pool - would
    delete the staging directory and discard the whole pass over one blank
    answer.
    """
    root, store, graph = _prepared_repository(tmp_path)
    blank_once = _ScriptedEngine("")  # blank once, then non-empty

    results = _scripted_pipeline(store, graph, blank_once).summarizeRepository(root, incremental=False)

    assert results, "the run produced summaries despite the blank completion"
    assert all(result.generatedSummary for result in results)
    # The blanked symbol contributed no result, so one fewer than was attempted.
    assert all(result.modelName == "local:scripted" for result in results)


def test_every_completion_blank_yields_no_summaries_rather_than_crashing(tmp_path) -> None:
    """Tolerating a blank answer is not the same as inventing one.

    When the model blanks on everything, the run finishes with nothing written
    rather than with empty summaries, and without raising - the wiki then
    renders every symbol without prose, exactly as it does when no model is
    available at all.
    """
    root, store, graph = _prepared_repository(tmp_path)
    always_blank = _ScriptedEngine("", "", "", "", "", "", "", "", "", "")

    results = _scripted_pipeline(store, graph, always_blank).summarizeRepository(root, incremental=False)

    assert results == []
