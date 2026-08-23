from __future__ import annotations

from pathlib import Path

import typer
from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, open_doc_manifest_store
from embedding_engine import create_embedding_engine
from local_llm import create_local_llm_engine
from reindex_pipeline import IncrementalReindexPipeline
from repo_watcher import RepositoryWatcher
from repository_metadata import CodeSummaryPipeline, RepositoryMetadataStore
from repository_metadata.sqlite_store import stable_repository_id
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

    llm_engine = create_local_llm_engine(
        config.llmModel, config.llmEndpointUrl, generate_timeout=config.llmGenerateTimeout
    )
    embedding_engine = create_embedding_engine(
        config.embeddingModel, config.embeddingEndpointUrl, embed_timeout=config.embeddingGenerateTimeout
    )
    check_ai_dependencies(llm_engine, embedding_engine)

    state_dir = paths.repo_state_dir(root)
    not_indexed_message = f"No index found for {root}. Run `repo-scanner index {root}` first."
    if not state_dir.exists():
        raise IndexNotFoundError(not_indexed_message)

    metadata_store = RepositoryMetadataStore(paths.metadata_db_path(state_dir))
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
        embedding_engine=embedding_engine,
    )
    manifest_store = open_doc_manifest_store(paths.doc_manifest_db_path(state_dir))
    doc_generator = DocGenerator(
        metadataStore=metadata_store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=docs_root,
        repositoryRoot=root,
    )
    summary_pipeline = CodeSummaryPipeline(metadataStore=metadata_store, dependencyGraph=graph, llmEngine=llm_engine)

    reindex_pipeline = IncrementalReindexPipeline(
        repositoryRoot=root,
        metadataStore=metadata_store,
        dependencyGraph=graph,
        dependencyGraphPath=paths.graph_db_path(state_dir),
        summaryPipeline=summary_pipeline,
        vectorIndex=vector_index,
        embeddingEngine=embedding_engine,
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
        embeddingEngine=embedding_engine,
        llmEngine=llm_engine,
        metadataDbPath=paths.metadata_db_path(state_dir),
        watcher=watcher,
    )
