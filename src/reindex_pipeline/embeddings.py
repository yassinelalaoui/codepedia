from __future__ import annotations

from pathlib import Path
from typing import Any

from repository_metadata import ClassSymbol, FunctionSymbol, ModuleSymbol, RepositoryMetadataStore, Symbol
from repository_metadata.models import SourceFileBundle
from vector_index import CodeChunk, VectorIndex, build_code_chunk


def update_embeddings(
    *,
    repository_root: Path,
    relative_path: str,
    metadata_store: RepositoryMetadataStore,
    vector_index: VectorIndex,
    embedding_engine: Any,
) -> tuple[CodeChunk, ...]:
    absolute_path = repository_root / relative_path
    # RepositoryMetadataStore keys by the absolute path SourceFile.path was stored
    # with (see pipeline.py's _reparse_and_store) — must match here to find the
    # bundle just persisted. CodeChunk.sourceFilePath is kept relative below, since
    # that value is user-facing (chat citations, 011) and shouldn't leak filesystem
    # layout.
    bundle = metadata_store.load_source_file(repository_root=repository_root, path=absolute_path)
    source_text = absolute_path.read_text(encoding="utf-8", errors="replace")
    built: list[CodeChunk] = []
    for symbol in _in_scope_symbols(bundle):
        symbol_text = _symbol_source_text(bundle, symbol, source_text)
        if symbol_text:
            built.append(
                build_code_chunk(
                    symbol_text,
                    source_symbol_id=symbol.id,
                    source_file_path=relative_path,
                    embedding_engine=embedding_engine,
                )
            )
        # A second, separately searchable chunk carrying what the symbol is *for*
        # rather than what it literally says. Code and summary chunks never
        # collide: build_chunk_id seeds on chunk_type.
        summary_text = _symbol_summary_text(symbol)
        if summary_text:
            built.append(
                build_code_chunk(
                    summary_text,
                    source_symbol_id=symbol.id,
                    source_file_path=relative_path,
                    embedding_engine=embedding_engine,
                    chunk_type="summary",
                )
            )
    chunks = tuple(built)
    vector_index.reindexFile(relative_path, chunks)
    return chunks


def remove_embeddings(*, relative_path: str, vector_index: VectorIndex) -> tuple[str, ...]:
    return vector_index.removeChunksForFile(relative_path)


def _in_scope_symbols(bundle: SourceFileBundle) -> list[Symbol]:
    nested_ids = {nested_id for function in bundle.functions for nested_id in function.nestedSymbols}
    symbols: list[Symbol] = [bundle.module]
    symbols.extend(bundle.classes)
    for function in bundle.functions:
        if function.id in nested_ids:
            continue
        if function.name.startswith("_"):
            continue
        symbols.append(function)
    return symbols


def _symbol_summary_text(symbol: Symbol) -> str:
    """Signature, docstring and generated summary as one searchable fragment.

    Returns "" when the symbol has no generated summary yet, which is a normal
    state: the incremental pipeline keeps embedding after a
    LocalLLMUnavailableError and only summarizes impacted symbols, so an
    un-summarized symbol must simply produce no summary chunk rather than an
    empty one.
    """
    summary = (symbol.generatedSummary or "").strip()
    if not summary:
        return ""
    parts = [_symbol_signature(symbol)]
    docstring = (symbol.docstring or "").strip()
    if docstring:
        parts.append(docstring)
    parts.append(summary)
    return "\n\n".join(part for part in parts if part)


def _symbol_signature(symbol: Symbol) -> str:
    if isinstance(symbol, ModuleSymbol):
        return f"module {symbol.name}"
    if isinstance(symbol, ClassSymbol):
        parent = f"({symbol.parentClass})" if symbol.parentClass else ""
        return f"class {symbol.name}{parent}"
    if isinstance(symbol, FunctionSymbol):
        parameters = ", ".join(parameter.name for parameter in symbol.parameters)
        returns = f" -> {symbol.returnType}" if symbol.returnType else ""
        return f"{symbol.name}({parameters}){returns}"
    return symbol.name


def _symbol_source_text(bundle: SourceFileBundle, symbol: Symbol, source_text: str) -> str:
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
