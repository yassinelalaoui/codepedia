from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import typer
from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, SectionNarrator, open_doc_manifest_store
from parser_engine import SourceFile, extract_symbols
from provider_routing import FailoverExecutor, PathFailoverLog, build_stage_executor
from reindex_pipeline import EmbeddingCache
from reindex_pipeline.embeddings import update_embeddings
from repo_scanner.docs_scope import load_docs_scope
from repo_scanner.scanner import scan_repository
from repo_watcher import RepositoryWatcher
from repository_metadata import CodeSummaryPipeline, RepositoryMetadataStore, Symbol, compute_content_hash
from repository_metadata.sqlite_store import connect as connect_metadata_db
from repository_metadata.sqlite_store import copy_summary_ledger, stable_repository_id
from sqlite_support import checkpoint_and_close
from vector_index import VectorIndex

from . import paths
from .availability import check_ai_dependencies
from .config import CLIConfiguration
from .errors import RepositoryNotFoundError

# A directory just closed by sqlite/other local I/O can briefly stay locked
# on Windows (e.g. antivirus/indexer scanning it right after it's written),
# even though nothing in this process still holds it open. Retrying the
# filesystem swap with a short backoff is the standard mitigation.
_FS_RETRY_DELAYS = (0.1, 0.2, 0.4, 0.8, 1.6)


def _rmtree_with_retry(path: Path) -> None:
    for delay in (*_FS_RETRY_DELAYS, None):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            if delay is None:
                raise
            time.sleep(delay)


def _checkpoint_state_dir(state_dir: Path) -> None:
    """Fold every `-wal` in `state_dir` back into its database before the rename.

    The databases run in WAL (`sqlite_support.apply_write_pragmas`), which is
    what makes a commit stop costing an fsync - but WAL keeps a `-wal` and a
    `-shm` file beside each database, and this directory is about to be renamed
    into place on Windows. That rename is the reason WAL was refused here
    before (`repository_metadata/sqlite_store.py`).

    Measured, this is belt and braces as the pipeline stands: every store closes
    its connection per call and `vector_index.close()` runs in a `finally`, so
    sqlite has already deleted both side files by the time control reaches here
    - the accompanying test passes with this function stubbed out. It stays
    because the guarantee the rename needs should be asserted at the rename
    rather than inferred from the closing habits of four separate stores: the
    first long-lived connection anyone adds to the run would otherwise turn a
    working publish into an intermittent Windows failure.

    Anything unreadable is skipped - a database this run never created is not a
    reason to fail a run that otherwise succeeded.
    """
    for db_path in sorted(state_dir.rglob("*.sqlite")):
        try:
            checkpoint_and_close(sqlite3.connect(str(db_path)))
        except sqlite3.Error:
            continue


def _replace_with_retry(source: Path, target: Path) -> None:
    for delay in (*_FS_RETRY_DELAYS, None):
        try:
            source.replace(target)
            return
        except OSError:
            if delay is None:
                raise
            time.sleep(delay)


class Stage(str, Enum):
    """One `index` pipeline stage, printed as it starts (data-model.md's
    `PipelineRun.stage`). Order matches research.md §6: two documentation
    passes (structure, then content) surrounding summarization, with
    embedding last."""

    VALIDATING = "Validating repository"
    CHECKING_MODELS = "Checking local model availability"
    SCANNING = "Scanning repository"
    PARSING = "Parsing and extracting symbols"
    BUILDING_GRAPH = "Building dependency graph"
    GENERATING_DOCS_STRUCTURE = "Generating documentation structure"
    SUMMARIZING = "Generating summaries"
    GENERATING_DOCS_CONTENT = "Generating documentation content"
    EMBEDDING = "Updating embeddings"
    STARTING_SERVER = "Starting local server"


@dataclass(slots=True)
class IndexRunResult:
    """Bundle `run_index`/`run_serve` return to their Typer command caller
    (data-model.md's `IndexRunResult`), so it can start the local server
    without knowing the pipeline's internal construction order."""

    docsRoot: Path
    vectorIndex: VectorIndex
    embeddingEngine: FailoverExecutor
    llmEngine: FailoverExecutor
    metadataDbPath: Path
    chatLlmEngine: FailoverExecutor
    watcher: Optional[RepositoryWatcher] = None
    dependencyGraph: Optional[DependencyGraph] = None


