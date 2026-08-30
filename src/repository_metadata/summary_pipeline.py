from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from dependency_graph import DependencyGraph
from parser_engine import FunctionSymbol, ModuleSymbol, Symbol

from .models import SourceFileBundle
from .store import RepositoryMetadataStore
from .summary_context import (
    ImpactedSymbolSet,
    SummaryContext,
    SummaryResult,
    SymbolSummaryJob,
    build_summary_context,
    build_summary_job,
    context_hash,
)
from .summary_prompts import (
    build_class_summary_prompt,
    build_function_summary_prompt,
    build_module_summary_prompt,
    build_prose_summary_prompt,
)

# Kept local rather than imported from `doc_generator`, which sits above this
# package in the dependency graph.
PROSE_FILE_SUFFIXES = frozenset({".md", ".markdown"})


# Called as (completed_count, total_count, symbol) once each symbol's LLM
# summarization call has *finished*, so a caller (e.g. the CLI) can print
# progress during what's otherwise a long, silent, one-call-per-symbol pass.
#
# It used to fire just before each call started, which only had a defined
# order while the pass was sequential. Symbols are now summarized from a
# thread pool, where "about to start" arrives in whatever order the pool
# schedules; "finished" is the one event that still counts monotonically.
# The pipeline serializes these calls, so a callback never needs its own lock.
SummaryProgressCallback = Callable[[int, int, Symbol], None]

# Symbols are summarized concurrently because each one is a single blocking
# remote call - the pass is almost entirely network wait, not computation.
# Four is deliberately modest: the ceiling here is the provider's rate limit
# on one API key, not local CPU, and `provider_routing`'s backoff turns any
# excess straight back into waiting.
DEFAULT_SUMMARY_WORKERS = 4


class SummaryPipelineError(RuntimeError):
    pass


class LocalLLMUnavailableError(SummaryPipelineError):
    pass


