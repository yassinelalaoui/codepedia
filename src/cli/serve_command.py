from __future__ import annotations

from pathlib import Path

import typer
from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, FeaturePlanner, OverviewNarrator, open_doc_manifest_store
from reindex_pipeline import IncrementalReindexPipeline
from repo_watcher import RepositoryWatcher
from repository_metadata import CodeSummaryPipeline, RepositoryMetadataStore
from repository_metadata.sqlite_store import stable_repository_id
from vector_index import VectorIndex

from . import paths, progress_stream
from .availability import check_ai_dependencies
from .config import CLIConfiguration
from .errors import IndexNotFoundError
from .index_command import IndexRunResult, Stage, _build_stage_engines, validate_repo_path


def _emit_catchup_progress(phase: str, completed: int, total: int, relative_path: str) -> None:
    """Surface the previously-invisible catch-up re-index (research.md §3)."""
    progress_stream.emit(
        "catchup",
        phase=phase,
        completed=completed,
        total=total,
        path=relative_path,
    )


def _refresh_wiki_shell(doc_generator: DocGenerator, root: Path) -> None:
    """Bring an already-generated wiki up to date with this build, before serving it.

    A generated wiki is a snapshot, not a live view: its HTML came from the
    Jinja templates as they stood the day it was written, and its
    `assets/wiki-ui.js` is a copy of the bundle from that same day. Nothing
    refreshed either afterwards. The watcher only runs when a *source file*
    changes, so a repository whose code has not moved since it was analysed was
    served from its original shell forever - with no way for a reader to tell,
    and no way to reach anything the shell gained since.

    That produced two symptoms with one cause: a wiki whose sidebar predates the
    homepage has no link back to it, and a wiki carrying an older bundle is
    missing every improvement made to the wiki UI since.

    The pass itself is cheap when nothing moved. `template_fingerprint` is a
    hash comparison, and `ensure_wiki_ui_assets` compares bytes before writing,
    so an up-to-date wiki costs a few reads and rewrites nothing. When the
    templates *have* moved the generator rebuilds every page rather than leaving
    half the wiki on the old shell, which is what its fingerprint check exists
    for.

    Crucially it needs no provider: summaries are read from the metadata store,
    and the feature plan and the Overview's narrative are cached in the
    manifest, so this still works on a machine where no chain is reachable. The
    one call it can spend is the narrative's, and only when the repository
    changed since the narrative was written; with no chain reachable it shows
    the earlier narrative, marked as such, instead (038 FR-017a).
    """
    # Reuses the pipeline's own stage name, so a hub-launched serve lights up a
    # stage the homepage already knows how to draw instead of needing a new
    # event type (contracts/run-progress-stream.md).
    progress_stream.emit(
        "stage",
        stage=Stage.GENERATING_DOCS_CONTENT.name,
        label=Stage.GENERATING_DOCS_CONTENT.value,
    )
    refreshed = doc_generator.generateRepositoryDocumentation(root, incremental=True)
    progress_stream.emit("stage_end", stage=Stage.GENERATING_DOCS_CONTENT.name, elapsedSeconds=0.0)

    # Silent when there was nothing to do, which is the common case - a person
    # running `codepedia serve` on an up-to-date wiki sees exactly what they saw
    # before.
    if refreshed.pages:
        typer.echo(f"Rebuilt {len(refreshed.pages)} wiki page(s) for this version of the templates.")


def run_serve(repo_path: Path, *, config: CLIConfiguration) -> IndexRunResult:
    """Load an already-indexed repository's `RepositoryState`, wire the
    watcher (017) to the incremental reindexing pipeline (018), and return
    what's needed to start serving it (research.md §8).
    """
    root = validate_repo_path(repo_path)

    state_dir = paths.repo_state_dir(root)
    metadata_db_path = paths.metadata_db_path(state_dir)
    embeddings_executor, summary_executor, chat_executor = _build_stage_engines(config, metadata_db_path)
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
        # Same executor, same cache as `index`: an unchanged repository
        # renders the Overview it was indexed with, whether or not a provider
        # is reachable now (038 FR-016).
        overviewNarrator=OverviewNarrator(summary_executor, cache=manifest_store),
        onNotice=typer.echo,
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

    def _run_batch(batch) -> None:  # noqa: ANN001 - ChangeBatch, matching on_batch's signature
        """Run a change batch, reporting per-file progress on the hub channel.

        `watcher.start()` runs `compute_catchup_batch` synchronously *before*
        `start_local_server` prints the URL (`repo_watcher/watcher.py:51-53`),
        so a hub-launched `serve` reports everything it is bringing up to date
        and only then hands over the address. That ordering is what makes spec
        FR-019 and FR-035 fall out in sequence with no extra coordination - and
        why a repository with nothing to catch up emits no `catchup` event at
        all, which is spec FR-020's "no empty progress display".

        With `CODEPEDIA_PROGRESS_STREAM` unset every emit is a no-op, so a
        person's own `codepedia serve` prints exactly what it always did.
        """
        reindex_pipeline.run(batch, on_progress=_emit_catchup_progress)

    _refresh_wiki_shell(doc_generator, root)

    watcher = RepositoryWatcher(
        repository_root=root,
        on_batch=_run_batch,
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
