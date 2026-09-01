from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from parser_engine import (
    ExtractedClassSymbol,
    ExtractedFunctionSymbol,
    ExtractedModuleSymbol,
    FileSymbolInventory,
    SourceFile,
)

from sqlite_support import apply_write_pragmas

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
    """
    CREATE TABLE IF NOT EXISTS engine_failover_log (
        id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        stage TEXT NOT NULL,
        attempted_provider TEXT NOT NULL,
        result_provider TEXT,
        reason TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS summary_ledger (
        context_hash TEXT PRIMARY KEY,
        source_file_id TEXT NOT NULL,
        symbol_kind TEXT NOT NULL,
        symbol_name TEXT NOT NULL,
        generated_summary TEXT NOT NULL,
        model_name TEXT NOT NULL,
        generated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_summary_ledger_symbol ON summary_ledger(source_file_id, symbol_kind, symbol_name, generated_at)",
    "CREATE INDEX IF NOT EXISTS idx_source_files_repository_path ON source_files(repository_id, path)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_source_file ON symbols(source_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_dependency_edges_source_file ON dependency_edges(source_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_dependency_edges_target_id ON dependency_edges(target_id)",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_timestamp ON chat_messages(session_id, timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_engine_failover_log_timestamp ON engine_failover_log(timestamp)",
)


# Every call into this store opens its own connection and replays
# `ensure_schema` (DDL, so it takes the write lock). Once summarization runs
# from a thread pool, several of those overlap on the same file, and sqlite's
# 5s default is thin for a burst of writers. Raising the busy timeout makes a
# contending writer wait its turn instead of raising "database is locked".
#
# WAL *is* enabled now, by `apply_write_pragmas` below, and the busy timeout
# still matters under it: WAL lets readers and one writer run concurrently, but
# two writers still serialize. What used to rule WAL out was that it leaves
# `-wal`/`-shm` files beside the database while `cli/index_command.py` renames
# the whole state directory into place on Windows. `_checkpoint_state_dir`
# there is the answer to that: the run checkpoints and closes every database
# before the rename, so no side file survives it.
_BUSY_TIMEOUT_MS = 30000


def connect(db_path: str | Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open the metadata database, schema ensured.

    `check_same_thread=False` is for `RepositoryMetadataStore.session`, which
    hands one connection to a whole summarization pass: the pool's workers all
    write through it, serialized by the store's own lock. Same trade the vector
    index already makes for the same reason (`vector_index/storage.connect`).
    """
    connection = sqlite3.connect(str(db_path), check_same_thread=check_same_thread)
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    apply_write_pragmas(connection)
    ensure_schema(connection)
    return connection


#: Bumped whenever `parser_engine.extractor` changes how a symbol id is
#: derived. Version 2 is the line-free scheme: an id is seeded on the file, the
#: kind, the qualified name and an ordinal, never on `lineStart`/`lineEnd`.
SYMBOL_ID_SCHEME_VERSION = 2


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    for statement in SCHEMA_STATEMENTS:
        connection.execute(statement)
    _ensure_chat_messages_generated_by_column(connection)
    _ensure_repositories_commit_sha_column(connection)
    _ensure_symbols_summary_provenance_columns(connection)
    _ensure_symbol_id_scheme(connection)


def _ensure_symbol_id_scheme(connection: sqlite3.Connection) -> None:
    """Re-parse every file once when the id derivation itself has changed.

    An index written by an older version holds symbols keyed the old way. The
    incremental path only re-parses files whose content hash moved, so without
    this a long-lived `serve` would keep both schemes side by side forever,
    each file switching over only if someone happened to edit it.

    Blanking `content_hash` is the lever the watcher already has: its catch-up
    scan compares the stored hash with the file's, so an empty one reads as
    "modified" and the file is re-parsed on the next pass. Nothing is deleted -
    a re-parse rewrites the symbols, and the summary ledger is keyed on content
    rather than on symbol identity, so the summaries come straight back with no
    model call (`copy_summary_ledger`).

    A database created just now reports version 0 with no rows to update, so
    this only ever stamps it.
    """
    stored = connection.execute("PRAGMA user_version").fetchone()[0]
    if stored == SYMBOL_ID_SCHEME_VERSION:
        return
    with connection:
        connection.execute("UPDATE source_files SET content_hash = ''")
        # `PRAGMA user_version` takes no parameter binding.
        connection.execute(f"PRAGMA user_version = {SYMBOL_ID_SCHEME_VERSION:d}")


