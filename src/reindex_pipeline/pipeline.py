from __future__ import annotations

from pathlib import Path

from dependency_graph import DependencyGraph
from doc_generator import DocGenerator
from embedding_engine import EmbeddingEngine
from parser_engine import SourceFile, extract_symbols
from repo_scanner.ignore import load_ignore_matcher
from repo_watcher import ChangeBatch, ChangeType
from repository_metadata import CodeSummaryPipeline, LocalLLMUnavailableError, RepositoryMetadataStore, compute_content_hash
from vector_index import VectorIndex

from . import graph_sync
from .classification import classify_path, confirm_change
from .embeddings import remove_embeddings, update_embeddings
from .models import PathClassification, ReindexOutcome

# repository_metadata and dependency_graph key everything by the absolute path
# SourceFile.path/DependencyNode.sourceFile were constructed with (parser_engine's
# SourceFile needs a real filesystem path; see _reparse_and_store below) — so every
# call into those two components below uses the resolved absolute path. vector_index
# (via embeddings.py) and this pipeline's own public ReindexOutcome fields use the
# relative path instead, since those are either an independent key space (vector_index)
# or user/watcher-facing (ReindexOutcome, matching repo_watcher's FileChange.relative_path).


class IncrementalReindexPipeline:
    def __init__(
        self,
        *,
        repositoryRoot: str | Path,
        metadataStore: RepositoryMetadataStore,
        dependencyGraph: DependencyGraph,
        dependencyGraphPath: str | Path,
        summaryPipeline: CodeSummaryPipeline,
        vectorIndex: VectorIndex,
        embeddingEngine: EmbeddingEngine,
        docGenerator: DocGenerator,
    ) -> None:
        self.repositoryRoot = Path(repositoryRoot).expanduser().resolve()
        self.metadataStore = metadataStore
        self.dependencyGraph = dependencyGraph
        self.dependencyGraphPath = Path(dependencyGraphPath)
        self.summaryPipeline = summaryPipeline
        self.vectorIndex = vectorIndex
        self.embeddingEngine = embeddingEngine
        self.docGenerator = docGenerator
        self._ignoreMatcher = load_ignore_matcher(self.repositoryRoot)

    def run(self, batch: ChangeBatch) -> ReindexOutcome:
        to_remove: list[str] = []
        to_skip: list[str] = []
        candidates: list[str] = []
        classifications: dict[str, PathClassification] = {}

        for change in batch.changes:
            if change.change_type is ChangeType.DELETED:
                to_remove.append(change.relative_path)
                continue

            classification = classify_path(self.repositoryRoot, change.relative_path, self._ignoreMatcher)
            classifications[change.relative_path] = classification
            if classification.excluded or classification.isBinary or classification.language is None:
                continue

            if change.change_type is ChangeType.MODIFIED:
                confirmation = confirm_change(self.repositoryRoot, change.relative_path, self.metadataStore)
                if not confirmation.changed:
                    to_skip.append(change.relative_path)
                    continue

            candidates.append(change.relative_path)

        reprocessed: list[str] = []
        failed: list[str] = []
        inventories = []
        for relative_path in candidates:
            inventory = self._reparse_and_store(relative_path, classifications[relative_path].language)
            if inventory is None:
                failed.append(relative_path)
                continue
            inventories.append(inventory)
            reprocessed.append(relative_path)

        changed_edge_ids = graph_sync.sync_graph(
            graph=self.dependencyGraph,
            dependency_graph_path=self.dependencyGraphPath,
            inventories_to_ingest=inventories,
            source_files_to_remove=[str(self.repositoryRoot / relative_path) for relative_path in to_remove],
        )

        for relative_path in to_remove:
            self.metadataStore.delete_source_file(self.repositoryRoot, self.repositoryRoot / relative_path)

        absolute_reprocessed = [str(self.repositoryRoot / relative_path) for relative_path in reprocessed]

        regenerated_symbol_ids: tuple[str, ...] = ()
        summary_failure: str | None = None
        if reprocessed:
            try:
                results = self.summaryPipeline.summarizeRepository(
                    self.repositoryRoot,
                    incremental=True,
                    changed_paths=absolute_reprocessed,
                )
                regenerated_symbol_ids = tuple(result.symbolId for result in results)
            except LocalLLMUnavailableError as exc:
                summary_failure = str(exc)

        for relative_path in reprocessed:
            update_embeddings(
                repository_root=self.repositoryRoot,
                relative_path=relative_path,
                metadata_store=self.metadataStore,
                vector_index=self.vectorIndex,
                embedding_engine=self.embeddingEngine,
            )
        for relative_path in to_remove:
            remove_embeddings(relative_path=relative_path, vector_index=self.vectorIndex)

        documentation = self.docGenerator.generateRepositoryDocumentation(
            self.repositoryRoot,
            incremental=True,
            changedPaths=absolute_reprocessed,
            changedSymbolIds=regenerated_symbol_ids,
            changedDependencyEdgeIds=changed_edge_ids,
        )

        return ReindexOutcome(
            reprocessedPaths=tuple(reprocessed),
            skippedPaths=tuple(to_skip),
            removedPaths=tuple(to_remove),
            regeneratedSymbolIds=regenerated_symbol_ids,
            documentation=documentation,
            summaryFailure=summary_failure,
            failedPaths=tuple(failed),
        )

    def _reparse_and_store(self, relative_path: str, language: str):
        absolute_path = self.repositoryRoot / relative_path
        try:
            content = absolute_path.read_text(encoding="utf-8", errors="replace")
            source_file = SourceFile(path=absolute_path, language=language, content=content)
            inventory = extract_symbols(source_file)
        except Exception:
            return None
        self.metadataStore.store_inventory(
            repository_root=self.repositoryRoot,
            source_file=source_file,
            inventory=inventory,
            content_hash=compute_content_hash(absolute_path),
        )
        return inventory
