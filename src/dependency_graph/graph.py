from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from parser_engine.inventory import FileSymbolInventory

from .export import build_diagram_export
from .models import (
    DiagramExport,
    DependencyEdge,
    DependencyNode,
    EdgeType,
    GraphPersistenceRecord,
    GraphQuery,
    SelectionType,
)
from .persistence import load_snapshot_from_path, save_snapshot_to_path
from .queries import filter_edges, ordered_nodes


@dataclass(slots=True)
class _SimpleDiGraph:
    nodes: dict[str, DependencyNode] = field(default_factory=dict)
    edges: dict[tuple[str, str, str], DependencyEdge] = field(default_factory=dict)
    outgoing: dict[str, set[tuple[str, str, str]]] = field(default_factory=lambda: defaultdict(set))
    incoming: dict[str, set[tuple[str, str, str]]] = field(default_factory=lambda: defaultdict(set))

    def add_node(self, node: DependencyNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: DependencyEdge) -> None:
        key = (edge.sourceId, edge.targetId, edge.type)
        self.edges[key] = edge
        self.outgoing[edge.sourceId].add(key)
        self.incoming[edge.targetId].add(key)

    def successors(self, node_id: str) -> Iterator[str]:
        for source_id, target_id, _ in self.outgoing.get(node_id, set()):
            yield target_id

    def predecessors(self, node_id: str) -> Iterator[str]:
        for source_id, target_id, _ in self.incoming.get(node_id, set()):
            yield source_id