def _ensure_symbols_summary_provenance_columns(connection: sqlite3.Connection) -> None:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(symbols)").fetchall()}
    with connection:
        if "summary_context_hash" not in columns:
            connection.execute("ALTER TABLE symbols ADD COLUMN summary_context_hash TEXT NOT NULL DEFAULT ''")
        if "summary_is_stale" not in columns:
            connection.execute("ALTER TABLE symbols ADD COLUMN summary_is_stale INTEGER NOT NULL DEFAULT 0")


def _ensure_repositories_commit_sha_column(connection: sqlite3.Connection) -> None:
    # Same introspection-guarded shape as the migration below; a database
    # written before provenance existed simply reports "" for every repository.
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(repositories)").fetchall()}
    if "commit_sha" not in columns:
        with connection:
            connection.execute("ALTER TABLE repositories ADD COLUMN commit_sha TEXT NOT NULL DEFAULT ''")


def _ensure_chat_messages_generated_by_column(connection: sqlite3.Connection) -> None:
    # ALTER TABLE ADD COLUMN has no IF NOT EXISTS equivalent - guarded
    # separately so re-running against an already-migrated database doesn't
    # raise sqlite3.OperationalError (contracts/sqlite-schema-deltas.md).
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(chat_messages)").fetchall()}
    if "generated_by" not in columns:
        with connection:
            connection.execute("ALTER TABLE chat_messages ADD COLUMN generated_by TEXT NOT NULL DEFAULT ''")


def stable_repository_id(root_path: str | Path) -> str:
    normalized = Path(root_path).expanduser().resolve().as_posix()
    return f"repo::{normalized}"


def stable_source_file_id(repository_id: str, path: str | Path) -> str:
    normalized = Path(path).as_posix().replace("\\", "/")
    return f"{repository_id}::file::{normalized}"