class CodeSummaryPipeline:
    def __init__(
        self,
        *,
        metadataStore: RepositoryMetadataStore,
        dependencyGraph: DependencyGraph,
        llmEngine: Any,
        maxWorkers: int = DEFAULT_SUMMARY_WORKERS,
    ) -> None:
        """`llmEngine` is a `provider_routing.FailoverExecutor` wrapping the
        summary stage's configured provider chain (research.md's "deferred
        implementation" of constitution 2.1/2.3) - this package must not
        depend on `provider_routing` directly (it sits below it in the
        dependency graph), so it's accepted duck-typed via `Any`.

        Both collaborators are safe to share across `maxWorkers` threads
        without any change of their own: `RepositoryMetadataStore` opens a
        connection per call, and `_summarize_symbol` reads the provider from
        the `FailoverResult` it was handed rather than from the executor's
        `providerUsed` attribute, which concurrent calls do overwrite.
        """
        if maxWorkers < 1:
            raise ValueError("maxWorkers must be at least 1")
        self.metadataStore = metadataStore
        self.dependencyGraph = dependencyGraph
        self.llmEngine = llmEngine
        self.maxWorkers = maxWorkers

    def isReady(self) -> bool:
        return self.llmEngine.isAvailable()

    def summarizeRepository(
        self,
        repository_root: str | Path,
        *,
        incremental: bool = True,
        changed_paths: Iterable[str | Path] = (),
        changed_symbol_ids: Iterable[str] = (),
        on_progress: SummaryProgressCallback | None = None,
    ) -> list[SummaryResult]:
        self._ensure_ready()
        repository_bundle = self.metadataStore.load_repository(repository_root)
        impacted = self._compute_impacted_symbols(
            repository_bundle.files,
            changed_paths=changed_paths,
            changed_symbol_ids=changed_symbol_ids,
            incremental=incremental,
        )
        return self._summarize_bundle_list(
            repository_root, repository_bundle.files, impacted=impacted, incremental=incremental, on_progress=on_progress
        )

    def summarizeSourceFile(
        self,
        repository_root: str | Path,
        path: str | Path,
        *,
        incremental: bool = True,
        on_progress: SummaryProgressCallback | None = None,
    ) -> list[SummaryResult]:
        self._ensure_ready()
        bundle = self.metadataStore.load_source_file(repository_root=repository_root, path=path)
        bundle_symbols = self._summarizable_symbols(bundle)
        impacted = ImpactedSymbolSet(
            changedFileIds=(bundle.file.id,),
            changedSymbolIds=tuple(symbol.id for symbol in bundle_symbols),
            dependentSymbolIds=tuple(sorted({dependent_id for symbol in bundle_symbols for dependent_id in self._dependent_symbol_ids(symbol.id)})),
        )
        return self._summarize_bundle_list(
            repository_root, (bundle,), impacted=impacted, incremental=incremental, on_progress=on_progress
        )

    def summarizeImpactedSymbols(
        self,
        repository_root: str | Path,
        symbol_ids: Iterable[str],
        *,
        on_progress: SummaryProgressCallback | None = None,
    ) -> list[SummaryResult]:
        self._ensure_ready()
        repository_bundle = self.metadataStore.load_repository(repository_root)
        impacted_ids = set(symbol_ids)
        dependent_ids: set[str] = set()
        for symbol_id in impacted_ids:
            dependent_ids.update(self._dependent_symbol_ids(symbol_id))
        impacted = ImpactedSymbolSet(
            changedFileIds=tuple(),
            changedSymbolIds=tuple(sorted(impacted_ids)),
            dependentSymbolIds=tuple(sorted(dependent_ids)),
        )
        return self._summarize_bundle_list(
            repository_root, repository_bundle.files, impacted=impacted, incremental=True, on_progress=on_progress
        )

    def restoreSummariesFromLedger(
        self, repository_root: str | Path, paths: Iterable[str | Path] = ()
    ) -> tuple[int, int]:
        """Refill wiped summaries from the ledger, without calling any model.

        Re-parsing a file deletes and re-inserts its symbols, which blanks every
        summary in it - including summaries of symbols that did not change. This
        puts back what is already known, and it needs no provider at all, so it
        also runs when the summary chain is unreachable. That is the difference
        between an edited file's documentation degrading to the parts that
        actually changed, and the whole file going blank.

        Two levels of recall, in order:

        1. an exact content match, restored as **fresh** - the material is
           identical, so the summary still describes it;
        2. otherwise the symbol's previous summary, restored as **stale** - it
           describes an earlier version, which the page then says out loud
           rather than presenting as current.

        Returns `(restored_fresh, restored_stale)`.
        """
        fresh = 0
        stale = 0
        for file_bundle in self._bundles_to_restore(repository_root, paths):
            source_text: str | None = None
            for symbol in self._summarizable_symbols(file_bundle):
                if symbol.generatedSummary:
                    continue
                if source_text is None:
                    try:
                        source_text = self._read_source_text(repository_root, file_bundle.file.path)
                    except OSError:
                        break
                restored, restored_hash, is_stale = self._recall_summary(
                    repository_root, file_bundle, symbol, source_text
                )
                if not restored:
                    continue
                self.metadataStore.record_symbol_summary(
                    symbol_id=symbol.id,
                    generated_summary=restored,
                    context_hash=restored_hash,
                    is_stale=is_stale,
                )
                stale += 1 if is_stale else 0
                fresh += 0 if is_stale else 1
        return fresh, stale

    def _bundles_to_restore(
        self, repository_root: str | Path, paths: Iterable[str | Path]
    ) -> list[SourceFileBundle]:
        """Only the files asked for, loaded one by one.

        The watcher calls this on every save with a single changed path, so
        loading the whole repository bundle to then filter it down would make an
        incremental run pay a repository-wide cost - exactly what the
        incremental path exists to avoid. Falling back to the full bundle when
        no path is given keeps the whole-repository call available for a full
        `index` run.
        """
        requested = list(paths)
        if not requested:
            return list(self.metadataStore.load_repository(repository_root).files)
        bundles: list[SourceFileBundle] = []
        for path in requested:
            try:
                bundles.append(self.metadataStore.load_source_file(repository_root=repository_root, path=path))
            except KeyError:
                # Deleted between the reparse and here, or never stored.
                continue
        return bundles

    def _recall_summary(
        self,
        repository_root: str | Path,
        bundle: SourceFileBundle,
        symbol: Symbol,
        source_text: str,
    ) -> tuple[str, str, bool]:
        """`(summary, context_hash, is_stale)` for `symbol`, or `("", "", False)`."""
        summary_context = build_summary_context(
            repository_root=repository_root,
            source_file_bundle=bundle,
            symbol=symbol,
            dependency_graph=self.dependencyGraph,
            source_text=source_text,
            symbol_source_text=self._symbol_source_text(bundle, symbol, source_text),
        )
        current_hash = context_hash(summary_context)
        exact = self.metadataStore.recall_summary(context_hash=current_hash)
        if exact:
            return exact, current_hash, False
        previous, previous_hash = self.metadataStore.recall_previous_summary(
            source_file_id=bundle.file.id, symbol_kind=symbol.kind, symbol_name=symbol.name
        )
        if previous:
            return previous, previous_hash, True
        return "", "", False

    def _ensure_ready(self) -> None:
        if not self.llmEngine.isAvailable():
            raise LocalLLMUnavailableError(
                "No provider in the summary chain is currently available. Start the local service, "
                "install the required model, or check your remote provider credentials, then try again."
            )

    def _summarize_bundle_list(
        self,
        repository_root: str | Path,
        bundles: Sequence[SourceFileBundle],
        *,
        impacted: ImpactedSymbolSet | None,
        incremental: bool,
        on_progress: SummaryProgressCallback | None = None,
    ) -> list[SummaryResult]:
        impacted_ids = set(impacted.all_symbol_ids()) if impacted is not None else None
        pending: list[tuple[SourceFileBundle, Symbol]] = []
        for bundle in bundles:
            for symbol in self._summarizable_symbols(bundle):
                if impacted_ids is not None and symbol.id not in impacted_ids:
                    continue
                pending.append((bundle, symbol))

        total = len(pending)
        if not pending:
            return []

        # Read every distinct source file up front rather than lazily inside
        # the pool: it is cheap local I/O, and hoisting it out is what keeps
        # the shared cache from needing a lock of its own.
        source_text_by_file_id: dict[str, str] = {}
        for bundle, _ in pending:
            if bundle.file.id not in source_text_by_file_id:
                source_text_by_file_id[bundle.file.id] = self._read_source_text(repository_root, bundle.file.path)

        progress_lock = threading.Lock()
        completed = 0

        def summarize_one(bundle: SourceFileBundle, symbol: Symbol) -> SummaryResult:
            nonlocal completed
            result = self._summarize_symbol(
                repository_root,
                bundle,
                symbol,
                source_text=source_text_by_file_id[bundle.file.id],
                incremental=incremental,
            )
            if on_progress is not None:
                # Counter and callback under one lock, so the reported count is
                # both gap-free and printed in the order it was counted -
                # otherwise two workers can interleave into "[7/9]" then
                # "[6/9]" on the same line of output.
                with progress_lock:
                    completed += 1
                    on_progress(completed, total, symbol)
            return result

        workers = min(self.maxWorkers, total)
        executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="codepedia-summary")
        try:
            futures: list[Future[SummaryResult]] = [
                executor.submit(summarize_one, bundle, symbol) for bundle, symbol in pending
            ]
            results: list[SummaryResult] = []
            for future in futures:
                # Collected in submission order, so `results` stays ordered
                # exactly as the sequential pass returned it. The first failure
                # propagates, as before; calls already in flight when it does
                # may still complete and persist their summary, which is
                # harmless - a summary is idempotent per symbol.
                results.append(future.result())
            return results
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    def _summarizable_symbols(self, bundle: SourceFileBundle) -> list[Symbol]:
        symbols: list[Symbol] = [bundle.module]
        symbols.extend(bundle.classes)
        nested_function_ids = self._nested_function_ids(bundle)
        for function_symbol in bundle.functions:
            if function_symbol.id in nested_function_ids:
                continue
            if function_symbol.name.startswith("_"):
                continue
            symbols.append(function_symbol)
        return symbols

    def _nested_function_ids(self, bundle: SourceFileBundle) -> set[str]:
        nested_ids: set[str] = set()
        for symbol in bundle.functions:
            nested_ids.update(symbol.nestedSymbols)
        return nested_ids

    def _summarize_symbol(
        self,
        repository_root: str | Path,
        bundle: SourceFileBundle,
        symbol: Symbol,
        *,
        source_text: str,
        incremental: bool,
    ) -> SummaryResult:
        symbol_source_text = self._symbol_source_text(bundle, symbol, source_text)
        summary_context = build_summary_context(
            repository_root=repository_root,
            source_file_bundle=bundle,
            symbol=symbol,
            dependency_graph=self.dependencyGraph,
            source_text=source_text,
            symbol_source_text=symbol_source_text,
        )
        current_context_hash = context_hash(summary_context)

        # The ledger is consulted before the model is. Re-parsing a file wipes
        # the summaries of *every* symbol in it, including symbols that were not
        # touched, so without this an edit to one function re-bought a summary
        # for every other function in the file, forever. The ledger is keyed on
        # content, so a symbol whose material is unchanged is served from it -
        # and that holds even when the symbol's id changed because lines moved
        # above it.
        remembered = self.metadataStore.recall_summary(context_hash=current_context_hash)
        if remembered:
            self.metadataStore.record_symbol_summary(
                symbol_id=symbol.id,
                generated_summary=remembered,
                context_hash=current_context_hash,
                is_stale=False,
            )
            return SummaryResult(
                symbolId=symbol.id,
                generatedSummary=remembered,
                modelName="",
                contextHash=current_context_hash,
                sourceFileId=bundle.file.id,
                symbolKind=symbol.kind,
                symbolName=symbol.name,
            )

        prompt = self._build_prompt(summary_context)
        failover_result = self.llmEngine.run(lambda engine: engine.generate(prompt))
        generated_summary = failover_result.value.strip()
        if not generated_summary:
            raise SummaryPipelineError(f"LLM returned an empty summary for symbol {symbol.id}")
        result = SummaryResult(
            symbolId=symbol.id,
            generatedSummary=generated_summary,
            modelName=str(failover_result.providerUsed),
            contextHash=current_context_hash,
            sourceFileId=bundle.file.id,
            symbolKind=symbol.kind,
            symbolName=symbol.name,
        )
        self.metadataStore.remember_summary(
            context_hash=current_context_hash,
            source_file_id=bundle.file.id,
            symbol_kind=symbol.kind,
            symbol_name=symbol.name,
            generated_summary=generated_summary,
            model_name=result.modelName,
            generated_at=result.generatedAt,
        )
        self.metadataStore.record_symbol_summary(
            symbol_id=symbol.id,
            generated_summary=generated_summary,
            context_hash=current_context_hash,
            is_stale=False,
        )
        return result

    def _build_prompt(self, context: SummaryContext):
        # A .md file's symbols are headings, so the code-shaped prompt would ask
        # the model to read prose as an implementation.
        if Path(context.sourceFilePath).suffix.lower() in PROSE_FILE_SUFFIXES:
            return build_prose_summary_prompt(context)
        if context.symbolKind == "module":
            return build_module_summary_prompt(context)
        if context.symbolKind == "class":
            return build_class_summary_prompt(context)
        return build_function_summary_prompt(context)

    def _read_source_text(self, repository_root: str | Path, relative_path: str | Path) -> str:
        source_path = Path(relative_path)
        if not source_path.is_absolute():
            source_path = Path(repository_root) / source_path
        return source_path.read_text(encoding="utf-8")

    def _symbol_source_text(self, bundle: SourceFileBundle, symbol: Symbol, source_text: str) -> str:
        if isinstance(symbol, ModuleSymbol):
            return source_text.strip()
        lines = source_text.splitlines()
        if not lines:
            return ""
        start = max(1, symbol.lineStart)
        end = max(start, symbol.lineEnd)
        start_index = max(0, start - 1)
        end_index = min(len(lines), end)
        return "\n".join(lines[start_index:end_index]).strip()

    def _dependent_symbol_ids(self, symbol_id: str) -> tuple[str, ...]:
        dependents = self.dependencyGraph.dependents(symbol_id)
        return tuple(node.id for node in dependents if node.kind == "symbol")

    def _compute_impacted_symbols(
        self,
        bundles: Sequence[SourceFileBundle],
        *,
        changed_paths: Iterable[str | Path],
        changed_symbol_ids: Iterable[str],
        incremental: bool,
    ) -> ImpactedSymbolSet:
        if not incremental:
            return ImpactedSymbolSet(
                changedFileIds=tuple(bundle.file.id for bundle in bundles),
                changedSymbolIds=tuple(symbol.id for bundle in bundles for symbol in self._summarizable_symbols(bundle)),
                dependentSymbolIds=(),
            )
        changed_path_strings = {Path(path).as_posix().replace("\\", "/") for path in changed_paths}
        changed_files = [bundle for bundle in bundles if bundle.file.path in changed_path_strings or bundle.file.id in changed_path_strings]
        if not changed_files and not set(changed_symbol_ids):
            return ImpactedSymbolSet(
                changedFileIds=tuple(bundle.file.id for bundle in bundles),
                changedSymbolIds=tuple(symbol.id for bundle in bundles for symbol in self._summarizable_symbols(bundle)),
                dependentSymbolIds=(),
            )
        changed_file_ids = tuple(bundle.file.id for bundle in changed_files)
        direct_changed_ids: set[str] = set(changed_symbol_ids)
        for bundle in changed_files:
            direct_changed_ids.update(symbol.id for symbol in self._summarizable_symbols(bundle))
        dependent_ids: set[str] = set()
        for symbol_id in direct_changed_ids:
            dependent_ids.update(self._dependent_symbol_ids(symbol_id))
        return ImpactedSymbolSet(
            changedFileIds=changed_file_ids,
            changedSymbolIds=tuple(sorted(direct_changed_ids)),
            dependentSymbolIds=tuple(sorted(dependent_ids)),
        )