class DependencyGraph:
    def __init__(
        self,
        *,
        id: str,
        sourceFile: str,
        nodes: Iterable[DependencyNode] | None = None,
        edges: Iterable[DependencyEdge] | None = None,
    ) -> None:
        self.id = id
        self.sourceFile = sourceFile
        self.nodes: dict[str, DependencyNode] = {}
        self.edges: dict[tuple[str, str, str], DependencyEdge] = {}
        self._outgoing: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
        self._incoming: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
        self._name_index: dict[str, set[str]] = defaultdict(set)
        if nodes is not None:
            for node in nodes:
                self.add_node(node)
        if edges is not None:
            for edge in edges:
                self._add_edge_object(edge)

    @classmethod
    def build_from_inventories(
        cls,
        inventories: Iterable[FileSymbolInventory],
        *,
        id: str | None = None,
        sourceFile: str | None = None,
    ) -> "DependencyGraph":
        inventory_list = list(inventories)
        graph_id = id or _stable_graph_id(inventory_list)
        repository_root = sourceFile or _derive_repository_root(inventory_list)
        graph = cls(id=graph_id, sourceFile=repository_root)
        for inventory in inventory_list:
            graph._ingest_inventory_nodes(inventory)
        for inventory in inventory_list:
            graph._ingest_inventory_relations(inventory)
        return graph

    def add_node(self, node: DependencyNode) -> DependencyNode:
        existing = self.nodes.get(node.id)
        if existing is not None:
            return existing
        self.nodes[node.id] = node
        self._name_index[node.name].add(node.id)
        return node

    def addEdge(self, source: str | DependencyNode, target: str | DependencyNode, type: EdgeType) -> DependencyEdge:
        source_id = self._resolve_node_id(source)
        target_id = self._resolve_node_id(target)
        if source_id is None or target_id is None:
            raise ValueError("source and target nodes must exist before adding an edge")
        return self._add_edge_object(
            DependencyEdge(
                sourceId=source_id,
                targetId=target_id,
                type=type,
                sourceFile=self.nodes.get(source_id).sourceFile if source_id in self.nodes else self.sourceFile,
                metadata={},
            )
        )

    def remove_source_file(self, source_file: str) -> None:
        normalized = _normalize_path(source_file)
        node_ids = {
            node_id
            for node_id, node in self.nodes.items()
            if _normalize_path(node.sourceFile) == normalized
        }
        if not node_ids:
            return
        edge_keys = [key for key in self.edges if key[0] in node_ids or key[1] in node_ids]
        for key in edge_keys:
            edge = self.edges.pop(key)
            self._outgoing[edge.sourceId].discard(key)
            self._incoming[edge.targetId].discard(key)
        for node_id in node_ids:
            node = self.nodes.pop(node_id)
            self._name_index[node.name].discard(node_id)
            self._outgoing.pop(node_id, None)
            self._incoming.pop(node_id, None)

    def ingest_inventory(self, inventory: FileSymbolInventory) -> None:
        self._ingest_inventory_nodes(inventory)
        self._ingest_inventory_relations(inventory)

    def _ingest_inventory_nodes(self, inventory: FileSymbolInventory) -> None:
        file_node = self._ensure_file_node(inventory)
        for class_symbol in inventory.classes:
            self.add_node(
                DependencyNode(
                    id=class_symbol.id,
                    kind="symbol",
                    name=class_symbol.name,
                    sourceFile=inventory.sourceFile,
                    symbolType="class",
                    metadata={
                        "lineStart": class_symbol.lineStart,
                        "lineEnd": class_symbol.lineEnd,
                        "docstring": class_symbol.docstring,
                    },
                )
            )
        for function_symbol in inventory.functions:
            self.add_node(
                DependencyNode(
                    id=function_symbol.id,
                    kind="symbol",
                    name=function_symbol.name,
                    sourceFile=inventory.sourceFile,
                    symbolType="function",
                    metadata={
                        "lineStart": function_symbol.lineStart,
                        "lineEnd": function_symbol.lineEnd,
                        "docstring": function_symbol.docstring,
                    },
                )
            )

    def _ingest_inventory_relations(self, inventory: FileSymbolInventory) -> None:
        file_node = self._ensure_file_node(inventory)
        self._ingest_imports(inventory, file_node)
        self._ingest_calls(inventory)
        self._ingest_inheritance(inventory)

    def dependencies(self, focus: str | DependencyNode, *, relation_type: EdgeType | None = None) -> list[DependencyNode]:
        focus_id = self._resolve_node_id(focus)
        if focus_id is None:
            return []
        related = self._related_nodes(focus_id, outgoing=True, relation_type=relation_type)
        return ordered_nodes(related)

    def dependents(self, focus: str | DependencyNode, *, relation_type: EdgeType | None = None) -> list[DependencyNode]:
        focus_id = self._resolve_node_id(focus)
        if focus_id is None:
            return []
        related = self._related_nodes(focus_id, outgoing=False, relation_type=relation_type)
        return ordered_nodes(related)

    def files_importing(self, focus: str | DependencyNode) -> list[DependencyNode]:
        return [node for node in self.dependents(focus, relation_type="import") if node.kind == "file"]

    def functions_calling(self, focus: str | DependencyNode) -> list[DependencyNode]:
        return [node for node in self.dependents(focus, relation_type="call") if node.symbolType == "function"]

    def functions_called_by(self, focus: str | DependencyNode) -> list[DependencyNode]:
        return [node for node in self.dependencies(focus, relation_type="call") if node.symbolType == "function"]

    def classes_inheriting(self, focus: str | DependencyNode) -> list[DependencyNode]:
        return [node for node in self.dependents(focus, relation_type="inheritance") if node.symbolType == "class"]

    def classes_inherited_from(self, focus: str | DependencyNode) -> list[DependencyNode]:
        return [node for node in self.dependencies(focus, relation_type="inheritance") if node.symbolType == "class"]

    def query(self, query: GraphQuery) -> list[DependencyNode]:
        if query.direction == "outgoing":
            return self.dependencies(query.focusId, relation_type=query.relationType)
        if query.direction == "incoming":
            return self.dependents(query.focusId, relation_type=query.relationType)
        incoming = self.dependents(query.focusId, relation_type=query.relationType)
        outgoing = self.dependencies(query.focusId, relation_type=query.relationType)
        unique: dict[str, DependencyNode] = {node.id: node for node in incoming}
        unique.update({node.id: node for node in outgoing})
        return ordered_nodes(unique.values())

    def exportDiagram(self, root: str | DependencyNode, selectionType: SelectionType | None = None) -> DiagramExport:
        root_id = self._resolve_node_id(root)
        if root_id is None:
            root_id = root.id if isinstance(root, DependencyNode) else str(root)
            return build_diagram_export(root_id=root_id, selection_type=selectionType or "symbol", nodes=[], edges=[])
        root_node = self.nodes[root_id]
        selected_ids = {root_id}
        selected_ids.update(self._neighbor_ids(root_id, outgoing=True))
        selected_ids.update(self._neighbor_ids(root_id, outgoing=False))
        selected_nodes = [self.nodes[node_id] for node_id in selected_ids if node_id in self.nodes]
        selected_edges = [
            edge
            for edge in self.edges.values()
            if edge.sourceId in selected_ids and edge.targetId in selected_ids
        ]
        return build_diagram_export(
            root_id=root_id,
            selection_type=selectionType or root_node.kind,
            nodes=ordered_nodes(selected_nodes),
            edges=sorted(selected_edges, key=lambda edge: (edge.type, edge.sourceId, edge.targetId)),
        )

    def save(self, db_path: str | Path) -> GraphPersistenceRecord:
        return save_snapshot_to_path(
            db_path,
            graph_id=self.id,
            repository_root=self.sourceFile,
            created_at=datetime.now(timezone.utc).isoformat(),
            nodes=self.nodes.values(),
            edges=self.edges.values(),
        )

    @classmethod
    def load(cls, db_path: str | Path, *, graph_id: str) -> "DependencyGraph":
        _meta, nodes, edges = load_snapshot_from_path(db_path, graph_id=graph_id)
        repository_root = _meta["repository_root"]
        return cls(id=graph_id, sourceFile=str(repository_root), nodes=nodes, edges=edges)

    def _ensure_file_node(self, inventory: FileSymbolInventory) -> DependencyNode:
        file_node = DependencyNode(
            id=_file_node_id(inventory.sourceFile),
            kind="file",
            name=inventory.module.name,
            sourceFile=inventory.sourceFile,
            symbolType="module",
            metadata={
                "moduleId": inventory.module.id,
                "lineStart": inventory.module.lineStart,
                "lineEnd": inventory.module.lineEnd,
            },
        )
        return self.add_node(file_node)

    def _ingest_imports(self, inventory: FileSymbolInventory, file_node: DependencyNode) -> None:
        for import_record in inventory.imports:
            for target_id, target_node in self._resolve_import_targets(inventory, import_record.text):
                self._add_edge_object(
                    DependencyEdge(
                        sourceId=file_node.id,
                        targetId=target_id,
                        type="import",
                        sourceFile=inventory.sourceFile,
                        metadata={"text": import_record.text, "targetName": target_node.name},
                    )
                )

    def _ingest_calls(self, inventory: FileSymbolInventory) -> None:
        for call_relation in inventory.callRelations:
            caller_id = call_relation.callerSymbolId
            if caller_id not in self.nodes:
                continue
            target_id = self._resolve_symbol_target(
                call_relation.calleeSymbolIdOrName,
                symbol_type="function",
                source_file=inventory.sourceFile,
            )
            target_node = self._ensure_unresolved_symbol_node(
                target_id,
                name=call_relation.calleeSymbolIdOrName or "<unresolved>",
                symbol_type="function",
                source_file=inventory.sourceFile,
            )
            self._add_edge_object(
                DependencyEdge(
                    sourceId=caller_id,
                    targetId=target_node.id,
                    type="call",
                    sourceFile=inventory.sourceFile,
                    metadata={"rawTarget": call_relation.calleeSymbolIdOrName, "lineStart": call_relation.lineStart, "lineEnd": call_relation.lineEnd},
                )
            )

    def _ingest_inheritance(self, inventory: FileSymbolInventory) -> None:
        for inheritance in inventory.inheritanceRelations:
            if inheritance.subclassSymbolId not in self.nodes:
                continue
            target_id = self._resolve_symbol_target(
                inheritance.parentClassName,
                symbol_type="class",
                source_file=inventory.sourceFile,
            )
            target_node = self._ensure_unresolved_symbol_node(
                target_id,
                name=inheritance.parentClassName,
                symbol_type="class",
                source_file=inventory.sourceFile,
            )
            self._add_edge_object(
                DependencyEdge(
                    sourceId=inheritance.subclassSymbolId,
                    targetId=target_node.id,
                    type="inheritance",
                    sourceFile=inventory.sourceFile,
                    metadata={"rawTarget": inheritance.parentClassName, "lineStart": inheritance.lineStart, "lineEnd": inheritance.lineEnd},
                )
            )

    def _add_edge_object(self, edge: DependencyEdge) -> DependencyEdge:
        key = (edge.sourceId, edge.targetId, edge.type)
        existing = self.edges.get(key)
        if existing is not None:
            return existing
        self.edges[key] = edge
        self._outgoing[edge.sourceId].add(key)
        self._incoming[edge.targetId].add(key)
        return edge

    def _resolve_node_id(self, value: str | DependencyNode) -> str | None:
        if isinstance(value, DependencyNode):
            return value.id
        if value in self.nodes:
            return value
        normalized = _normalize_identifier(value)
        if normalized in self.nodes:
            return normalized
        if value.startswith("file::"):
            return value if value in self.nodes else None
        candidate = _file_node_id(value)
        if candidate in self.nodes:
            return candidate
        if value in self._name_index and len(self._name_index[value]) == 1:
            return next(iter(self._name_index[value]))
        return None

    def _related_nodes(self, focus_id: str, *, outgoing: bool, relation_type: EdgeType | None) -> list[DependencyNode]:
        edge_keys = self._outgoing.get(focus_id, set()) if outgoing else self._incoming.get(focus_id, set())
        related: dict[str, DependencyNode] = {}
        for edge_key in edge_keys:
            edge = self.edges[edge_key]
            if relation_type is not None and edge.type != relation_type:
                continue
            neighbor_id = edge.targetId if outgoing else edge.sourceId
            node = self.nodes.get(neighbor_id)
            if node is not None:
                related[node.id] = node
        return list(related.values())

    def _neighbor_ids(self, focus_id: str, *, outgoing: bool) -> set[str]:
        edge_keys = self._outgoing.get(focus_id, set()) if outgoing else self._incoming.get(focus_id, set())
        return {self.edges[edge_key].targetId if outgoing else self.edges[edge_key].sourceId for edge_key in edge_keys}

    def _resolve_import_targets(
        self,
        inventory: FileSymbolInventory,
        text: str,
    ) -> list[tuple[str, DependencyNode]]:
        candidates = _extract_import_candidates(text)
        resolved: list[tuple[str, DependencyNode]] = []
        for candidate in candidates:
            node = self._resolve_file_candidate(candidate, inventory.sourceFile)
            if node is None:
                unresolved_id = _unresolved_file_node_id(candidate)
                node = self.add_node(
                    DependencyNode(
                        id=unresolved_id,
                        kind="file",
                        name=candidate,
                        sourceFile=inventory.sourceFile,
                        symbolType="module",
                        metadata={"unresolved": True, "rawImport": text},
                    )
                )
            resolved.append((node.id, node))
        return resolved

    def _resolve_file_candidate(self, candidate: str, source_file: str) -> DependencyNode | None:
        normalized = _normalize_identifier(candidate)
        stem = _candidate_stem(candidate)
        path_stem = _candidate_path_stem(candidate)
        for node in self.nodes.values():
            if node.kind != "file":
                continue
            if node.sourceFile == source_file:
                continue
            file_name = _normalize_identifier(node.name)
            file_stem = _candidate_path_stem(node.sourceFile)
            if normalized in {file_name, file_stem}:
                return node
            if stem and stem in {file_name, file_stem}:
                return node
            if path_stem and path_stem in {file_name, file_stem}:
                return node
        return None

    def _resolve_symbol_target(self, candidate: str | None, *, symbol_type: str, source_file: str) -> str:
        if not candidate:
            return _unresolved_symbol_node_id(symbol_type, "<missing>")
        normalized = _normalize_identifier(candidate)
        tail = _normalize_identifier(candidate.split(".")[-1])
        candidates: list[DependencyNode] = []
        for node in self.nodes.values():
            if node.kind != "symbol" or node.symbolType != symbol_type:
                continue
            node_name = _normalize_identifier(node.name)
            node_id = _normalize_identifier(node.id)
            if node_name == normalized or node_name == tail:
                if node.sourceFile == source_file:
                    return node.id
                candidates.append(node)
            elif node_id == normalized or node_id == tail:
                return node.id
        if len(candidates) == 1:
            return candidates[0].id
        return _unresolved_symbol_node_id(symbol_type, candidate)

    def _ensure_unresolved_symbol_node(self, node_id: str, *, name: str | None, symbol_type: str, source_file: str) -> DependencyNode:
        existing = self.nodes.get(node_id)
        if existing is not None:
            return existing
        if node_id.startswith("unresolved::"):
            node = DependencyNode(
                id=node_id,
                kind="symbol",
                name=name or "<unresolved>",
                sourceFile=source_file,
                symbolType=symbol_type,
                metadata={"unresolved": True},
            )
            return self.add_node(node)
        node = DependencyNode(
            id=node_id,
            kind="symbol",
            name=name or node_id,
            sourceFile=source_file,
            symbolType=symbol_type,
            metadata={"unresolved": False},
        )
        return self.add_node(node)


