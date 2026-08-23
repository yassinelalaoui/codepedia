from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("text must not be empty")
    return text


def _dedupe_preserve_order(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return tuple(ordered)


@dataclass(frozen=True, slots=True)
class Citation:
    symbolId: str
    filePath: str
    chunkId: str
    chunkType: str = "code"
    score: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbolId", _normalize_text(self.symbolId))
        object.__setattr__(self, "filePath", _normalize_text(self.filePath).replace("\\", "/"))
        object.__setattr__(self, "chunkId", _normalize_text(self.chunkId))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    chunkId: str
    content: str
    score: float
    sourceSymbolId: str
    sourceFilePath: str
    chunkType: str = "code"

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunkId", _normalize_text(self.chunkId))
        object.__setattr__(self, "content", _normalize_text(self.content))
        object.__setattr__(self, "sourceSymbolId", _normalize_text(self.sourceSymbolId))
        object.__setattr__(self, "sourceFilePath", _normalize_text(self.sourceFilePath).replace("\\", "/"))

    def citation(self) -> Citation:
        return Citation(
            symbolId=self.sourceSymbolId,
            filePath=self.sourceFilePath,
            chunkId=self.chunkId,
            chunkType=self.chunkType,
            score=self.score,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str
    citedSymbolIds: tuple[str, ...] = ()
    citedFilePaths: tuple[str, ...] = ()
    timestamp: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", _normalize_text(self.role))
        object.__setattr__(self, "content", _normalize_text(self.content))
        object.__setattr__(self, "citedSymbolIds", _dedupe_preserve_order(tuple(_normalize_text(item) for item in self.citedSymbolIds)))
        object.__setattr__(self, "citedFilePaths", _dedupe_preserve_order(tuple(_normalize_text(item).replace("\\", "/") for item in self.citedFilePaths)))
        object.__setattr__(self, "timestamp", _normalize_text(self.timestamp))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RAGContext:
    question: str
    conversationHistory: tuple[ChatMessage, ...] = ()
    retrievedEvidence: tuple[RetrievedEvidence, ...] = ()
    citationMap: tuple[Citation, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "question", _normalize_text(self.question))

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "conversationHistory": [item.to_dict() for item in self.conversationHistory],
            "retrievedEvidence": [item.to_dict() for item in self.retrievedEvidence],
            "citationMap": [item.to_dict() for item in self.citationMap],
        }


@dataclass
class ChatSession:
    id: str
    messages: list[ChatMessage] = field(default_factory=list)
    vectorIndex: Any | None = None
    embeddingEngine: Any | None = None
    llmEngine: Any | None = None
    topK: int = 5
    createdAt: str = field(default_factory=_utc_now)
    lastActivityAt: str = field(default_factory=_utc_now)
    messageStore: Any | None = None

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id)
        self.messages = list(self.messages)
        if self.topK <= 0:
            raise ValueError("topK must be positive")
        self.createdAt = _normalize_text(self.createdAt)
        self.lastActivityAt = _normalize_text(self.lastActivityAt)
