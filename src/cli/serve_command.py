from __future__ import annotations

from pathlib import Path

import typer
from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, FeaturePlanner, open_doc_manifest_store
from reindex_pipeline import IncrementalReindexPipeline
from repo_watcher import RepositoryWatcher
from repository_metadata import CodeSummaryPipeline, RepositoryMetadataStore
from repository_metadata.sqlite_store import connect as connect_metadata_db
from repository_metadata.sqlite_store import stable_repository_id
from provider_routing import PathFailoverLog, build_stage_executor
from vector_index import VectorIndex

from . import paths
from .availability import check_ai_dependencies
from .config import CLIConfiguration
from .errors import IndexNotFoundError
from .index_command import IndexRunResult, validate_repo_path


def run_serve(repo_path: Path, *, config: CLIConfiguration) -> IndexRunResult:
    """Load an already-indexed repository's `RepositoryState`, wire the
    watcher (017) to the incremental reindexing pipeline (018), and return
    what's needed to start serving it (research.md §8).
    """
    root = validate_repo_path(repo_path)

    state_dir = paths.repo_state_dir(root)
    metadata_db_path = paths.metadata_db_path(state_dir)
    failover_log = PathFailoverLog(metadata_db_path, connect_metadata_db)
    embeddings_executor = build_stage_executor("embeddings", config, failover_log=failover_log)
    summary_executor = build_stage_executor("summary", config, failover_log=failover_log)
    chat_executor = build_stage_executor("chat", config, failover_log=failover_log)
    check_ai_dependencies(embeddings=embeddings_executor, summary=summary_executor, chat=chat_executor)

    not_indexed_message = f"No index found for {root}. Run `codepedia index {root}` first."
    if not state_dir.exists():
        raise IndexNotFoundError(not_indexed_message)

    metadata_store = RepositoryMetadataStore(metadata_db_path)
    try:
        metadata_store.load_repository_record(root)
    except KeyError as exc:
        raise IndexNotFoundError(not_indexed_message) from exc

    graph_id = stable_repository_id(root)
    graph = DependencyGraph.load(paths.graph_db_path(state_dir), graph_id=graph_id)

    docs_root = paths.docs_output_dir(state_dir)
    vector_index = VectorIndex(
        root,
        paths.vector_metadata_db_path(state_dir),
        embedding_engine=embeddings_executor,
    )
    manifest_store = open_doc_manifest_store(paths.doc_manifest_db_path(state_dir))
    doc_generator = DocGenerator(
        metadataStore=metadata_store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=docs_root,
        repositoryRoot=root,
        # One call for the whole feature set, not one per feature, and cached
        # in the manifest store against the repository's structure - so
        # regenerating an unchanged repository consults no model at all, and a
        # repository indexed with no provider reachable still gets the same
        # features at the same addresses, just under plainer names.
        featurePlanner=FeaturePlanner(summary_executor, cache=manifest_store),
    )
    summary_pipeline = CodeSummaryPipeline(
        metadataStore=metadata_store,
        dependencyGraph=graph,
        llmEngine=summary_executor,
        maxWorkers=config.summaryConcurrency,
    )

    reindex_pipeline = IncrementalReindexPipeline(
        repositoryRoot=root,
        metadataStore=metadata_store,
        dependencyGraph=graph,
        dependencyGraphPath=paths.graph_db_path(state_dir),
        summaryPipeline=summary_pipeline,
        vectorIndex=vector_index,
        embeddingEngine=embeddings_executor,
        docGenerator=doc_generator,
    )

    watcher = RepositoryWatcher(
        repository_root=root,
        on_batch=reindex_pipeline.run,
        metadata_store=metadata_store,
    )
    typer.echo("Starting repository watcher...")
    watcher.start()

    return IndexRunResult(
        docsRoot=docs_root,
        vectorIndex=vector_index,
        embeddingEngine=embeddings_executor,
        llmEngine=summary_executor,
        metadataDbPath=metadata_db_path,
        chatLlmEngine=chat_executor,
        watcher=watcher,
        dependencyGraph=graph,
    )
