from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Literal, Sequence


Vector = tuple[float, ...]
ChunkType = Literal["code", "summary"]
ChunkLifecycle = Literal["added", "replaced", "removed", "unchanged"]


def _coerce_vector(values: Sequence[float]) -> Vector:
    return tuple(float(value) for value in values)


def _normalize_path(path: str | Path) -> str:
    return Path(path).expanduser().as_posix().replace("\\", "/")


@dataclass(frozen=True, slots=True)
class CodeChunk:
    id: str
    content: str
    embedding: Vector
    sourceSymbolId: str
    sourceFilePath: str = ""
    chunkType: ChunkType = "code"
    metadata: dict[str, Any] = field(default_factory=dict)
    # The ProviderRef string (e.g. "openai:text-embedding-3-small") of
    # whichever provider/model actually computed `embedding` (spec FR-009).
    # Empty for a chunk built before this feature shipped.
    embeddingModelId: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("chunk id must be provided")
        if not self.content:
            raise ValueError("chunk content must be provided")
        if not self.sourceSymbolId:
            raise ValueError("chunk sourceSymbolId must be provided")
        if self.chunkType not in {"code", "summary"}:
            raise ValueError("chunkType must be 'code' or 'summary'")
        object.__setattr__(self, "embedding", _coerce_vector(self.embedding))
        object.__setattr__(self, "sourceFilePath", _normalize_path(self.sourceFilePath) if self.sourceFilePath else "")

    @property
    def dimensionality(self) -> int:
        return len(self.embedding)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VectorEntry:
    chunkId: str
    # May be empty. `VectorIndex` loads its entries without vectors, because
    # `VectorMatrix` already holds every one of them as a float32 row and a
    # second copy as Python floats costs 24 bytes per value - the difference
    # between the ~307 MB pyproject.toml claims at 50k chunks of 1536
    # dimensions and the ~2.3 GB the two representations together actually
    # occupied. `dimensionality` is stored either way, so an entry still knows
    # its own length; scoring reads the vector from the matrix.
    #
    # Callers that build an entry from a chunk (`from_chunk`, `rank_entries`)
    # still carry the vector, which is what keeps `search.score_entry` usable
    # for ad-hoc chunks that were never indexed.
    vector: Vector
    dimensionality: int
    sourceFilePath: str
    sourceSymbolId: str
    chunkType: ChunkType
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    embeddingModelId: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "vector", _coerce_vector(self.vector))
        object.__setattr__(self, "sourceFilePath", _normalize_path(self.sourceFilePath) if self.sourceFilePath else "")
        if self.vector and self.dimensionality != len(self.vector):
            raise ValueError("dimensionality must match vector length")

    @property
    def hasVector(self) -> bool:
        return bool(self.vector)

    @classmethod
    def from_chunk(cls, chunk: CodeChunk) -> "VectorEntry":
        return cls(
            chunkId=chunk.id,
            vector=chunk.embedding,
            dimensionality=chunk.dimensionality,
            sourceFilePath=chunk.sourceFilePath,
            sourceSymbolId=chunk.sourceSymbolId,
            chunkType=chunk.chunkType,
            content=chunk.content,
            metadata=dict(chunk.metadata),
            embeddingModelId=chunk.embeddingModelId,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SearchQuery:
    queryText: str
    k: int
    filters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.queryText:
            raise ValueError("queryText must be provided")
        if self.k <= 0:
            raise ValueError("k must be positive")


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunkId: str
    content: str
    score: float
    sourceSymbolId: str
    sourceFilePath: str
    chunkType: ChunkType

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class IndexRecord:
    id: str
    repositoryRoot: str
    metadataPath: str
    createdAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    lastIndexedAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        object.__setattr__(self, "repositoryRoot", str(Path(self.repositoryRoot).expanduser().resolve()))
        object.__setattr__(self, "metadataPath", str(Path(self.metadataPath).expanduser()))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