def upsert_repository(
    connection: sqlite3.Connection,
    *,
    root_path: str | Path,
    detected_languages: Iterable[str],
    last_indexed_at: str,
    commit_sha: str | None = None,
) -> Repository:
    """`commit_sha=None` means "leave whatever is stored alone".

    This runs once per stored file, but HEAD is only read once per indexing run
    (`RepositoryMetadataStore.ensure_repository`), so every later call in the
    run must not blank the column it did not look up.
    """
    repository_id = stable_repository_id(root_path)
    stored_commit_sha = commit_sha
    if stored_commit_sha is None:
        row = connection.execute("SELECT commit_sha FROM repositories WHERE id = ?", (repository_id,)).fetchone()
        stored_commit_sha = row["commit_sha"] if row is not None else ""
    repository = Repository(
        id=repository_id,
        rootPath=str(Path(root_path).expanduser().resolve()),
        detectedLanguages=tuple(sorted({language for language in detected_languages})),
        lastIndexedAt=last_indexed_at,
        commitSha=stored_commit_sha,
    )
    with connection:
        connection.execute(
            """
            INSERT INTO repositories (id, root_path, detected_languages, last_indexed_at, commit_sha)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                root_path = excluded.root_path,
                detected_languages = excluded.detected_languages,
                last_indexed_at = excluded.last_indexed_at,
                commit_sha = excluded.commit_sha
            """,
            (
                repository.id,
                repository.rootPath,
                json.dumps(repository.detectedLanguages),
                repository.lastIndexedAt,
                repository.commitSha,
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


def update_repository_commit_sha(connection: sqlite3.Connection, *, repository_id: str, commit_sha: str) -> None:
    """Move the recorded HEAD without touching anything else about the row.

    Deliberately not `upsert_repository(commit_sha=...)`: that call writes
    `detected_languages` from its argument, so a caller who only knows the new
    sha would blank the language list on its way past.
    """
    with connection:
        connection.execute(
            "UPDATE repositories SET commit_sha = ? WHERE id = ?",
            (commit_sha, repository_id),
        )


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
    row = connection.execute(
        "SELECT id, root_path, detected_languages, last_indexed_at, commit_sha FROM repositories WHERE id = ?",
        (repository_id,),
    ).fetchone()
    if row is None:
        raise KeyError(repository_id)
    return Repository(
        id=row["id"],
        rootPath=row["root_path"],
        detectedLanguages=tuple(json.loads(row["detected_languages"])),
        lastIndexedAt=row["last_indexed_at"],
        commitSha=row["commit_sha"],
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
        "SELECT id, kind, name, line_start, line_end, docstring, generated_summary, metadata, "
        "summary_context_hash, summary_is_stale FROM symbols WHERE source_file_id = ? "
        "ORDER BY line_start, line_end, name",
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
                    summaryContextHash=row["summary_context_hash"],
                    summaryIsStale=bool(row["summary_is_stale"]),
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
                    summaryContextHash=row["summary_context_hash"],
                    summaryIsStale=bool(row["summary_is_stale"]),
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
                    summaryContextHash=row["summary_context_hash"],
                    summaryIsStale=bool(row["summary_is_stale"]),
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


def update_symbol_summary_provenance(
    connection: sqlite3.Connection,
    *,
    symbol_id: str,
    generated_summary: str,
    context_hash: str,
    is_stale: bool,
) -> None:
    """Write a summary together with the material it was generated from."""
    with connection:
        connection.execute(
            "UPDATE symbols SET generated_summary = ?, summary_context_hash = ?, summary_is_stale = ? WHERE id = ?",
            (generated_summary, context_hash, 1 if is_stale else 0, symbol_id),
        )


def save_summary_to_ledger(
    connection: sqlite3.Connection,
    *,
    context_hash: str,
    source_file_id: str,
    symbol_kind: str,
    symbol_name: str,
    generated_summary: str,
    model_name: str,
    generated_at: str,
) -> None:
    """Record what a model said about one exact version of one symbol.

    Keyed by `context_hash` - the hash of the material the model was shown -
    rather than by symbol id, and deliberately carrying no foreign key to
    `symbols`. Both choices exist for the same reason: re-parsing a file
    deletes and re-inserts every symbol in it, so anything keyed on symbol
    identity (or cascading from it) would be destroyed by an edit to an
    unrelated part of the same file. Content is what the summary actually
    describes, and content is what survives.
    """
    with connection:
        connection.execute(
            """
            INSERT INTO summary_ledger
                (context_hash, source_file_id, symbol_kind, symbol_name, generated_summary, model_name, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(context_hash) DO UPDATE SET
                source_file_id = excluded.source_file_id,
                symbol_kind = excluded.symbol_kind,
                symbol_name = excluded.symbol_name,
                generated_summary = excluded.generated_summary,
                model_name = excluded.model_name,
                generated_at = excluded.generated_at
            """,
            (context_hash, source_file_id, symbol_kind, symbol_name, generated_summary, model_name, generated_at),
        )


def copy_summary_ledger(connection: sqlite3.Connection, *, source_db_path: str | Path) -> int:
    """Carry a previous run's ledger into this run's database. Returns rows copied.

    A full `index` builds into a fresh staging directory, so its metadata
    database starts empty - and an empty ledger means every symbol in the
    repository is re-summarized at the model, however unchanged the code is.
    `cli.index_command._warm_embedding_cache` already carries the previous
    run's *vectors* forward for exactly this reason; this is the same move for
    the answers that cost far more per call.

    `ATTACH` rather than a read-and-reinsert loop: the ledger holds one row per
    summary ever generated for the repository, and the whole point is that this
    is cheap enough to do unconditionally.

    Rows are matched on `context_hash`, which is what the ledger is keyed on and
    what makes this safe across a change of symbol ids: the hash covers the
    material the model was shown and deliberately not the symbol's id
    (`summary_context.context_hash`).
    """
    connection.execute("ATTACH DATABASE ? AS previous_state", (str(source_db_path),))
    try:
        with connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO summary_ledger
                    (context_hash, source_file_id, symbol_kind, symbol_name, generated_summary, model_name, generated_at)
                SELECT context_hash, source_file_id, symbol_kind, symbol_name, generated_summary, model_name, generated_at
                FROM previous_state.summary_ledger
                """
            )
            return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
    finally:
        connection.execute("DETACH DATABASE previous_state")


def load_summary_by_context_hash(connection: sqlite3.Connection, *, context_hash: str) -> str:
    """A summary already generated for exactly this content, or "".

    A hit means the model would be shown material it has already summarized, so
    the call can be skipped outright.
    """
    if not context_hash:
        return ""
    row = connection.execute(
        "SELECT generated_summary FROM summary_ledger WHERE context_hash = ?",
        (context_hash,),
    ).fetchone()
    return row["generated_summary"] if row is not None else ""


def load_latest_summary_for_symbol(
    connection: sqlite3.Connection, *, source_file_id: str, symbol_kind: str, symbol_name: str
) -> tuple[str, str]:
    """The most recent summary written for this symbol, whatever version it described.

    Returns `(generated_summary, context_hash)`, or `("", "")`. Matched on
    file/kind/name rather than symbol id: a re-parse deletes and re-inserts
    every symbol in the file, and an id can still move on a rename or when an
    earlier homonym appears above it. Used only to carry a *stale* summary
    forward when the current version of a symbol has none of its own.
    """
    row = connection.execute(
        """
        SELECT generated_summary, context_hash FROM summary_ledger
        WHERE source_file_id = ? AND symbol_kind = ? AND symbol_name = ?
        ORDER BY generated_at DESC LIMIT 1
        """,
        (source_file_id, symbol_kind, symbol_name),
    ).fetchone()
    return (row["generated_summary"], row["context_hash"]) if row is not None else ("", "")


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