def _echo_summary_progress(completed: int, total: int, symbol: Symbol) -> None:
    """`CodeSummaryPipeline` already serializes this call under its own lock,
    so no lock is needed here - see `SummaryProgressCallback`."""
    typer.echo(f"  [{completed}/{total}] {symbol.kind} {symbol.name}")


def _echo_embedding_progress(completed: int, total: int, relative_path: str) -> None:
    typer.echo(f"  [{completed}/{total}] {relative_path}")


def _echo_backoff(*, stage: str, provider: str, delay_seconds: float, wait_number: int, max_waits: int) -> None:
    """Print a rate-limit wait as it happens.

    A wait is deliberately absent from `engine_failover_log`, which records
    provider *switches* (constitution 2.3) - waiting on the same provider is
    the opposite of switching. It still has to be visible, or a run that slows
    down under a rate limit looks like a run that has simply hung.
    """
    typer.echo(
        f"  rate limited by {provider} ({stage}); waiting {delay_seconds:.1f}s "
        f"before retry {wait_number}/{max_waits}"
    )


class _stage:
    """Announce a stage, then report what it cost.

    Per-stage timings are what make an indexing regression - or an improvement
    - attributable to one stage instead of visible only in the total.

    Deliberately a class rather than a `@contextmanager` generator:
    `contextlib`'s generator wrapper assigns `exc.__traceback__` when an
    exception passes through it, and this codebase's engine errors are frozen
    dataclasses (`FailoverExhaustedError`, `EmbeddingError`, `LocalLLMError`).
    Assigning any attribute on a directly-raised one raises
    `FrozenInstanceError`, which would replace a real "every provider is
    unavailable" message with a meaningless one. A plain `__exit__` touches
    nothing on the exception.
    """

    def __init__(self, stage: "Stage") -> None:
        self._stage = stage
        self._started = 0.0

    def __enter__(self) -> "_stage":
        typer.echo(self._stage.value)
        self._started = time.perf_counter()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        elapsed = time.perf_counter() - self._started
        # Timed even on failure: how far a failed run got, and how long it took
        # to get there, is exactly what makes it diagnosable.
        typer.echo(f"  {self._stage.value} finished in {elapsed:.1f}s")
        return False


