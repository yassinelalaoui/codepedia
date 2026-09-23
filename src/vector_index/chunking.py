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
    """`embedding_engine` is an `EmbeddingProvider` (`.embed(text)`).
    `embeddingModelId` is stamped from its `providerId` when it has one, so a
    stored vector always records the model that produced it (spec FR-009). A
    provider without `providerId` stamps "", which makes the vector
    unreusable by the embedding cache rather than reusable under the wrong
    model.

    `embedding_model_id` names the provider behind an `embedding` passed in
    directly - a vector reused from a cache or from a previous index. Without
    it a reused vector would be stored with an empty model id and stop matching
    `search`'s `embeddingModelId` filter, which is exactly how a cached chunk
    would silently vanish from results."""
    # Deliberately a plain assignment. This used to read
    # `content if content.endswith("\n") else content` - both branches
    # identical, so it never normalized anything. The readable intent was to
    # append the missing newline, but `build_chunk_id` hashes what is passed
    # here: adding one now would change every chunk id in every existing index
    # and force a full reindex, for a trailing newline. The name is kept
    # because the value is passed on under it below.
    normalized_content = content
    if embedding is None:
        embedding_model_id = ""
        if embedding_engine is None:
            raise ValueError("embedding_engine must be provided when embedding is omitted")
        embedding = embedding_engine.embed(normalized_content)
        embedding_model_id = str(getattr(embedding_engine, "providerId", "") or "")
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
