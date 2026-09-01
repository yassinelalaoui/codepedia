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


def _write_head(root: Path, sha: str) -> str:
    git_dir = root / ".git"
    git_dir.mkdir(exist_ok=True)
    (git_dir / "HEAD").write_text(sha, encoding="utf-8")
    return sha


def test_each_pass_re_reads_head(tmp_path):
    """N6: `serve` outlives the commit it started on.

    HEAD used to be read once, by `ensure_repository` at the start of an
    indexing run. That is right for `index`, and wrong for a watcher that keeps
    regenerating pages for hours: every page written after a `git commit`
    footed itself with the commit the process was launched on, which is a
    provenance line that asserts something false.
    """
    root = _copy_fixture_repo(tmp_path)
    first = _write_head(root, "a" * 40)
    pipeline, _ = _build_minimal_pipeline(tmp_path, summary_pipeline=_RaisingSummaryPipeline(), root=root)
    batch = ChangeBatch(changes=(FileChange(relative_path="alpha.py", change_type=ChangeType.CREATED),))

    pipeline.run(batch)
    assert pipeline.metadataStore.load_repository(root).repository.commitSha == first

    second = _write_head(root, "b" * 40)
    pipeline.run(batch)

    assert pipeline.metadataStore.load_repository(root).repository.commitSha == second


def test_an_unreadable_head_leaves_the_recorded_commit_alone(tmp_path):
    """An empty read means "unknown", and unknown must not overwrite known.

    `read_commit_sha` degrades to "" for everything uninteresting - not a
    repository, an unborn branch, a directory it cannot read - so writing it
    back would turn a transient condition into an erased provenance.
    """
    root = _copy_fixture_repo(tmp_path)
    known = _write_head(root, "c" * 40)
    pipeline, _ = _build_minimal_pipeline(tmp_path, summary_pipeline=_RaisingSummaryPipeline(), root=root)
    batch = ChangeBatch(changes=(FileChange(relative_path="alpha.py", change_type=ChangeType.CREATED),))
    pipeline.run(batch)

    (root / ".git" / "HEAD").unlink()
    pipeline.run(batch)

    assert pipeline.metadataStore.load_repository(root).repository.commitSha == known


def test_refreshing_the_commit_never_blanks_the_language_list(tmp_path):
    """Why this is not `ensure_repository(commit_sha=...)`.

    `upsert_repository` writes `detected_languages` from its argument, so a
    caller that only knows the new sha would silently empty the column on its
    way past.
    """
    root = _copy_fixture_repo(tmp_path)
    _write_head(root, "d" * 40)
    store = RepositoryMetadataStore(tmp_path / "languages.sqlite")
    store.ensure_repository(root, detected_languages=("python", "markdown"))

    store.refresh_commit_sha(root)

    repository = store.load_repository_record(root)
    assert repository.detectedLanguages == ("markdown", "python")
    assert repository.commitSha == "d" * 40



def test_classify_path_applies_the_documentation_perimeter(tmp_path):
    # The watcher has to answer the same question `scan_repository` answers, or
    # a save under `specs/` gets reindexed here while a full `index` no longer
    # knows the file exists, and the two views of the repository drift apart.
    from repo_scanner.docs_scope import DocsScope
    from repo_scanner.ignore import load_ignore_matcher
    from reindex_pipeline.classification import classify_path

    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "specs").mkdir()
    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (root / "specs" / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    matcher = load_ignore_matcher(root)
    scope = DocsScope()

    assert classify_path(root, "docs/guide.md", matcher, scope).language == "Markdown"
    assert classify_path(root, "specs/spec.md", matcher, scope).language is None
    # Excluded, not ignored: `.gitignore` has no opinion about `specs/`, the
    # documentation perimeter does - and code is never scoped by it.
    assert classify_path(root, "specs/spec.md", matcher, scope).excluded is False
    assert classify_path(root, "app.py", matcher, scope).language == "Python"


def test_classify_path_honours_a_declared_perimeter(tmp_path):
    from repo_scanner.docs_scope import DocsScope
    from repo_scanner.ignore import load_ignore_matcher
    from reindex_pipeline.classification import classify_path

    root = tmp_path / "repo"
    (root / "specs").mkdir(parents=True)
    (root / "specs" / "spec.md").write_text("# Spec\n", encoding="utf-8")
    matcher = load_ignore_matcher(root)

    assert classify_path(root, "specs/spec.md", matcher, DocsScope(include=("specs/",))).language == "Markdown"