def validate_repo_path(repo_path: Path) -> Path:
    typer.echo(Stage.VALIDATING.value)
    resolved = Path(repo_path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise RepositoryNotFoundError(
            f"Repository path does not exist or is not a directory: {resolved}. "
            "Point the command at a local repository."
        )
    return resolved


def _build_stage_executors(
    config: CLIConfiguration, metadata_db_path: Path
) -> tuple[FailoverExecutor, FailoverExecutor, FailoverExecutor]:
    """Build the three per-stage `FailoverExecutor`s from `config`'s chains
    (provider_routing.factory), each logging its own actual switches to the
    repository's `engine_failover_log` table (T017/T018). Uses
    `PathFailoverLog` (connects fresh per event, never holds the metadata db
    open) rather than one long-lived connection, so nothing here can block a
    later rename/replace of that file on Windows."""
    failover_log = PathFailoverLog(metadata_db_path, connect_metadata_db)
    # The two indexing stages announce their rate-limit waits; chat does not,
    # because `FailoverExecutor.stream` - the only path chat uses - carries no
    # backoff and would never call it.
    embeddings_executor = build_stage_executor(
        "embeddings", config, failover_log=failover_log, on_backoff=_echo_backoff
    )
    summary_executor = build_stage_executor("summary", config, failover_log=failover_log, on_backoff=_echo_backoff)
    chat_executor = build_stage_executor("chat", config, failover_log=failover_log)
    return embeddings_executor, summary_executor, chat_executor


def run_index(repo_path: Path, *, config: CLIConfiguration) -> IndexRunResult:
    """Run the full indexing pipeline for `repo_path` and return what's
    needed to start serving it.

    Builds every stage's output into a fresh staging directory and only
    replaces the repository's prior `RepositoryState` on full success, so a
    failed run never corrupts a previously-successful index (research.md
    §10, spec.md's anti-corruption requirement).
    """
    root = validate_repo_path(repo_path)
    # Before the staging directory, the provider checks and the first parse: a
    # typo in `.codepedia.json` is the user's, not the pipeline's, and it should
    # read as one rather than as a traceback out of the scanner ten stages in.
    try:
        load_docs_scope(root)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    final_state_dir = paths.repo_state_dir(root)
    staging_dir = final_state_dir.parent / f"{final_state_dir.name}.staging-{os.getpid()}"
    if staging_dir.exists():
        _rmtree_with_retry(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(Stage.CHECKING_MODELS.value)
    embeddings_executor, summary_executor, chat_executor = _build_stage_executors(
        config, paths.metadata_db_path(staging_dir)
    )
    check_ai_dependencies(embeddings=embeddings_executor, summary=summary_executor, chat=chat_executor)

    try:
        _run_pipeline(
            root,
            staging_dir,
            embedding_engine=embeddings_executor,
            llm_engine=summary_executor,
            config=config,
            previous_state_dir=final_state_dir,
        )
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    _checkpoint_state_dir(staging_dir)

    if final_state_dir.exists():
        _rmtree_with_retry(final_state_dir)
    _replace_with_retry(staging_dir, final_state_dir)

    docs_root = paths.docs_output_dir(final_state_dir)
    embeddings_executor, summary_executor, chat_executor = _build_stage_executors(
        config, paths.metadata_db_path(final_state_dir)
    )
    vector_index = VectorIndex(
        root,
        paths.vector_metadata_db_path(final_state_dir),
        embedding_engine=embeddings_executor,
    )
    # Reloaded from the snapshot _run_pipeline just wrote: the chat path uses it
    # to rerank retrieved evidence by proximity to symbols already cited.
    dependency_graph = DependencyGraph.load(
        paths.graph_db_path(final_state_dir), graph_id=stable_repository_id(root)
    )
    return IndexRunResult(
        docsRoot=docs_root,
        vectorIndex=vector_index,
        embeddingEngine=embeddings_executor,
        llmEngine=summary_executor,
        metadataDbPath=paths.metadata_db_path(final_state_dir),
        chatLlmEngine=chat_executor,
        dependencyGraph=dependency_graph,
    )


def _run_pipeline(
    root: Path,
    state_dir: Path,
    *,
    embedding_engine: Any,
    llm_engine: Any,
    config: CLIConfiguration,
    previous_state_dir: Path | None = None,
) -> None:
    """`previous_state_dir` is the state this run will replace on success.

    It is read, never written: its vectors warm this run's embedding cache.
    Without it the cache would be useless on a full `index`, which always
    builds into an empty staging directory.
    """
    graph_id = stable_repository_id(root)
    metadata_store = RepositoryMetadataStore(paths.metadata_db_path(state_dir))

    with _stage(Stage.SCANNING):
        scan_result = scan_repository(root)

    # Ensure the repository row exists even when no source files were found
    # (spec.md's "no recognizable source files" edge case) - store_inventory
    # below only creates it as a side effect of storing at least one file.
    languages = tuple(sorted({entry.language for entry in scan_result.entries}))
    metadata_store.ensure_repository(root, detected_languages=languages)

    with _stage(Stage.PARSING):
        inventories = []
        for entry in scan_result.entries:
            absolute_path = root / entry.relative_path
            source_file = SourceFile(path=absolute_path, language=entry.language)
            inventory = extract_symbols(source_file)
            metadata_store.store_inventory(
                repository_root=root,
                source_file=source_file,
                inventory=inventory,
                content_hash=compute_content_hash(absolute_path),
            )
            inventories.append(inventory)

    with _stage(Stage.BUILDING_GRAPH):
        graph = DependencyGraph.build_from_inventories(inventories, id=graph_id, sourceFile=str(root))
        graph.save(paths.graph_db_path(state_dir))

    manifest_store = open_doc_manifest_store(paths.doc_manifest_db_path(state_dir))
    doc_generator = DocGenerator(
        metadataStore=metadata_store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=paths.docs_output_dir(state_dir),
        repositoryRoot=root,
        # One call per section, not per page, and cached in the manifest store
        # against the section's membership - so an unchanged section is never
        # narrated twice, and a repository indexed with no provider reachable
        # still gets its sections, just under their directory-derived names.
        sectionNarrator=SectionNarrator(llm_engine, cache=manifest_store),
    )

    with _stage(Stage.GENERATING_DOCS_STRUCTURE):
        doc_generator.generateRepositoryDocumentation(root, incremental=False)

    _carry_forward_summary_ledger(state_dir, previous_state_dir)

    with _stage(Stage.SUMMARIZING):
        summary_pipeline = CodeSummaryPipeline(
            metadataStore=metadata_store,
            dependencyGraph=graph,
            llmEngine=llm_engine,
            maxWorkers=config.summaryConcurrency,
        )
        summary_pipeline.summarizeRepository(root, incremental=False, on_progress=_echo_summary_progress)

    with _stage(Stage.GENERATING_DOCS_CONTENT):
        doc_generator.generateRepositoryDocumentation(root, incremental=False)

    with _stage(Stage.EMBEDDING):
        vector_index = VectorIndex(
            root,
            paths.vector_metadata_db_path(state_dir),
            embedding_engine=embedding_engine,
        )
        try:
            cache = _warm_embedding_cache(root, previous_state_dir)
            _embed_files_concurrently(
                root,
                [entry.relative_path for entry in scan_result.entries],
                metadata_store=metadata_store,
                vector_index=vector_index,
                embedding_engine=embedding_engine,
                embedding_cache=cache,
                max_workers=config.embeddingConcurrency,
            )
            if cache.hits:
                typer.echo(f"  reused {cache.hits} embedding(s) from cache, computed {cache.misses}")
        finally:
            vector_index.close()


def _carry_forward_summary_ledger(state_dir: Path, previous_state_dir: Path | None) -> int:
    """Bring the previous run's summaries into this staging database.

    Same shape and same two rules as `_warm_embedding_cache` below: opened and
    closed immediately, because the state directory this reads is the one about
    to be replaced and a held connection blocks that replace on Windows; and no
    failure here is allowed to fail the run, because a stale or missing prior
    state means "pay for the summaries again", never "refuse to index".

    Without this a full `index` re-summarizes the entire repository at the
    model even when nothing changed, which is what made a reindex expensive
    enough to be worth avoiding.
    """
    if previous_state_dir is None:
        return 0
    previous_db = paths.metadata_db_path(previous_state_dir)
    if not previous_db.exists():
        return 0
    connection = connect_metadata_db(paths.metadata_db_path(state_dir))
    try:
        copied = copy_summary_ledger(connection, source_db_path=previous_db)
    except Exception:  # noqa: BLE001 - a stale prior ledger must never fail a fresh run
        return 0
    finally:
        checkpoint_and_close(connection)
    if copied:
        typer.echo(f"  carried {copied} summary(ies) forward from the previous index")
    return copied


def _warm_embedding_cache(root: Path, previous_state_dir: Path | None) -> EmbeddingCache:
    """Preload the vectors the previous successful index already paid for.

    Opened and closed immediately: this is the state directory the run is
    about to replace, and leaving a connection on it would block that replace
    on Windows.
    """
    cache = EmbeddingCache()
    if previous_state_dir is None:
        return cache
    previous_db = paths.vector_metadata_db_path(previous_state_dir)
    if not previous_db.exists():
        return cache
    try:
        previous_index = VectorIndex(root, previous_db)
    except Exception:  # noqa: BLE001 - a stale prior index must never fail a fresh run
        return cache
    try:
        cache.seed_from_index(previous_index)
    finally:
        previous_index.close()
    return cache


def _embed_files_concurrently(
    root: Path,
    relative_paths: list[str],
    *,
    metadata_store: RepositoryMetadataStore,
    vector_index: VectorIndex,
    embedding_engine: Any,
    embedding_cache: EmbeddingCache,
    max_workers: int,
) -> None:
    """Embed every file in parallel; each file is an independent unit of work.

    `update_embeddings` reads one file's symbols and replaces exactly that
    file's chunks, so two files never contend for the same rows.
    `VectorIndex` serializes the writes behind its own reentrant lock and
    holds its connection with `check_same_thread=False`, so nothing there
    needs to change for this.
    """
    total = len(relative_paths)
    if not total:
        return
    progress_lock = threading.Lock()
    completed = 0

    def embed_one(relative_path: str) -> None:
        nonlocal completed
        update_embeddings(
            repository_root=root,
            relative_path=relative_path,
            metadata_store=metadata_store,
            vector_index=vector_index,
            embedding_engine=embedding_engine,
            embedding_cache=embedding_cache,
        )
        # Counter and echo under one lock, or two workers interleave into a
        # "[7/9]" printed before "[6/9]".
        with progress_lock:
            completed += 1
            _echo_embedding_progress(completed, total, relative_path)

    executor = ThreadPoolExecutor(max_workers=min(max_workers, total), thread_name_prefix="codepedia-embed")
    try:
        futures: list[Future[None]] = [executor.submit(embed_one, path) for path in relative_paths]
        for future in futures:
            # The first failure propagates and aborts the run, exactly as it
            # did when this was a plain loop; the staging directory is then
            # discarded whole by run_index.
            future.result()
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
