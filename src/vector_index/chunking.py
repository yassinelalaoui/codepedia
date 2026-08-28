from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable, Sequence

from .models import CodeChunk


def normalize_chunk_content(content: str) -> str:
    """The exact text `build_chunk_id` hashes, minus the symbol id.

    Public because an embedding cache needs to key on content alone: a chunk id
    is seeded on `sourceSymbolId`, so two symbols with byte-identical bodies get
    different ids and would each pay for their own embedding call. Keying the
    cache on this value instead is what lets the second one reuse the first's
    vector.
    """
    return "\n".join(line.rstrip() for line in content.strip().splitlines())


# The private name the rest of this module already used.
_normalize_content = normalize_chunk_content


def build_chunk_id(source_symbol_id: str, content: str, *, chunk_type: str = "code") -> str:
    normalized = normalize_chunk_content(content)
    seed = f"{source_symbol_id}|{chunk_type}|{normalized}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return f"chunk_{digest[:16]}"


def build_code_chunk(
    content: str,
    *,
    source_symbol_id: str,
    source_file_path: str | Path = "",
    embedding: Sequence[float] | None = None,
    embedding_engine: Any = None,
    chunk_type: str = "code",
    chunk_id: str | None = None,
    metadata: dict[str, object] | None = None,
    embedding_model_id: str = "",
) -> CodeChunk:
    """`embedding_engine` is either a raw `EmbeddingProvider` (`.embed(text)`)
    or a `provider_routing.FailoverExecutor` wrapping one (`.run(call)`,
    duck-typed via `hasattr` since this package must not depend on
    `provider_routing` - it sits below it in the dependency graph). When a
    `FailoverExecutor` is given, `embeddingModelId` is stamped from whichever
    provider actually produced the vector (spec FR-009).

    `embedding_model_id` names the provider behind an `embedding` passed in
    directly - a vector reused from a cache or from a previous index. Without
    it a reused vector would be stored with an empty model id and stop matching
    `search`'s `embeddingModelId` filter, which is exactly how a cached chunk
    would silently vanish from results."""
    normalized_content = content if content.endswith("\n") else content
    if embedding is None:
        embedding_model_id = ""
        if embedding_engine is None:
            raise ValueError("embedding_engine must be provided when embedding is omitted")
        if hasattr(embedding_engine, "run"):
            failover_result = embedding_engine.run(lambda engine: engine.embed(normalized_content))
            embedding = failover_result.value
            embedding_model_id = str(failover_result.providerUsed)
        else:
            embedding = embedding_engine.embed(normalized_content)
    return CodeChunk(
        id=chunk_id or build_chunk_id(source_symbol_id, normalized_content, chunk_type=chunk_type),
        content=normalized_content,
        embedding=tuple(embedding),
        sourceSymbolId=source_symbol_id,
        sourceFilePath=str(Path(source_file_path).expanduser()) if source_file_path else "",
        chunkType=chunk_type,  # type: ignore[arg-type]
        metadata=dict(metadata or {}),
        embeddingModelId=embedding_model_id,
    )


def build_code_chunks(
    fragments: Iterable[str],
    *,
    source_symbol_id: str,
    source_file_path: str | Path = "",
    embedding_engine: Any = None,
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
