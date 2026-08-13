from __future__ import annotations

from pathlib import Path

from embedding_engine import EmbeddingEngine
from repository_metadata import ModuleSymbol, RepositoryMetadataStore, Symbol
from repository_metadata.models import SourceFileBundle
from vector_index import CodeChunk, VectorIndex, build_code_chunk


def update_embeddings(
    *,
    repository_root: Path,
    relative_path: str,
    metadata_store: RepositoryMetadataStore,
    vector_index: VectorIndex,
    embedding_engine: EmbeddingEngine,
) -> tuple[CodeChunk, ...]:
    absolute_path = repository_root / relative_path
    # RepositoryMetadataStore keys by the absolute path SourceFile.path was stored
    # with (see pipeline.py's _reparse_and_store) — must match here to find the
    # bundle just persisted. CodeChunk.sourceFilePath is kept relative below, since
    # that value is user-facing (chat citations, 011) and shouldn't leak filesystem
    # layout.
    bundle = metadata_store.load_source_file(repository_root=repository_root, path=absolute_path)
    source_text = absolute_path.read_text(encoding="utf-8", errors="replace")
    chunks = tuple(
        build_code_chunk(
            symbol_text,
            source_symbol_id=symbol.id,
            source_file_path=relative_path,
            embedding_engine=embedding_engine,
        )
        for symbol in _in_scope_symbols(bundle)
        if (symbol_text := _symbol_source_text(bundle, symbol, source_text))
    )
    vector_index.reindexFile(relative_path, chunks)
    return chunks


def remove_embeddings(*, relative_path: str, vector_index: VectorIndex) -> tuple[str, ...]:
    return vector_index.removeChunksForFile(relative_path)


def _in_scope_symbols(bundle: SourceFileBundle) -> list[Symbol]:
    nested_ids = {nested_id for function in bundle.functions for nested_id in function.nestedSymbols}
    symbols: list[Symbol] = [bundle.module]
    for function in bundle.functions:
        if function.id in nested_ids:
            continue
        if function.name.startswith("_"):
            continue
        symbols.append(function)
    return symbols


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
