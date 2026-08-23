from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, open_doc_manifest_store
from embedding_engine import EmbeddingEngine, create_embedding_engine
from local_llm import LocalLLMEngine, create_local_llm_engine
from parser_engine import SourceFile, extract_symbols
from reindex_pipeline.embeddings import update_embeddings
from repo_scanner.scanner import scan_repository
from repo_watcher import RepositoryWatcher
from repository_metadata import CodeSummaryPipeline, RepositoryMetadataStore, Symbol, compute_content_hash
from repository_metadata.sqlite_store import stable_repository_id
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
    watcher: Optional[RepositoryWatcher] = None


def _echo_summary_progress(completed: int, total: int, symbol: Symbol) -> None:
    typer.echo(f"  [{completed}/{total}] {symbol.kind} {symbol.name}")


def validate_repo_path(repo_path: Path) -> Path:
    typer.echo(Stage.VALIDATING.value)
    resolved = Path(repo_path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise RepositoryNotFoundError(
            f"Repository path does not exist or is not a directory: {resolved}. "
            "Point the command at a local repository."
        )
    return resolved


def run_index(repo_path: Path, *, config: CLIConfiguration) -> IndexRunResult:
    """Run the full indexing pipeline for `repo_path` and return what's
    needed to start serving it.

    Builds every stage's output into a fresh staging directory and only
    replaces the repository's prior `RepositoryState` on full success, so a
    failed run never corrupts a previously-successful index (research.md
    §10, spec.md's anti-corruption requirement).
    """
    root = validate_repo_path(repo_path)

    typer.echo(Stage.CHECKING_MODELS.value)
    llm_engine = create_local_llm_engine(
        config.llmModel, config.llmEndpointUrl, generate_timeout=config.llmGenerateTimeout
    )
    embedding_engine = create_embedding_engine(
        config.embeddingModel, config.embeddingEndpointUrl, embed_timeout=config.embeddingGenerateTimeout
    )
    check_ai_dependencies(llm_engine, embedding_engine)

    final_state_dir = paths.repo_state_dir(root)
    staging_dir = final_state_dir.parent / f"{final_state_dir.name}.staging-{os.getpid()}"
    if staging_dir.exists():
        _rmtree_with_retry(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        _run_pipeline(root, staging_dir, embedding_engine=embedding_engine, llm_engine=llm_engine)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    if final_state_dir.exists():
        _rmtree_with_retry(final_state_dir)
    _replace_with_retry(staging_dir, final_state_dir)

    docs_root = paths.docs_output_dir(final_state_dir)
    vector_index = VectorIndex(
        root,
        paths.vector_metadata_db_path(final_state_dir),
        embedding_engine=embedding_engine,
    )
    return IndexRunResult(
        docsRoot=docs_root,
        vectorIndex=vector_index,
        embeddingEngine=embedding_engine,
        llmEngine=llm_engine,
        metadataDbPath=paths.metadata_db_path(final_state_dir),
    )


def _run_pipeline(root: Path, state_dir: Path, *, embedding_engine: EmbeddingEngine, llm_engine: LocalLLMEngine) -> None:
    graph_id = stable_repository_id(root)
    metadata_store = RepositoryMetadataStore(paths.metadata_db_path(state_dir))

    typer.echo(Stage.SCANNING.value)
    scan_result = scan_repository(root)

    # Ensure the repository row exists even when no source files were found
    # (spec.md's "no recognizable source files" edge case) - store_inventory
    # below only creates it as a side effect of storing at least one file.
    languages = tuple(sorted({entry.language for entry in scan_result.entries}))
    metadata_store.ensure_repository(root, detected_languages=languages)

    typer.echo(Stage.PARSING.value)
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

    typer.echo(Stage.BUILDING_GRAPH.value)
    graph = DependencyGraph.build_from_inventories(inventories, id=graph_id, sourceFile=str(root))
    graph.save(paths.graph_db_path(state_dir))

    manifest_store = open_doc_manifest_store(paths.doc_manifest_db_path(state_dir))
    doc_generator = DocGenerator(
        metadataStore=metadata_store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=paths.docs_output_dir(state_dir),
        repositoryRoot=root,
    )

    typer.echo(Stage.GENERATING_DOCS_STRUCTURE.value)
    doc_generator.generateRepositoryDocumentation(root, incremental=False)

    typer.echo(Stage.SUMMARIZING.value)
    summary_pipeline = CodeSummaryPipeline(metadataStore=metadata_store, dependencyGraph=graph, llmEngine=llm_engine)
    summary_pipeline.summarizeRepository(root, incremental=False, on_progress=_echo_summary_progress)

    typer.echo(Stage.GENERATING_DOCS_CONTENT.value)
    doc_generator.generateRepositoryDocumentation(root, incremental=False)

    typer.echo(Stage.EMBEDDING.value)
    vector_index = VectorIndex(
        root,
        paths.vector_metadata_db_path(state_dir),
        embedding_engine=embedding_engine,
    )
    try:
        for entry in scan_result.entries:
            update_embeddings(
                repository_root=root,
                relative_path=entry.relative_path,
                metadata_store=metadata_store,
                vector_index=vector_index,
                embedding_engine=embedding_engine,
            )
    finally:
        vector_index.close()