def assemble_dependency_graph(
    inventories: Iterable[FileSymbolInventory],
    *,
    id: str | None = None,
    sourceFile: str | None = None,
) -> DependencyGraph:
    return DependencyGraph.build_from_inventories(inventories, id=id, sourceFile=sourceFile)


def _stable_graph_id(inventories: Iterable[FileSymbolInventory]) -> str:
    seeds = sorted(inventory.sourceFile for inventory in inventories)
    digest = hashlib.sha1("\n".join(seeds).encode("utf-8")).hexdigest()[:16]
    return f"graph_{digest}"


def _derive_repository_root(inventories: Iterable[FileSymbolInventory]) -> str:
    source_files = sorted(inventory.sourceFile for inventory in inventories)
    if not source_files:
        return ""
    if len(source_files) == 1:
        return str(Path(source_files[0]).parent)
    common = Path(source_files[0])
    for source_file in source_files[1:]:
        common = Path(_common_prefix(str(common), source_file))
    if not common or str(common) == ".":
        return str(Path(source_files[0]).parent)
    return str(common)


def _common_prefix(a: str, b: str) -> str:
    a_parts = Path(a).parts
    b_parts = Path(b).parts
    prefix: list[str] = []
    for left, right in zip(a_parts, b_parts, strict=False):
        if left != right:
            break
        prefix.append(left)
    return str(Path(*prefix)) if prefix else ""


