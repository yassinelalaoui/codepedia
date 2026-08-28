from __future__ import annotations

from pathlib import Path
from typing import Any

from repository_metadata import ClassSymbol, FunctionSymbol, ModuleSymbol, RepositoryMetadataStore, Symbol
from repository_metadata.models import SourceFileBundle
from vector_index import CodeChunk, VectorIndex, build_code_chunk

from .embedding_cache import EmbeddingCache, expected_embedding_model_id


def update_embeddings(
    *,
    repository_root: Path,
    relative_path: str,
    metadata_store: RepositoryMetadataStore,
    vector_index: VectorIndex,
    embedding_engine: Any,
    embedding_cache: EmbeddingCache | None = None,
) -> tuple[CodeChunk, ...]:
    """Re-embed one file and replace its chunks in the index.

    `embedding_cache`, when given, is consulted before every embedding call
    and fed after every real one, so an unchanged fragment costs nothing the
    second time it is seen - whether that is a second run of the same
    repository or a byte-identical body under another symbol.
    """
    absolute_path = repository_root / relative_path
    # RepositoryMetadataStore keys by the absolute path SourceFile.path was stored
    # with (see pipeline.py's _reparse_and_store) — must match here to find the
    # bundle just persisted. CodeChunk.sourceFilePath is kept relative below, since
    # that value is user-facing (chat citations, 011) and shouldn't leak filesystem
    # layout.
    bundle = metadata_store.load_source_file(repository_root=repository_root, path=absolute_path)
    source_text = absolute_path.read_text(encoding="utf-8", errors="replace")
    model_id = expected_embedding_model_id(embedding_engine) if embedding_cache is not None else ""
    built: list[CodeChunk] = []
    for symbol in _in_scope_symbols(bundle):
        symbol_text = _symbol_source_text(bundle, symbol, source_text)
        if symbol_text:
            built.append(
                _build_chunk_reusing_cache(
                    symbol_text,
                    source_symbol_id=symbol.id,
                    relative_path=relative_path,
                    embedding_engine=embedding_engine,
                    embedding_cache=embedding_cache,
                    model_id=model_id,
                    chunk_type="code",
                )
            )
        # A second, separately searchable chunk carrying what the symbol is *for*
        # rather than what it literally says. Code and summary chunks never
        # collide: build_chunk_id seeds on chunk_type.
        summary_text = _symbol_summary_text(symbol)
        if summary_text:
            built.append(
                _build_chunk_reusing_cache(
                    summary_text,
                    source_symbol_id=symbol.id,
                    relative_path=relative_path,
                    embedding_engine=embedding_engine,
                    embedding_cache=embedding_cache,
                    model_id=model_id,
                    chunk_type="summary",
                )
            )
    chunks = tuple(built)
    vector_index.reindexFile(relative_path, chunks)
    return chunks


def _build_chunk_reusing_cache(
    fragment: str,
    *,
    source_symbol_id: str,
    relative_path: str,
    embedding_engine: Any,
    embedding_cache: EmbeddingCache | None,
    model_id: str,
    chunk_type: str,
) -> CodeChunk:
    """Build one chunk, paying for an embedding only when the cache cannot serve it."""
    if embedding_cache is not None:
        cached = embedding_cache.get(
            source_symbol_id=source_symbol_id, content=fragment, chunk_type=chunk_type, model_id=model_id
        )
        if cached is not None:
            return build_code_chunk(
                fragment,
                source_symbol_id=source_symbol_id,
                source_file_path=relative_path,
                embedding=cached,
                chunk_type=chunk_type,
                # Carried over explicitly: a reused vector still has to be
                # stored under the model that produced it, or `search`'s
                # embeddingModelId filter would drop it.
                embedding_model_id=model_id,
            )
    chunk = build_code_chunk(
        fragment,
        source_symbol_id=source_symbol_id,
        source_file_path=relative_path,
        embedding_engine=embedding_engine,
        chunk_type=chunk_type,
    )
    if embedding_cache is not None:
        embedding_cache.put(
            source_symbol_id=source_symbol_id,
            content=fragment,
            chunk_type=chunk_type,
            model_id=chunk.embeddingModelId,
            vector=chunk.embedding,
        )
    return chunk


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
