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
from provider_routing import FailoverExecutor, ProviderRef
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


def _wrap(engine) -> FailoverExecutor:
    return FailoverExecutor("summary", ((ProviderRef.parse("local:probe"), engine),))


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


def _two_provider_pipeline(store, graph, first, second) -> CodeSummaryPipeline:
    chain = ((ProviderRef.parse("local:blank"), first), (ProviderRef.parse("groq:real"), second))
    return CodeSummaryPipeline(
        metadataStore=store,
        dependencyGraph=graph,
        llmEngine=FailoverExecutor("summary", chain),
        maxWorkers=1,
    )


def test_a_blank_completion_fails_over_to_the_next_provider(tmp_path) -> None:
    """A small local model returning nothing is ordinary, not fatal: the chain
    asks the next provider for that symbol and the run continues."""
    root, store, graph = _prepared_repository(tmp_path)
    blank = _ScriptedEngine("")  # blank once, then non-empty
    real = _ScriptedEngine()

    results = _two_provider_pipeline(store, graph, blank, real).summarizeRepository(
        root, incremental=False
    )

    assert len(results) > 1  # the run finished every symbol, not just the first
    assert all(result.generatedSummary for result in results)
    assert real.call_count == 1  # exactly the one symbol the local model blanked
    assert results[0].modelName == "groq:real"
    assert results[1].modelName == "local:blank"


def test_a_blank_completion_from_every_provider_still_raises(tmp_path) -> None:
    """Failover is not silent tolerance - if nobody produces text, the run
    still fails rather than writing an empty summary."""
    root, store, graph = _prepared_repository(tmp_path)

    with pytest.raises(Exception) as excinfo:
        _two_provider_pipeline(
            store, graph, _ScriptedEngine(""), _ScriptedEngine("")
        ).summarizeRepository(root, incremental=False)

    assert "empty_response" in str(excinfo.value)
