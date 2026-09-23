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
from embedding_engine import EmbeddingEngine, create_embedding_engine
from doc_generator import DocGenerator, FeaturePlanner, OverviewNarrator, open_doc_manifest_store
from local_llm import LocalLLMEngine, create_local_llm_engine
from parser_engine import SourceFile, extract_symbols
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

from . import paths, progress_stream
from .availability import check_ai_dependencies
from .config import CLIConfiguration
from .errors import LocalModelUnavailableError, RepositoryNotFoundError

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
    embeddingEngine: EmbeddingEngine
    llmEngine: LocalLLMEngine
    metadataDbPath: Path
    chatLlmEngine: LocalLLMEngine
    watcher: Optional[RepositoryWatcher] = None
    dependencyGraph: Optional[DependencyGraph] = None


def _echo_summary_progress(completed: int, total: int, symbol: Symbol) -> None:
    """`CodeSummaryPipeline` already serializes this call under its own lock,
    so no lock is needed here - see `SummaryProgressCallback`."""
    typer.echo(f"  [{completed}/{total}] {symbol.kind} {symbol.name}")
    # Summarization dominates the wall clock, so this is the event spec FR-015
    # exists for: without it the bar would sit still for the majority of a run.
    progress_stream.emit(
        "items",
        stage=Stage.SUMMARIZING.name,
        completed=completed,
        total=total,
        item=f"{symbol.kind} {symbol.name}",
    )


def _echo_embedding_progress(completed: int, total: int, relative_path: str) -> None:
    typer.echo(f"  [{completed}/{total}] {relative_path}")
    progress_stream.emit(
        "items",
        stage=Stage.EMBEDDING.name,
        completed=completed,
        total=total,
        item=relative_path,
    )


# Which stage the pipeline is inside, for attributing a failure to it. A plain
# module global rather than a parameter threaded through every call: spec FR-012
# guarantees one analysis per process, so there is exactly one answer at a time,
# and the alternative would touch every function signature in this file.
_current_stage: "Stage | None" = None

# `check_ai_dependencies` names the stage whose chain refused, in its message.
# Mapping that back to the configured chain is what lets a failure say *which*
# providers were tried rather than just that something was unavailable
# (spec FR-022).
_STAGE_CHAIN_FIELDS = {
    "embeddings": "embeddingChain",
    "summary": "summaryChain",
    "chat": "chatChain",
}


def _emit_failure(stage: "Stage | None", error: BaseException, config: CLIConfiguration | None = None) -> None:
    """Report a run's cause of death on the progress channel.

    The hub does not rely on this to *detect* failure - a non-zero exit code is
    authoritative, and a child killed outright emits nothing at all
    (contracts/run-progress-stream.md, reader obligation 6). This supplies the
    diagnosis that turns "it failed" into something a person can act on.
    """
    attempted: tuple[str, ...] = getattr(error, "attempted", ()) or ()
    stage_name = getattr(error, "stage", None)
    if not attempted and config is not None:
        message = str(error)
        for chain_stage, field in _STAGE_CHAIN_FIELDS.items():
            if f"'{chain_stage}'" in message:
                attempted = tuple(getattr(config, field, ()) or ())
                stage_name = stage_name or chain_stage
                break
    progress_stream.emit(
        "failed",
        stage=stage.name if stage is not None else None,
        chain=stage_name,
        message=str(error),
        providers=list(attempted),
    )


