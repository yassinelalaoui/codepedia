from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Sequence

from embedding_engine import EmbeddingEngine

from .models import CodeChunk


def _normalize_content(content: str) -> str:
    return "\n".join(line.rstrip() for line in content.strip().splitlines())


def build_chunk_id(source_symbol_id: str, content: str, *, chunk_type: str = "code") -> str:
    normalized = _normalize_content(content)
    seed = f"{source_symbol_id}|{chunk_type}|{normalized}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return f"chunk_{digest[:16]}"


def build_code_chunk(
    content: str,
    *,
    source_symbol_id: str,
    source_file_path: str | Path = "",
    embedding: Sequence[float] | None = None,
    embedding_engine: EmbeddingEngine | None = None,
    chunk_type: str = "code",
    chunk_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> CodeChunk:
    normalized_content = content if content.endswith("\n") else content
    if embedding is None:
        if embedding_engine is None:
            raise ValueError("embedding_engine must be provided when embedding is omitted")
        embedding = embedding_engine.embed(normalized_content)
    return CodeChunk(
        id=chunk_id or build_chunk_id(source_symbol_id, normalized_content, chunk_type=chunk_type),
        content=normalized_content,
        embedding=tuple(embedding),
        sourceSymbolId=source_symbol_id,
        sourceFilePath=str(Path(source_file_path).expanduser()) if source_file_path else "",
        chunkType=chunk_type,  # type: ignore[arg-type]
        metadata=dict(metadata or {}),
    )


def build_code_chunks(
    fragments: Iterable[str],
    *,
    source_symbol_id: str,
    source_file_path: str | Path = "",
    embedding_engine: EmbeddingEngine | None = None,
    chunk_type: str = "code",
) -> tuple[CodeChunk, ...]:
    return tuple(
        build_code_chunk(
            fragment,
            source_symbol_id=source_symbol_id,
            source_file_path=source_file_path,
            embedding_engine=embedding_engine,
            chunk_type=chunk_type,
        )
        for fragment in fragments
    )
