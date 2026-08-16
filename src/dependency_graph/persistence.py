from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Iterable

from .models import DependencyEdge, DependencyNode, GraphPersistenceRecord


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS graphs (
        graph_id TEXT PRIMARY KEY,
        repository_root TEXT NOT NULL,
        snapshot_version INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        node_count INTEGER NOT NULL,
        edge_count INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nodes (
        graph_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        name TEXT NOT NULL,
        source_file TEXT NOT NULL,
        symbol_type TEXT,
        metadata TEXT NOT NULL,
        PRIMARY KEY (graph_id, node_id),
        FOREIGN KEY (graph_id) REFERENCES graphs(graph_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS edges (
        graph_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        type TEXT NOT NULL,
        source_file TEXT,
        metadata TEXT NOT NULL,
        PRIMARY KEY (graph_id, source_id, target_id, type),
        FOREIGN KEY (graph_id) REFERENCES graphs(graph_id) ON DELETE CASCADE
    )
    """,
)


class DependencyGraphPersistenceError(RuntimeError):
    pass


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    for statement in SCHEMA_STATEMENTS:
        connection.execute(statement)


def save_snapshot(
    connection: sqlite3.Connection,
    *,
    graph_id: str,
    repository_root: str,
    created_at: str,
    nodes: Iterable[DependencyNode],
    edges: Iterable[DependencyEdge],
    snapshot_version: int = 1,
) -> GraphPersistenceRecord:
    ensure_schema(connection)
    node_list = list(nodes)
    edge_list = list(edges)
    with connection:
        connection.execute("DELETE FROM edges WHERE graph_id = ?", (graph_id,))
        connection.execute("DELETE FROM nodes WHERE graph_id = ?", (graph_id,))
        connection.execute("DELETE FROM graphs WHERE graph_id = ?", (graph_id,))
        connection.execute(
            """
            INSERT INTO graphs (graph_id, repository_root, snapshot_version, created_at, node_count, edge_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (graph_id, repository_root, snapshot_version, created_at, len(node_list), len(edge_list)),
        )
        for node in node_list:
            connection.execute(
                """
                INSERT INTO nodes (graph_id, node_id, kind, name, source_file, symbol_type, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    graph_id,
                    node.id,
                    node.kind,
                    node.name,
                    node.sourceFile,
                    node.symbolType,
                    json.dumps(node.metadata, sort_keys=True),
                ),
            )
        for edge in edge_list:
            connection.execute(
                """
                INSERT INTO edges (graph_id, source_id, target_id, type, source_file, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    graph_id,
                    edge.sourceId,
                    edge.targetId,
                    edge.type,
                    edge.sourceFile,
                    json.dumps(edge.metadata, sort_keys=True),
                ),
            )
    return GraphPersistenceRecord(
        graphId=graph_id,
        repositoryRoot=repository_root,
        nodeCount=len(node_list),
        edgeCount=len(edge_list),
        createdAt=created_at,
        snapshotVersion=snapshot_version,
    )


def load_snapshot(connection: sqlite3.Connection, *, graph_id: str) -> tuple[dict[str, object], list[DependencyNode], list[DependencyEdge]]:
    ensure_schema(connection)
    graph_row = connection.execute(
        "SELECT graph_id, repository_root, snapshot_version, created_at, node_count, edge_count FROM graphs WHERE graph_id = ?",
        (graph_id,),
    ).fetchone()
    if graph_row is None:
        raise DependencyGraphPersistenceError(f"graph not found: {graph_id}")
    node_rows = connection.execute(
        "SELECT node_id, kind, name, source_file, symbol_type, metadata FROM nodes WHERE graph_id = ? ORDER BY node_id",
        (graph_id,),
    ).fetchall()
    edge_rows = connection.execute(
        "SELECT source_id, target_id, type, source_file, metadata FROM edges WHERE graph_id = ? ORDER BY source_id, target_id, type",
        (graph_id,),
    ).fetchall()
    nodes = [
        DependencyNode(
            id=row[0],
            kind=row[1],
            name=row[2],
            sourceFile=row[3],
            symbolType=row[4],
            metadata=json.loads(row[5]) if row[5] else {},
        )
        for row in node_rows
    ]
    edges = [
        DependencyEdge(
            sourceId=row[0],
            targetId=row[1],
            type=row[2],
            sourceFile=row[3],
            metadata=json.loads(row[4]) if row[4] else {},
        )
        for row in edge_rows
    ]
    return (
        {
            "graph_id": graph_row[0],
            "repository_root": graph_row[1],
            "snapshot_version": graph_row[2],
            "created_at": graph_row[3],
            "node_count": graph_row[4],
            "edge_count": graph_row[5],
        },
        nodes,
        edges,
    )


def save_snapshot_to_path(
    db_path: str | Path,
    *,
    graph_id: str,
    repository_root: str,
    created_at: str,
    nodes: Iterable[DependencyNode],
    edges: Iterable[DependencyEdge],
    snapshot_version: int = 1,
) -> GraphPersistenceRecord:
    # `with sqlite3.connect(...)` only manages the transaction (commit/rollback
    # on exit) - it does not close the connection, which can leave the file
    # locked (e.g. blocking a directory rename on Windows) until the
    # connection object happens to be garbage-collected. `closing()` ensures
    # it's actually closed once this function returns.
    with closing(sqlite3.connect(str(db_path))) as connection:
        with connection:
            return save_snapshot(
                connection,
                graph_id=graph_id,
                repository_root=repository_root,
                created_at=created_at,
                nodes=nodes,
                edges=edges,
                snapshot_version=snapshot_version,
            )


def load_snapshot_from_path(db_path: str | Path, *, graph_id: str) -> tuple[dict[str, object], list[DependencyNode], list[DependencyEdge]]:
    with closing(sqlite3.connect(str(db_path))) as connection:
        return load_snapshot(connection, graph_id=graph_id)
