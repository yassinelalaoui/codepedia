from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from dependency_graph import DependencyGraph
from parser_engine import ClassSymbol, FunctionSymbol, ModuleSymbol, Symbol

from .models import DependencyEdge, SourceFileBundle


@dataclass(frozen=True, slots=True)
class SymbolSummaryJob:
    symbolId: str
    sourceFileId: str
    symbolKind: str
    symbolName: str
    sourceFilePath: str
    lineStart: int
    lineEnd: int
    contentHash: str
    isIncremental: bool = True
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SummaryContext:
    symbolId: str
    symbolKind: str
    symbolName: str
    sourceFileId: str
    sourceFilePath: str
    sourceText: str
    imports: tuple[str, ...] = ()
    directCallers: tuple[str, ...] = ()
    docstring: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SummaryResult:
    symbolId: str
    generatedSummary: str
    modelName: str
    contextHash: str
    generatedAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sourceFileId: str = ""
    symbolKind: str = ""
    symbolName: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ImpactedSymbolSet:
    changedFileIds: tuple[str, ...] = ()
    changedSymbolIds: tuple[str, ...] = ()
    dependentSymbolIds: tuple[str, ...] = ()

    def all_symbol_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.changedSymbolIds, *self.dependentSymbolIds)))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_summary_job(
    symbol: Symbol,
    source_file_bundle: SourceFileBundle,
    *,
    content_hash: str,
    is_incremental: bool = True,
    priority: int = 0,
) -> SymbolSummaryJob:
    return SymbolSummaryJob(
        symbolId=symbol.id,
        sourceFileId=source_file_bundle.file.id,
        symbolKind=symbol.kind,
        symbolName=symbol.name,
        sourceFilePath=source_file_bundle.file.path,
        lineStart=symbol.lineStart,
        lineEnd=symbol.lineEnd,
        contentHash=content_hash,
        isIncremental=is_incremental,
        priority=priority,
    )


def build_summary_context(
    *,
    repository_root: str | Path,
    source_file_bundle: SourceFileBundle,
    symbol: Symbol,
    dependency_graph: DependencyGraph,
    source_text: str,
    symbol_source_text: str,
) -> SummaryContext:
    imports = _collect_import_texts(source_file_bundle.module)
    focus = source_file_bundle.file.path if isinstance(symbol, ModuleSymbol) else symbol.id
    callers = _collect_direct_callers(focus, symbol, dependency_graph)
    metadata = _symbol_metadata(symbol)
    metadata["sourceFileLanguage"] = source_file_bundle.file.language
    # `repositoryRoot` and `sourceFileLastModified` used to be added here and
    # reached the model through the prompt's "Metadata:" block. Both are gone:
    # neither tells a model anything about what a symbol does, and both are
    # volatile in a way that broke everything downstream. `lastModified` is set
    # to `datetime.now()` on every store, so the context hash changed on every
    # single re-parse - which is why `contextHash` could never be used as a
    # cache key. `repositoryRoot` is an absolute path, and `index_command`
    # builds inside a `.staging-<pid>` directory before renaming it into place,
    # so it differed between the run that wrote a summary and the run that
    # tried to reuse it.
    return SummaryContext(
        symbolId=symbol.id,
        symbolKind=symbol.kind,
        symbolName=symbol.name,
        sourceFileId=source_file_bundle.file.id,
        sourceFilePath=_relative_source_path(source_file_bundle.file.path, repository_root),
        sourceText=symbol_source_text or source_text,
        imports=tuple(imports),
        directCallers=tuple(callers),
        docstring=symbol.docstring,
        metadata=metadata,
    )


def context_hash(context: SummaryContext) -> str:
    """Identify the *material* a summary was generated from.

    Hashes a curated payload rather than the whole dataclass, because two of its
    fields identify the symbol rather than describe it, and both move for
    reasons a summary should not care about:

    * `symbolId` embeds the symbol's line range, so inserting a line anywhere
      above it changes the id while the symbol itself is untouched;
    * `sourceFileId` embeds the absolute repository path, which differs between
      an `index` run (built inside `.staging-<pid>`) and the published state
      directory it is renamed into.

    Including either would mean a symbol never matched its own previous entry in
    the ledger. What remains is exactly what the model is shown, so an identical
    hash really does mean an identical prompt.
    """
    payload = repr(
        (
            context.symbolKind,
            context.symbolName,
            context.sourceFilePath,
            context.docstring,
            context.sourceText,
            context.imports,
            context.directCallers,
            sorted(context.metadata.items(), key=lambda item: item[0]),
        )
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _relative_source_path(file_path: str, repository_root: str | Path) -> str:
    """The file's path as a reader would write it, and as it stays across runs.

    An absolute path in the prompt is noise, and it also changes when the same
    repository is indexed from a staging directory, which would stop a summary
    from ever being reused.
    """
    try:
        return Path(file_path).resolve().relative_to(Path(repository_root).resolve()).as_posix()
    except (OSError, ValueError):
        return Path(file_path).as_posix()


def _collect_import_texts(module: ModuleSymbol) -> list[str]:
    result: list[str] = []
    for item in module.imports:
        if hasattr(item, "text"):
            result.append(str(getattr(item, "text")))
        else:
            result.append(str(item))
    return result


def _collect_direct_callers(focus: str, symbol: Symbol, dependency_graph: DependencyGraph) -> list[str]:
    if isinstance(symbol, FunctionSymbol):
        caller_nodes = dependency_graph.functions_calling(focus)
    elif isinstance(symbol, ClassSymbol):
        caller_nodes = dependency_graph.classes_inheriting(focus)
    else:
        caller_nodes = dependency_graph.files_importing(focus)
    descriptions: list[str] = []
    for node in caller_nodes:
        label = f"{node.kind}:{node.name}"
        if node.symbolType:
            label = f"{label} ({node.symbolType})"
        descriptions.append(label)
    return descriptions


def _symbol_metadata(symbol: Symbol) -> dict[str, Any]:
    metadata = dict(symbol.metadata)
    metadata["symbolKind"] = symbol.kind
    metadata["symbolName"] = symbol.name
    metadata["lineStart"] = symbol.lineStart
    metadata["lineEnd"] = symbol.lineEnd
    if isinstance(symbol, ModuleSymbol):
        metadata["filePath"] = symbol.filePath
        metadata["imports"] = [str(item.text) if hasattr(item, "text") else str(item) for item in symbol.imports]
    elif isinstance(symbol, ClassSymbol):
        metadata["parentClass"] = symbol.parentClass
        metadata["methods"] = list(symbol.methods)
        metadata["nestedSymbols"] = list(symbol.nestedSymbols)
    elif isinstance(symbol, FunctionSymbol):
        metadata["parameters"] = [param.to_dict() for param in symbol.parameters]
        metadata["returnType"] = symbol.returnType
        metadata["nestedSymbols"] = list(symbol.nestedSymbols)
        metadata["owner"] = symbol.owner
    return metadata
