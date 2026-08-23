from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from parser_engine import ClassSymbol as ExtractedClassSymbol
from parser_engine import FileSymbolInventory, FunctionSymbol as ExtractedFunctionSymbol, ModuleSymbol as ExtractedModuleSymbol, SourceFile

from .fingerprints import compute_content_hash
from .models import (
    ClassSymbol,
    DependencyEdge,
    DependencyGraph,
    FunctionSymbol,
    ModuleSymbol,
    Repository,
    RepositoryBundle,
    SourceFile as StoredSourceFile,
    SourceFileBundle,
    Symbol,
)


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS repositories (
        id TEXT PRIMARY KEY,
        root_path TEXT NOT NULL UNIQUE,
        detected_languages TEXT NOT NULL,
        last_indexed_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_files (
        id TEXT PRIMARY KEY,
        repository_id TEXT NOT NULL,
        path TEXT NOT NULL,
        language TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        last_modified TEXT NOT NULL,
        UNIQUE(repository_id, path),
        FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS symbols (
        id TEXT PRIMARY KEY,
        source_file_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        name TEXT NOT NULL,
        line_start INTEGER NOT NULL,
        line_end INTEGER NOT NULL,
        docstring TEXT NOT NULL,
        generated_summary TEXT NOT NULL,
        metadata TEXT NOT NULL,
        FOREIGN KEY (source_file_id) REFERENCES source_files(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS module_symbols (
        symbol_id TEXT PRIMARY KEY,
        file_path TEXT NOT NULL,
        imports TEXT NOT NULL,
        FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS class_symbols (
        symbol_id TEXT PRIMARY KEY,
        parent_class TEXT,
        methods TEXT NOT NULL,
        nested_symbols TEXT NOT NULL,
        FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS function_symbols (
        symbol_id TEXT PRIMARY KEY,
        parameters TEXT NOT NULL,
        return_type TEXT,
        nested_symbols TEXT NOT NULL,
        owner TEXT NOT NULL,
        FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dependency_graphs (
        id TEXT PRIMARY KEY,
        repository_id TEXT NOT NULL,
        last_indexed_at TEXT NOT NULL,
        FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dependency_edges (
        graph_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        type TEXT NOT NULL,
        source_file_id TEXT NOT NULL,
        metadata TEXT NOT NULL,
        PRIMARY KEY (graph_id, source_id, target_id, type),
        FOREIGN KEY (graph_id) REFERENCES dependency_graphs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        last_activity_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        cited_symbol_ids TEXT NOT NULL,
        cited_file_paths TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_source_files_repository_path ON source_files(repository_id, path)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_source_file ON symbols(source_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_dependency_edges_source_file ON dependency_edges(source_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_dependency_edges_target_id ON dependency_edges(target_id)",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_timestamp ON chat_messages(session_id, timestamp)",
)


def connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    for statement in SCHEMA_STATEMENTS:
        connection.execute(statement)


def stable_repository_id(root_path: str | Path) -> str:
    normalized = Path(root_path).expanduser().resolve().as_posix()
    return f"repo::{normalized}"


def stable_source_file_id(repository_id: str, path: str | Path) -> str:
    normalized = Path(path).as_posix().replace("\\", "/")
    return f"{repository_id}::file::{normalized}"


def stable_symbol_id(source_file_id: str, kind: str, name: str, line_start: int, line_end: int) -> str:
    seed = f"{source_file_id}|{kind}|{name}|{line_start}|{line_end}"
    import hashlib

    return f"symbol_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"


def upsert_repository(
    connection: sqlite3.Connection,
    *,
    root_path: str | Path,
    detected_languages: Iterable[str],
    last_indexed_at: str,
) -> Repository:
    repository_id = stable_repository_id(root_path)
    repository = Repository(
        id=repository_id,
        rootPath=str(Path(root_path).expanduser().resolve()),
        detectedLanguages=tuple(sorted({language for language in detected_languages})),
        lastIndexedAt=last_indexed_at,
    )
    with connection:
        connection.execute(
            """
            INSERT INTO repositories (id, root_path, detected_languages, last_indexed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                root_path = excluded.root_path,
                detected_languages = excluded.detected_languages,
                last_indexed_at = excluded.last_indexed_at
            """,
            (
                repository.id,
                repository.rootPath,
                json.dumps(repository.detectedLanguages),
                repository.lastIndexedAt,
            ),
        )
        connection.execute(
            """
            INSERT INTO dependency_graphs (id, repository_id, last_indexed_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                repository_id = excluded.repository_id,
                last_indexed_at = excluded.last_indexed_at
            """,
            (repository.id, repository.id, repository.lastIndexedAt),
        )
    return repository


def file_record_from_source(
    repository_id: str,
    source_file: SourceFile,
    *,
    content_hash: str | None = None,
    last_modified: str,
) -> StoredSourceFile:
    return StoredSourceFile(
        id=stable_source_file_id(repository_id, source_file.path),
        repositoryId=repository_id,
        path=Path(source_file.path).as_posix().replace("\\", "/"),
        language=source_file.language,
        contentHash=content_hash or compute_content_hash(source_file),
        lastModified=last_modified,
    )


def upsert_source_file_bundle(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
    source_file: SourceFile,
    inventory: FileSymbolInventory,
    content_hash: str,
    last_modified: str,
    dependency_edges: Iterable[DependencyEdge] = (),
) -> StoredSourceFile:
    file_record = file_record_from_source(
        repository_id,
        source_file,
        content_hash=content_hash,
        last_modified=last_modified,
    )
    module = _convert_module_symbol(file_record.id, inventory.module)
    classes = [_convert_class_symbol(file_record.id, item) for item in inventory.classes]
    functions = [_convert_function_symbol(file_record.id, item) for item in inventory.functions]
    symbols = [module, *classes, *functions]
    edge_list = list(dependency_edges)
    with connection:
        _delete_source_file_records(connection, file_record.id)
        connection.execute(
            """
            INSERT INTO source_files (id, repository_id, path, language, content_hash, last_modified)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                file_record.id,
                file_record.repositoryId,
                file_record.path,
                file_record.language,
                file_record.contentHash,
                file_record.lastModified,
            ),
        )
        for symbol in symbols:
            try:
                _insert_symbol_record(connection, file_record.id, symbol)
            except sqlite3.IntegrityError as exc:
                conflicting = connection.execute(
                    "SELECT source_file_id, kind, name, line_start, line_end FROM symbols WHERE id = ?",
                    (symbol.id,),
                ).fetchone()
                conflict_detail = (
                    f"already belongs to source_file_id={conflicting['source_file_id']!r} "
                    f"({conflicting['kind']} {conflicting['name']!r} "
                    f"lines {conflicting['line_start']}-{conflicting['line_end']})"
                    if conflicting is not None
                    else "no existing row found for that id (unexpected)"
                )
                raise sqlite3.IntegrityError(
                    f"Duplicate symbol id {symbol.id!r} while inserting {symbol.kind} {symbol.name!r} "
                    f"(lines {symbol.lineStart}-{symbol.lineEnd}) for source_file_id={file_record.id!r} "
                    f"(path={file_record.path!r}): {conflict_detail}"
                ) from exc
        for edge in edge_list:
            _insert_dependency_edge(connection, repository_id, edge)
    return file_record


def _delete_source_file_records(connection: sqlite3.Connection, source_file_id: str) -> None:
    symbol_rows = connection.execute("SELECT id FROM symbols WHERE source_file_id = ?", (source_file_id,)).fetchall()
    symbol_ids = [row["id"] for row in symbol_rows]
    if symbol_ids:
        connection.execute(
            "DELETE FROM dependency_edges WHERE source_file_id = ? OR source_id IN ({0}) OR target_id IN ({0})".format(",".join("?" for _ in symbol_ids)),
            (source_file_id, *symbol_ids, *symbol_ids),
        )
    else:
        connection.execute("DELETE FROM dependency_edges WHERE source_file_id = ?", (source_file_id,))
    connection.execute("DELETE FROM module_symbols WHERE symbol_id IN (SELECT id FROM symbols WHERE source_file_id = ?)", (source_file_id,))
    connection.execute("DELETE FROM class_symbols WHERE symbol_id IN (SELECT id FROM symbols WHERE source_file_id = ?)", (source_file_id,))
    connection.execute("DELETE FROM function_symbols WHERE symbol_id IN (SELECT id FROM symbols WHERE source_file_id = ?)", (source_file_id,))
    connection.execute("DELETE FROM symbols WHERE source_file_id = ?", (source_file_id,))
    connection.execute("DELETE FROM source_files WHERE id = ?", (source_file_id,))


def delete_source_file(connection: sqlite3.Connection, *, repository_id: str, path: str | Path) -> None:
    source_file_id = stable_source_file_id(repository_id, path)
    with connection:
        _delete_source_file_records(connection, source_file_id)


def _insert_symbol_record(connection: sqlite3.Connection, source_file_id: str, symbol: Symbol) -> None:
    connection.execute(
        """
        INSERT INTO symbols (id, source_file_id, kind, name, line_start, line_end, docstring, generated_summary, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol.id,
            source_file_id,
            symbol.kind,
            symbol.name,
            symbol.lineStart,
            symbol.lineEnd,
            symbol.docstring,
            symbol.generatedSummary,
            json.dumps(symbol.metadata, sort_keys=True),
        ),
    )
    if isinstance(symbol, ModuleSymbol):
        connection.execute(
            "INSERT INTO module_symbols (symbol_id, file_path, imports) VALUES (?, ?, ?)",
            (symbol.id, symbol.filePath, json.dumps(list(symbol.imports), sort_keys=True)),
        )
    elif isinstance(symbol, ClassSymbol):
        connection.execute(
            "INSERT INTO class_symbols (symbol_id, parent_class, methods, nested_symbols) VALUES (?, ?, ?, ?)",
            (symbol.id, symbol.parentClass, json.dumps(list(symbol.methods), sort_keys=True), json.dumps(list(symbol.nestedSymbols), sort_keys=True)),
        )
    elif isinstance(symbol, FunctionSymbol):
        connection.execute(
            "INSERT INTO function_symbols (symbol_id, parameters, return_type, nested_symbols, owner) VALUES (?, ?, ?, ?, ?)",
            (
                symbol.id,
                json.dumps([param.to_dict() for param in symbol.parameters], sort_keys=True),
                symbol.returnType,
                json.dumps(list(symbol.nestedSymbols), sort_keys=True),
                symbol.owner,
            ),
        )


def _convert_module_symbol(source_file_id: str, module: ExtractedModuleSymbol) -> ModuleSymbol:
    return ModuleSymbol(
        id=module.id,
        sourceFileId=source_file_id,
        kind="module",
        name=module.name,
        lineStart=module.lineStart,
        lineEnd=module.lineEnd,
        docstring=module.docstring,
        generatedSummary=module.generatedSummary,
        metadata={"filePath": module.filePath},
        filePath=module.filePath,
        imports=tuple(_import_texts(module.imports)),
    )


def _convert_class_symbol(source_file_id: str, class_symbol: ExtractedClassSymbol) -> ClassSymbol:
    return ClassSymbol(
        id=class_symbol.id,
        sourceFileId=source_file_id,
        kind="class",
        name=class_symbol.name,
        lineStart=class_symbol.lineStart,
        lineEnd=class_symbol.lineEnd,
        docstring=class_symbol.docstring,
        generatedSummary=class_symbol.generatedSummary,
        metadata={"parentClass": class_symbol.parentClass},
        parentClass=class_symbol.parentClass,
        methods=tuple(item.id for item in class_symbol.methods if hasattr(item, "id")),
        nestedSymbols=tuple(item.id for item in class_symbol.nestedSymbols if hasattr(item, "id")),
    )


def _convert_function_symbol(source_file_id: str, function_symbol: ExtractedFunctionSymbol) -> FunctionSymbol:
    return FunctionSymbol(
        id=function_symbol.id,
        sourceFileId=source_file_id,
        kind="function",
        name=function_symbol.name,
        lineStart=function_symbol.lineStart,
        lineEnd=function_symbol.lineEnd,
        docstring=function_symbol.docstring,
        generatedSummary=function_symbol.generatedSummary,
        metadata={
            "owner": function_symbol.owner,
            "returnType": function_symbol.returnType,
            "decorators": list(function_symbol.decorators),
        },
        parameters=function_symbol.parameters,
        returnType=function_symbol.returnType,
        nestedSymbols=tuple(item.id for item in function_symbol.nestedSymbols if hasattr(item, "id")),
        owner=function_symbol.owner,
    )


def _import_texts(imports: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for item in imports:
        if hasattr(item, "text"):
            result.append(str(getattr(item, "text")))
        else:
            result.append(str(item))
    return result


def _insert_dependency_edge(connection: sqlite3.Connection, repository_id: str, edge: DependencyEdge) -> None:
    connection.execute(
        """
        INSERT INTO dependency_edges (graph_id, source_id, target_id, type, source_file_id, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(graph_id, source_id, target_id, type) DO UPDATE SET
            source_file_id = excluded.source_file_id,
            metadata = excluded.metadata
        """,
        (repository_id, edge.sourceId, edge.targetId, edge.type, edge.sourceFileId, json.dumps(edge.metadata, sort_keys=True)),
    )


def load_repository(connection: sqlite3.Connection, *, repository_id: str) -> Repository:
    row = connection.execute("SELECT id, root_path, detected_languages, last_indexed_at FROM repositories WHERE id = ?", (repository_id,)).fetchone()
    if row is None:
        raise KeyError(repository_id)
    return Repository(
        id=row["id"],
        rootPath=row["root_path"],
        detectedLanguages=tuple(json.loads(row["detected_languages"])),
        lastIndexedAt=row["last_indexed_at"],
    )


def load_source_file(connection: sqlite3.Connection, *, source_file_id: str) -> StoredSourceFile:
    row = connection.execute(
        "SELECT id, repository_id, path, language, content_hash, last_modified FROM source_files WHERE id = ?",
        (source_file_id,),
    ).fetchone()
    if row is None:
        raise KeyError(source_file_id)
    return StoredSourceFile(
        id=row["id"],
        repositoryId=row["repository_id"],
        path=row["path"],
        language=row["language"],
        contentHash=row["content_hash"],
        lastModified=row["last_modified"],
    )


def load_source_file_by_path(connection: sqlite3.Connection, *, repository_id: str, path: str | Path) -> StoredSourceFile:
    row = connection.execute(
        "SELECT id FROM source_files WHERE repository_id = ? AND path = ?",
        (repository_id, Path(path).as_posix().replace("\\", "/")),
    ).fetchone()
    if row is None:
        raise KeyError(str(path))
    return load_source_file(connection, source_file_id=row["id"])


def _load_symbols(connection: sqlite3.Connection, *, source_file_id: str) -> list[Symbol]:
    rows = connection.execute(
        "SELECT id, kind, name, line_start, line_end, docstring, generated_summary, metadata FROM symbols WHERE source_file_id = ? ORDER BY line_start, line_end, name",
        (source_file_id,),
    ).fetchall()
    symbols: list[Symbol] = []
    for row in rows:
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        if row["kind"] == "module":
            module_row = connection.execute("SELECT file_path, imports FROM module_symbols WHERE symbol_id = ?", (row["id"],)).fetchone()
            symbols.append(
                ModuleSymbol(
                    id=row["id"],
                    sourceFileId=source_file_id,
                    kind="module",
                    name=row["name"],
                    lineStart=row["line_start"],
                    lineEnd=row["line_end"],
                    docstring=row["docstring"],
                    generatedSummary=row["generated_summary"],
                    metadata=metadata,
                    filePath=module_row["file_path"] if module_row else "",
                    imports=tuple(json.loads(module_row["imports"])) if module_row else (),
                )
            )
        elif row["kind"] == "class":
            class_row = connection.execute("SELECT parent_class, methods, nested_symbols FROM class_symbols WHERE symbol_id = ?", (row["id"],)).fetchone()
            symbols.append(
                ClassSymbol(
                    id=row["id"],
                    sourceFileId=source_file_id,
                    kind="class",
                    name=row["name"],
                    lineStart=row["line_start"],
                    lineEnd=row["line_end"],
                    docstring=row["docstring"],
                    generatedSummary=row["generated_summary"],
                    metadata=metadata,
                    parentClass=class_row["parent_class"] if class_row else None,
                    methods=tuple(json.loads(class_row["methods"])) if class_row else (),
                    nestedSymbols=tuple(json.loads(class_row["nested_symbols"])) if class_row else (),
                )
            )
        elif row["kind"] == "function":
            function_row = connection.execute("SELECT parameters, return_type, nested_symbols, owner FROM function_symbols WHERE symbol_id = ?", (row["id"],)).fetchone()
            from parser_engine import Parameter

            parameters = tuple(Parameter(**item) for item in json.loads(function_row["parameters"])) if function_row else ()
            symbols.append(
                FunctionSymbol(
                    id=row["id"],
                    sourceFileId=source_file_id,
                    kind="function",
                    name=row["name"],
                    lineStart=row["line_start"],
                    lineEnd=row["line_end"],
                    docstring=row["docstring"],
                    generatedSummary=row["generated_summary"],
                    metadata=metadata,
                    parameters=parameters,
                    returnType=function_row["return_type"] if function_row else None,
                    nestedSymbols=tuple(json.loads(function_row["nested_symbols"])) if function_row else (),
                    owner=function_row["owner"] if function_row else "module",
                )
            )
    return symbols


def load_source_file_bundle(connection: sqlite3.Connection, *, source_file_id: str) -> SourceFileBundle:
    source_file = load_source_file(connection, source_file_id=source_file_id)
    symbols = _load_symbols(connection, source_file_id=source_file_id)
    modules = [symbol for symbol in symbols if isinstance(symbol, ModuleSymbol)]
    classes = [symbol for symbol in symbols if isinstance(symbol, ClassSymbol)]
    functions = [symbol for symbol in symbols if isinstance(symbol, FunctionSymbol)]
    edge_rows = connection.execute(
        "SELECT source_id, target_id, type, source_file_id, metadata FROM dependency_edges WHERE source_file_id = ? ORDER BY type, source_id, target_id",
        (source_file_id,),
    ).fetchall()
    edges = tuple(
        DependencyEdge(
            sourceId=row["source_id"],
            targetId=row["target_id"],
            type=row["type"],
            sourceFileId=row["source_file_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
        for row in edge_rows
    )
    module = modules[0] if modules else ModuleSymbol(
        id=f"{source_file_id}::module",
        sourceFileId=source_file_id,
        kind="module",
        name=Path(source_file.path).stem,
        lineStart=1,
        lineEnd=1,
        filePath=source_file.path,
    )
    return SourceFileBundle(
        file=source_file,
        module=module,
        classes=tuple(classes),
        functions=tuple(functions),
        dependencyEdges=edges,
    )


def load_symbol(connection: sqlite3.Connection, *, symbol_id: str) -> Symbol:
    row = connection.execute("SELECT source_file_id FROM symbols WHERE id = ?", (symbol_id,)).fetchone()
    if row is None:
        raise KeyError(symbol_id)
    source_file_id = row["source_file_id"]
    for symbol in _load_symbols(connection, source_file_id=source_file_id):
        if symbol.id == symbol_id:
            return symbol
    raise KeyError(symbol_id)


def load_symbols_for_source_file(connection: sqlite3.Connection, *, source_file_id: str) -> tuple[Symbol, ...]:
    return tuple(_load_symbols(connection, source_file_id=source_file_id))


def update_symbol_generated_summary(connection: sqlite3.Connection, *, symbol_id: str, generated_summary: str) -> None:
    with connection:
        connection.execute(
            "UPDATE symbols SET generated_summary = ? WHERE id = ?",
            (generated_summary, symbol_id),
        )


def load_symbol(connection: sqlite3.Connection, *, symbol_id: str) -> Symbol:
    row = connection.execute(
        "SELECT source_file_id FROM symbols WHERE id = ?",
        (symbol_id,),
    ).fetchone()
    if row is None:
        raise KeyError(symbol_id)
    source_file_id = row["source_file_id"]
    symbols = _load_symbols(connection, source_file_id=source_file_id)
    for symbol in symbols:
        if symbol.id == symbol_id:
            return symbol
    raise KeyError(symbol_id)


def load_symbols_for_source_file(connection: sqlite3.Connection, *, source_file_id: str) -> tuple[Symbol, ...]:
    return tuple(_load_symbols(connection, source_file_id=source_file_id))


def update_symbol_generated_summary(connection: sqlite3.Connection, *, symbol_id: str, generated_summary: str) -> None:
    with connection:
        connection.execute(
            "UPDATE symbols SET generated_summary = ? WHERE id = ?",
            (generated_summary, symbol_id),
        )


def load_repository_bundle(connection: sqlite3.Connection, *, repository_id: str) -> RepositoryBundle:
    repository = load_repository(connection, repository_id=repository_id)
    source_rows = connection.execute(
        "SELECT id FROM source_files WHERE repository_id = ? ORDER BY path",
        (repository_id,),
    ).fetchall()
    files = tuple(load_source_file_bundle(connection, source_file_id=row["id"]) for row in source_rows)
    graph_row = connection.execute(
        "SELECT id FROM dependency_graphs WHERE repository_id = ? ORDER BY id LIMIT 1",
        (repository_id,),
    ).fetchone()
    edge_rows = connection.execute(
        "SELECT source_id, target_id, type, source_file_id, metadata FROM dependency_edges WHERE graph_id = ? ORDER BY type, source_id, target_id",
        (repository_id,),
    ).fetchall()
    edges = tuple(
        DependencyEdge(
            sourceId=row["source_id"],
            targetId=row["target_id"],
            type=row["type"],
            sourceFileId=row["source_file_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
        for row in edge_rows
    )
    node_ids = tuple(
        dict.fromkeys(
            [
                *[item.file.id for item in files],
                *[item.module.id for item in files],
                *[symbol.id for item in files for symbol in (*item.classes, *item.functions)],
            ]
        )
    )
    graph = DependencyGraph(
        id=graph_row["id"] if graph_row else repository_id,
        repositoryId=repository_id,
        nodes=node_ids,
        edges=edges,
    )
    return RepositoryBundle(repository=repository, files=files, graph=graph)


def repository_root_exists(connection: sqlite3.Connection, *, root_path: str | Path) -> bool:
    row = connection.execute("SELECT 1 FROM repositories WHERE root_path = ?", (str(Path(root_path).expanduser().resolve()),)).fetchone()
    return row is not None


def get_source_file_content_hash(connection: sqlite3.Connection, *, repository_id: str, path: str | Path) -> str | None:
    row = connection.execute(
        "SELECT content_hash FROM source_files WHERE repository_id = ? AND path = ?",
        (repository_id, Path(path).as_posix().replace("\\", "/")),
    ).fetchone()
    if row is None:
        return None
    return row["content_hash"]
