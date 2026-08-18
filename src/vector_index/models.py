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
    vector: Vector
    dimensionality: int
    sourceFilePath: str
    sourceSymbolId: str
    chunkType: ChunkType
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "vector", _coerce_vector(self.vector))
        object.__setattr__(self, "sourceFilePath", _normalize_path(self.sourceFilePath) if self.sourceFilePath else "")
        if self.dimensionality != len(self.vector):
            raise ValueError("dimensionality must match vector length")

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