def _file_node_id(source_file: str) -> str:
    return f"file::{_normalize_path(source_file)}"


def _unresolved_file_node_id(candidate: str) -> str:
    return f"file::external::{_normalize_identifier(candidate)}"


def _unresolved_symbol_node_id(symbol_type: str, candidate: str) -> str:
    return f"unresolved::{symbol_type}::{_normalize_identifier(candidate)}"


def _extract_import_candidates(text: str) -> list[str]:
    import re

    stripped = text.strip().rstrip(";")
    candidates: list[str] = []
    if stripped.startswith("import ") and " from " in stripped:
        right = stripped.split(" from ", 1)[1].strip()
        candidates.append(_strip_quotes(right))
    elif stripped.startswith("from "):
        left = stripped.split(" import ", 1)[0][5:].strip()
        candidates.append(left)
    elif stripped.startswith("import "):
        body = stripped[7:].strip()
        if body.startswith("(") and body.endswith(")"):
            body = body[1:-1]
        if " as " in body:
            body = body.split(" as ", 1)[0]
        if "," in body:
            candidates.extend(part.strip() for part in body.split(",") if part.strip())
        else:
            candidates.append(_strip_quotes(body))
    elif stripped.startswith("use "):
        candidates.append(stripped[4:].split(" as ", 1)[0])
    elif stripped.startswith("extern crate "):
        candidates.append(stripped[len("extern crate ") :])
    if not candidates:
        token_matches = re.findall(r"[A-Za-z_][A-Za-z0-9_./:]*", stripped)
        candidates.extend(token_matches[-1:])
    normalized = []
    for candidate in candidates:
        candidate = candidate.strip().strip("{}()")
        if candidate:
            normalized.append(candidate)
    return normalized


def _strip_quotes(value: str) -> str:
    return value.strip().strip("'\"")


def _normalize_path(value: str) -> str:
    return Path(value).as_posix().replace("\\", "/")


def _normalize_identifier(value: str) -> str:
    return _normalize_path(value).strip().replace(" ", "").replace("-", "_")


def _candidate_stem(value: str) -> str:
    return Path(_strip_quotes(value)).stem


def _candidate_path_stem(value: str) -> str:
    path = Path(_strip_quotes(value))
    if path.suffix:
        return path.stem
    return path.name.split(".")[-1]
