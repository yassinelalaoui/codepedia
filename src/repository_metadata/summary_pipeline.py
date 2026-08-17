from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Sequence

from dependency_graph import DependencyGraph
from local_llm import LocalLLMEngine
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
from .summary_prompts import build_class_summary_prompt, build_function_summary_prompt, build_module_summary_prompt


# Called as (completed_count, total_count, symbol) right before each symbol's
# LLM summarization call starts, so a caller (e.g. the CLI) can print
# progress during what's otherwise a long, silent, one-call-per-symbol loop.
SummaryProgressCallback = Callable[[int, int, Symbol], None]


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
        llmEngine: LocalLLMEngine,
    ) -> None:
        self.metadataStore = metadataStore
        self.dependencyGraph = dependencyGraph
        self.llmEngine = llmEngine

    def isReady(self) -> bool:
        return self.llmEngine.isAvailableLocally()

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

    def _ensure_ready(self) -> None:
        status = self.llmEngine.checkAvailability()
        if not status.available:
            raise LocalLLMUnavailableError(
                f"Local LLM unavailable at {self.llmEngine.endpointUrl} for model {self.llmEngine.modelName}: {status.message}. "
                "Start the local service or install the model before summarizing code."
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
        results: list[SummaryResult] = []
        source_text_by_file_id: dict[str, str] = {}
        for index, (bundle, symbol) in enumerate(pending, start=1):
            source_text = source_text_by_file_id.get(bundle.file.id)
            if source_text is None:
                source_text = self._read_source_text(repository_root, bundle.file.path)
                source_text_by_file_id[bundle.file.id] = source_text
            if on_progress is not None:
                on_progress(index, total, symbol)
            result = self._summarize_symbol(
                repository_root,
                bundle,
                symbol,
                source_text=source_text,
                incremental=incremental,
            )
            results.append(result)
        return results

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
        prompt = self._build_prompt(summary_context)
        generated_summary = self.llmEngine.generate(prompt).strip()
        if not generated_summary:
            raise SummaryPipelineError(f"LLM returned an empty summary for symbol {symbol.id}")
        result = SummaryResult(
            symbolId=symbol.id,
            generatedSummary=generated_summary,
            modelName=self.llmEngine.modelName,
            contextHash=context_hash(summary_context),
            sourceFileId=bundle.file.id,
            symbolKind=symbol.kind,
            symbolName=symbol.name,
        )
        self.metadataStore.update_symbol_generated_summary(symbol.id, generated_summary)
        return result

    def _build_prompt(self, context: SummaryContext):
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
