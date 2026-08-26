from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from parser_engine import Parameter


SymbolKind = Literal["module", "class", "function"]
EdgeType = Literal["import", "call", "inheritance"]


@dataclass(frozen=True, slots=True)
class Repository:
    id: str
    rootPath: str
    detectedLanguages: tuple[str, ...] = ()
    lastIndexedAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SourceFile:
    id: str
    repositoryId: str
    path: str
    language: str
    contentHash: str
    lastModified: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Symbol:
    id: str
    sourceFileId: str
    kind: SymbolKind
    name: str
    lineStart: int
    lineEnd: int
    docstring: str = ""
    generatedSummary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.lineStart < 1 or self.lineEnd < 1:
            raise ValueError("symbol line positions must be positive")
        if self.lineStart > self.lineEnd:
            raise ValueError("symbol lineStart must be <= lineEnd")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ModuleSymbol(Symbol):
    filePath: str = ""
    imports: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Zero-arg super() breaks here on Python <3.14: @dataclass(slots=True)
        # recreates the class, but the __post_init__ closure's __class__ cell
        # still points at the pre-slots class (CPython gh-91126).
        Symbol.__post_init__(self)


@dataclass(frozen=True, slots=True)
class ClassSymbol(Symbol):
    parentClass: str | None = None
    methods: tuple[str, ...] = ()
    nestedSymbols: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        Symbol.__post_init__(self)


@dataclass(frozen=True, slots=True)
class FunctionSymbol(Symbol):
    parameters: tuple[Parameter, ...] = ()
    returnType: str | None = None
    nestedSymbols: tuple[str, ...] = ()
    owner: str = "module"

    def __post_init__(self) -> None:
        Symbol.__post_init__(self)


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    sourceId: str
    targetId: str
    type: EdgeType
    sourceFileId: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DependencyGraph:
    id: str
    repositoryId: str
    nodes: tuple[str, ...] = ()
    edges: tuple[DependencyEdge, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "repositoryId": self.repositoryId,
            "nodes": list(self.nodes),
            "edges": [edge.to_dict() for edge in self.edges],
        }


@dataclass(frozen=True, slots=True)
class SourceFileBundle:
    file: SourceFile
    module: ModuleSymbol
    classes: tuple[ClassSymbol, ...]
    functions: tuple[FunctionSymbol, ...]
    dependencyEdges: tuple[DependencyEdge, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file.to_dict(),
            "module": self.module.to_dict(),
            "classes": [item.to_dict() for item in self.classes],
            "functions": [item.to_dict() for item in self.functions],
            "dependencyEdges": [edge.to_dict() for edge in self.dependencyEdges],
        }


@dataclass(frozen=True, slots=True)
class RepositoryBundle:
    repository: Repository
    files: tuple[SourceFileBundle, ...]
    graph: DependencyGraph

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository.to_dict(),
            "files": [bundle.to_dict() for bundle in self.files],
            "graph": self.graph.to_dict(),
        }