class _stage:
    """Announce a stage, then report what it cost.

    Per-stage timings are what make an indexing regression - or an improvement
    - attributable to one stage instead of visible only in the total.

    Deliberately a class rather than a `@contextmanager` generator:
    `contextlib`'s generator wrapper assigns `exc.__traceback__` when an
    exception passes through it, and this codebase's engine errors are frozen
    dataclasses (`EmbeddingError`, `LocalLLMError`). Assigning any attribute
    on a directly-raised one raises `FrozenInstanceError`, which would replace
    a real "the model is unavailable" message with a meaningless one. A plain
    `__exit__` touches nothing on the exception.
    """

    def __init__(self, stage: "Stage") -> None:
        self._stage = stage
        self._started = 0.0

    def __enter__(self) -> "_stage":
        global _current_stage
        _current_stage = self._stage
        typer.echo(self._stage.value)
        # Alongside the echo, never instead of it (spec FR-016). This is the
        # single choke point for eight of the ten stages, which is why
        # contracts/run-progress-stream.md routes them through here rather than
        # adding an emit beside every call site.
        progress_stream.emit("stage", stage=self._stage.name, label=self._stage.value)
        self._started = time.perf_counter()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        elapsed = time.perf_counter() - self._started
        # Timed even on failure: how far a failed run got, and how long it took
        # to get there, is exactly what makes it diagnosable.
        typer.echo(f"  {self._stage.value} finished in {elapsed:.1f}s")
        progress_stream.emit("stage_end", stage=self._stage.name, elapsedSeconds=round(elapsed, 3))
        return False


