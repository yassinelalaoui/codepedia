from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


NodeKind = Literal["file", "symbol"]
EdgeType = Literal["import", "call", "inheritance"]
QueryDirection = Literal["incoming", "outgoing", "both"]
SelectionType = Literal["file", "module", "symbol"]


@dataclass(frozen=True, slots=True)
class DependencyNode:
    id: str
    kind: NodeKind
    name: str
    sourceFile: str
    symbolType: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    sourceId: str
    targetId: str
    type: EdgeType
    sourceFile: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GraphQuery:
    focusId: str
    direction: QueryDirection = "outgoing"
    relationType: EdgeType | None = None
    depth: int = 1


@dataclass(frozen=True, slots=True)
class DiagramExport:
    rootId: str
    selectionType: SelectionType
    nodes: tuple[DependencyNode, ...]
    edges: tuple[DependencyEdge, ...]
    generatedAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "rootId": self.rootId,
            "selectionType": self.selectionType,
            "generatedAt": self.generatedAt,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


@dataclass(frozen=True, slots=True)
class GraphPersistenceRecord:
    graphId: str
    repositoryRoot: str
    nodeCount: int
    edgeCount: int
    createdAt: str
    snapshotVersion: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DependencyGraphSnapshot:
    id: str
    sourceFile: str
    nodes: tuple[DependencyNode, ...]
    edges: tuple[DependencyEdge, ...]

