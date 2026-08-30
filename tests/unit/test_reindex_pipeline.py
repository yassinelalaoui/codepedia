from __future__ import annotations

from pathlib import Path
from shutil import copytree

import pytest

from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, open_doc_manifest_store
from embedding_engine import EmbeddingEngine
from parser_engine import SourceFile, extract_symbols
from reindex_pipeline import ChangeConfirmation, IncrementalReindexPipeline, PathClassification, ReindexBatch, ReindexOutcome
from reindex_pipeline.classification import confirm_change
from repo_watcher import ChangeBatch, ChangeType, FileChange
from repository_metadata import CodeSummaryPipeline, LocalLLMUnavailableError, RepositoryMetadataStore, compute_content_hash
from vector_index import VectorIndex


def _fixture_root() -> Path:
    return Path("tests/integration/fixtures/repository-metadata/sample-repo")


def _copy_fixture_repo(tmp_path: Path) -> Path:
    destination = tmp_path / "repo"
    copytree(_fixture_root(), destination)
    return destination


def test_models_are_constructible():
    batch = ReindexBatch(repositoryRoot=Path("/repo"), changes=(FileChange(relative_path="a.py", change_type=ChangeType.MODIFIED),))
    assert batch.changes[0].relative_path == "a.py"

    classification = PathClassification(relativePath="a.py", excluded=False, isBinary=False, language="Python")
    assert classification.language == "Python"

    confirmation = ChangeConfirmation(relativePath="a.py", currentHash="abc", changed=True)
    assert confirmation.changed is True

    outcome = ReindexOutcome()
    assert outcome.reprocessedPaths == ()
    assert outcome.failedPaths == ()


def test_confirm_change_reports_unchanged_when_hash_matches(tmp_path):
    root = _copy_fixture_repo(tmp_path)
    store = RepositoryMetadataStore(tmp_path / "metadata.sqlite")
    store.ensure_repository(root, detected_languages=("python",))
    alpha_path = root / "alpha.py"
    source_file = SourceFile(path=alpha_path, language="python")
    inventory = extract_symbols(source_file)
    content_hash = compute_content_hash(alpha_path)
    store.store_inventory(repository_root=root, source_file=source_file, inventory=inventory, content_hash=content_hash)

    confirmation = confirm_change(root, "alpha.py", store)

    assert confirmation.changed is False
    assert confirmation.currentHash == content_hash


def test_confirm_change_reports_changed_for_a_genuine_edit(tmp_path):
    root = _copy_fixture_repo(tmp_path)
    store = RepositoryMetadataStore(tmp_path / "metadata.sqlite")
    store.ensure_repository(root, detected_languages=("python",))
    alpha_path = root / "alpha.py"
    source_file = SourceFile(path=alpha_path, language="python")
    inventory = extract_symbols(source_file)
    store.store_inventory(
        repository_root=root,
        source_file=source_file,
        inventory=inventory,
        content_hash=compute_content_hash(alpha_path),
    )

    alpha_path.write_text(alpha_path.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")

    confirmation = confirm_change(root, "alpha.py", store)

    assert confirmation.changed is True


def test_confirm_change_reports_changed_when_no_prior_hash_exists(tmp_path):
    root = _copy_fixture_repo(tmp_path)
    store = RepositoryMetadataStore(tmp_path / "metadata.sqlite")
    store.ensure_repository(root, detected_languages=("python",))

    confirmation = confirm_change(root, "alpha.py", store)

    assert confirmation.changed is True


def _build_minimal_pipeline(tmp_path: Path, *, summary_pipeline, root: Path | None = None) -> IncrementalReindexPipeline:
    root = root or _copy_fixture_repo(tmp_path)
    store = RepositoryMetadataStore(tmp_path / "metadata.sqlite")
    store.ensure_repository(root, detected_languages=("python",))
    graph = DependencyGraph(id="graph-1", sourceFile=str(root))
    manifest_store = open_doc_manifest_store(tmp_path / "manifest.sqlite")
    doc_generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=tmp_path / "docs",
        repositoryRoot=root,
    )
    vector_index = VectorIndex(root, tmp_path / "vector-meta.sqlite", embedding_engine=_FakeEmbeddingEngine())
    return IncrementalReindexPipeline(
        repositoryRoot=root,
        metadataStore=store,
        dependencyGraph=graph,
        dependencyGraphPath=tmp_path / "graph.sqlite",
        summaryPipeline=summary_pipeline,
        vectorIndex=vector_index,
        embeddingEngine=_FakeEmbeddingEngine(),
        docGenerator=doc_generator,
    ), root


class _FakeEmbeddingEngine:
    def embed(self, text: str) -> tuple[float, ...]:
        return (float(len(text)), 1.0)


def test_reparse_and_store_reports_none_for_invalid_syntax(tmp_path):
    pipeline, root = _build_minimal_pipeline(tmp_path, summary_pipeline=None)
    bad_file = root / "broken.py"
    bad_file.write_text("def broken(:\n    pass\n", encoding="utf-8")

    result = pipeline._reparse_and_store("broken.py", "Python")

    assert result is None


class _RaisingSummaryPipeline:
    """A summary chain with nothing reachable behind it.

    `restoreSummariesFromLedger` deliberately still succeeds: it calls no
    provider, and the point of the ledger is that an unreachable model leaves a
    file documented by what is already known instead of blank. Only
    `summarizeRepository` fails here.
    """

    def restoreSummariesFromLedger(self, *args, **kwargs):
        return (0, 0)

    def summarizeRepository(self, *args, **kwargs):
        raise LocalLLMUnavailableError("local model is unavailable for this test")


def test_run_surfaces_summary_failure_without_raising(tmp_path):
    pipeline, root = _build_minimal_pipeline(tmp_path, summary_pipeline=_RaisingSummaryPipeline())
    batch = ChangeBatch(changes=(FileChange(relative_path="alpha.py", change_type=ChangeType.CREATED),))

    outcome = pipeline.run(batch)

    assert outcome.summaryFailure is not None
    assert "unavailable" in outcome.summaryFailure
    assert outcome.reprocessedPaths == ("alpha.py",)
    # Metadata/graph updates still completed despite the summary failure.
    stored = pipeline.metadataStore.load_repository(root)
    assert any(bundle.file.path.endswith("alpha.py") for bundle in stored.files)


def test_run_reports_a_failed_path_and_continues_with_the_rest_of_the_batch(tmp_path):
    pipeline, root = _build_minimal_pipeline(tmp_path, summary_pipeline=_RaisingSummaryPipeline())
    (root / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    batch = ChangeBatch(
        changes=(
            FileChange(relative_path="alpha.py", change_type=ChangeType.CREATED),
            FileChange(relative_path="broken.py", change_type=ChangeType.CREATED),
        )
    )

    outcome = pipeline.run(batch)

    assert outcome.failedPaths == ("broken.py",)
    assert "alpha.py" in outcome.reprocessedPaths