def validate_repo_path(repo_path: Path) -> Path:
    typer.echo(Stage.VALIDATING.value)
    # One of the two stages announced outside `_stage` (the other is
    # CHECKING_MODELS), so it needs its own emit to keep the ten-stage list the
    # homepage draws complete (data-model.md §1).
    progress_stream.emit("stage", stage=Stage.VALIDATING.name, label=Stage.VALIDATING.value)
    resolved = Path(repo_path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise RepositoryNotFoundError(
            f"Repository path does not exist or is not a directory: {resolved}. "
            "Point the command at a local repository."
        )
    return resolved


def _build_stage_engines(
    config: CLIConfiguration, metadata_db_path: Path
) -> tuple[EmbeddingEngine, LocalLLMEngine, LocalLLMEngine]:
    """Build the engines the three stages use.

    Summary and chat get separate engine instances rather than one shared
    object even though they read the same configured model: `LocalLLMEngine`
    caches an availability verdict behind a lock, and the indexing pool and a
    chat request have no reason to contend for it.

    `metadata_db_path` is accepted and unused. It fed the failover log, which
    recorded switches between providers in a chain; with one engine per stage
    there are no switches to record. The parameter stays so the call sites
    below keep their shape and the argument remains available if per-stage
    engine telemetry is ever wanted.
    """
    embedding_engine = create_embedding_engine(
        config.embeddingModel,
        config.embeddingEndpointUrl,
        embed_timeout=config.embeddingGenerateTimeout,
    )
    summary_engine = create_local_llm_engine(
        config.llmModel, config.llmEndpointUrl, generate_timeout=config.llmGenerateTimeout
    )
    chat_engine = create_local_llm_engine(
        config.llmModel, config.llmEndpointUrl, generate_timeout=config.llmGenerateTimeout
    )
    return embedding_engine, summary_engine, chat_engine


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
    progress_stream.emit("stage", stage=Stage.CHECKING_MODELS.name, label=Stage.CHECKING_MODELS.value)
    embeddings_executor, summary_executor, chat_executor = _build_stage_engines(
        config, paths.metadata_db_path(staging_dir)
    )
    try:
        check_ai_dependencies(embeddings=embeddings_executor, summary=summary_executor, chat=chat_executor)
    except LocalModelUnavailableError as error:
        # The most common failure on a machine with no reachable provider, and
        # the one spec FR-022 most needs named: report which stage refused
        # before re-raising, so the homepage can say more than "it failed".
        _emit_failure(Stage.CHECKING_MODELS, error, config)
        raise

    try:
        _run_pipeline(
            root,
            staging_dir,
            embedding_engine=embeddings_executor,
            llm_engine=summary_executor,
            config=config,
            previous_state_dir=final_state_dir,
        )
    except Exception as error:
        # Emitted before the cleanup, while `_current_stage` still names where
        # the run died. The staging directory goes either way: a failed run
        # keeps nothing, which is exactly what spec FR-023 requires the
        # homepage to say out loud rather than leave to be inferred from a
        # column of ticked stages.
        _emit_failure(_current_stage, error, config)
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    _checkpoint_state_dir(staging_dir)

    if final_state_dir.exists():
        _rmtree_with_retry(final_state_dir)
    _replace_with_retry(staging_dir, final_state_dir)

    docs_root = paths.docs_output_dir(final_state_dir)
    embeddings_executor, summary_executor, chat_executor = _build_stage_engines(
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

    # Before the store is opened, not after: everything this seeds is read
    # during the first generation pass, and `open_doc_manifest_store` would
    # create an empty database in its place.
    _carry_forward_doc_manifest(state_dir, previous_state_dir)

    manifest_store = open_doc_manifest_store(paths.doc_manifest_db_path(state_dir))
    doc_generator = DocGenerator(
        metadataStore=metadata_store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=paths.docs_output_dir(state_dir),
        repositoryRoot=root,
        # One call for the whole feature set, not one per feature, and cached
        # in the manifest store against the repository's structure - so
        # regenerating an unchanged repository consults no model at all, and a
        # repository indexed with no provider reachable still gets the same
        # features at the same addresses, just under plainer names.
        featurePlanner=FeaturePlanner(llm_engine, cache=manifest_store),
        # The Overview's narrative: one call through the same executor, cached
        # against its exact prompt in the same manifest - carried forward with
        # it, so re-indexing an unchanged repository asks no model (038).
        overviewNarrator=OverviewNarrator(llm_engine, cache=manifest_store),
        onNotice=typer.echo,
    )

    with _stage(Stage.GENERATING_DOCS_STRUCTURE):
        # No narrative yet: summaries do not exist, and a narrative keyed on
        # summary-less evidence would be bought again on the content pass.
        doc_generator.generateRepositoryDocumentation(root, incremental=False, narrateOverview=False)

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


def _carry_forward_doc_manifest(state_dir: Path, previous_state_dir: Path | None) -> bool:
    """Seed this run's page manifest from the index it is about to replace.

    Same two rules as `_carry_forward_summary_ledger`: copied file to file
    before anything opens either side, so no connection is held on the
    directory the run will later rename over; and no failure here may fail the
    run, because a missing or unreadable prior manifest means "pay for the plan
    again", never "refuse to index".

    A full `index` always builds into an empty staging directory, so without
    this it starts with an empty manifest - and two different things are lost,
    only one of which is speed:

    - `doc_feature_plans` caches `FeaturePlanner`'s single call against the
      repository's structure. Empty, an unchanged repository pays the model
      again to name the same feature set it named last time.
    - `doc_pages` is what `_redirect_superseded_pages` reads as
      `previous_entries`. Empty, it finds nothing superseded and records no
      alias, so a feature whose anchor module moved leaves its previously
      published URL dead. That is precisely the failure the alias table exists
      to prevent, on the one code path that could never see it - the anchors
      that move are found by comparing two runs, and a full index had no
      previous run to compare against.

    The whole database is copied rather than a chosen few tables: `doc_features`
    is what makes a renamed feature detectable, and `doc_page_aliases` is the
    accumulated record of every address already published, so dropping either
    reintroduces half the defect. Rows describing pages that no longer exist are
    the ones supersession has to see; `writer.remove_page` already tolerates an
    entry whose file is gone.
    """
    if previous_state_dir is None:
        return False
    previous_db = paths.doc_manifest_db_path(previous_state_dir)
    if not previous_db.exists():
        return False
    try:
        # `_checkpoint_state_dir` folds every `-wal` back into its database
        # before the rename that publishes it, so the published file is
        # self-contained and the sidecars need no copying.
        shutil.copy2(previous_db, paths.doc_manifest_db_path(state_dir))
    except OSError:  # noqa: BLE001 - a stale prior manifest must never fail a fresh run
        return False
    typer.echo("  carried the previous index's page manifest forward")
    return True


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
