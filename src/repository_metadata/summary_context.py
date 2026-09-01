from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from dependency_graph import DependencyGraph

# The *persisted* symbols, from this package's own models - not the identically
# named extracted ones in `parser_engine`. A `SourceFileBundle` carries these,
# and the `isinstance()` checks below are what read them; imported from
# `parser_engine` instead, as they were, none of those checks could ever be true.
from .models import ClassSymbol, DependencyEdge, FunctionSymbol, ModuleSymbol, SourceFileBundle, Symbol

# Defined here rather than in `doc_generator.prose`, which used to hold a second
# copy of it: `repository_metadata` is the lower of the two packages, so this is
# the direction the dependency already runs. Two copies meant adding `.mdx` to
# one of them would summarize a file as code and render it as prose, with
# nothing anywhere reporting an error.
PROSE_FILE_SUFFIXES = frozenset({".md", ".markdown"})


def is_prose_file(file_path: str) -> bool:
    """Whether this file is documentation rather than code.

    `parser_engine` maps a Markdown heading onto the class/function symbol
    types, which is what lets documentation reuse the whole pipeline unchanged.
    The cost is that a heading is indistinguishable from a real symbol by type
    alone, so the places where the difference matters ask here.
    """
    return Path(file_path).suffix.lower() in PROSE_FILE_SUFFIXES



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

    * `symbolId` names the symbol; it does not describe it. It no longer moves
      on an unrelated edit (`parser_engine.extractor._symbol_id`), but it still
      moves when a symbol is renamed or an earlier homonym is added - and a
      ledger keyed on identity could never match a symbol whose row a re-parse
      has just destroyed and rebuilt;
    * `sourceFileId` embeds the absolute repository path, which differs between
      an `index` run (built inside `.staging-<pid>`) and the published state
      directory it is renamed into.

    Including either would mean a symbol never matched its own previous entry in
    the ledger. What remains is exactly what the model is shown, so an identical
    hash really does mean an identical prompt.

    That last sentence is load-bearing in both directions, and it is where this
    used to go wrong: line numbers, kept out of the payload above, walked
    straight back in through `metadata`, which carried `lineStart`/`lineEnd`
    until `_symbol_metadata` stopped emitting them. Anything added to the prompt
    is added to the ledger's key, so a field has to earn its place twice.

    `metadata` is dropped entirely for prose, because the prose prompt has no
    `Metadata:` block at all (`summary_prompts.build_prose_summary_prompt`) -
    hashing what the model is never shown can only cost recall.
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
            () if is_prose_file(context.sourceFilePath) else sorted(context.metadata.items(), key=lambda item: item[0]),
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
    """What the prompt's `Metadata:` block says about a symbol.

    Everything here describes the symbol; nothing here locates it. Two kinds of
    field were deliberately dropped:

    * `lineStart`/`lineEnd` - a line number teaches a model nothing about what a
      symbol does, and putting it in the prompt put it in `context_hash` too, so
      a comment added at the top of a file made the summary ledger miss for
      every symbol below it and re-paid each one at the model.
    * `methods`/`nestedSymbols` - these are symbol *ids*, which name symbols
      rather than describing them, and carry the identity volatility of the
      `symbolId` exclusion one level down. They are also unreadable as prompt
      material.

    This is a derived dict; `symbol.metadata` as stored in the database is not
    touched.
    """
    metadata = dict(symbol.metadata)
    metadata["symbolKind"] = symbol.kind
    metadata["symbolName"] = symbol.name
    if isinstance(symbol, ModuleSymbol):
        metadata["filePath"] = symbol.filePath
        metadata["imports"] = [str(item.text) if hasattr(item, "text") else str(item) for item in symbol.imports]
    elif isinstance(symbol, ClassSymbol):
        metadata["parentClass"] = symbol.parentClass
    elif isinstance(symbol, FunctionSymbol):
        metadata["parameters"] = [param.to_dict() for param in symbol.parameters]
        metadata["returnType"] = symbol.returnType
        metadata["owner"] = symbol.owner
    return metadata
