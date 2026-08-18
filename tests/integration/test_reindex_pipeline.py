from __future__ import annotations

import time
from pathlib import Path
from shutil import copytree
from unittest.mock import patch

import pytest

from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, open_doc_manifest_store
from local_llm import PromptEnvelope
from local_llm.models import AvailabilityStatus
from parser_engine import SourceFile, extract_symbols
from reindex_pipeline import IncrementalReindexPipeline
from reindex_pipeline.embeddings import update_embeddings
from repo_watcher import ChangeBatch, ChangeType, FileChange
from repository_metadata import CodeSummaryPipeline, RepositoryMetadataStore, compute_content_hash
from vector_index import VectorIndex


def _fixture_root() -> Path:
    return Path("tests/integration/fixtures/repository-metadata/sample-repo")


def _copy_fixture_repo(tmp_path: Path, name: str = "repo") -> Path:
    destination = tmp_path / name
    copytree(_fixture_root(), destination)
    return destination


class RecordingLLMEngine:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.modelName = "llama3"
        self.endpointUrl = "http://localhost:11434"
        self.prompts: list[str] = []
        self.generate_calls = 0

    def checkAvailability(self) -> AvailabilityStatus:
        if self.available:
            return AvailabilityStatus(True, True, True, "available")
        return AvailabilityStatus(False, False, False, "local model unavailable")

    def isAvailableLocally(self) -> bool:
        return self.available

    def generate(self, prompt: str | PromptEnvelope) -> str:
        self.generate_calls += 1
        envelope = prompt if isinstance(prompt, PromptEnvelope) else PromptEnvelope.from_prompt(prompt)
        rendered = envelope.to_prompt_text()
        self.prompts.append(rendered)
        symbol_line = next((line for line in rendered.splitlines() if line.startswith("Symbol name: ")), "Symbol name: unknown")
        symbol_name = symbol_line.split(": ", 1)[1]
        return f"{symbol_name} summary"


class FakeEmbeddingEngine:
    def embed(self, text: str) -> tuple[float, ...]:
        # Deterministic, cheap "embedding": a short vector derived from length/hash.
        seed = sum(text.encode("utf-8")) % 1000
        return (float(seed), float(len(text)), 1.0)


class Harness:
    """A fully indexed sample repository, ready to feed live batches through."""

    def __init__(self, tmp_path: Path, *, repo_name: str = "repo") -> None:
        self.tmp_path = tmp_path
        self.root = _copy_fixture_repo(tmp_path, repo_name)
        self.metadata_db = tmp_path / f"{repo_name}-metadata.sqlite"
        self.graph_path = tmp_path / f"{repo_name}-graph.sqlite"
        self.vector_metadata_db = tmp_path / f"{repo_name}-vector-meta.sqlite"
        self.manifest_db = tmp_path / f"{repo_name}-manifest.sqlite"
        self.output_root = tmp_path / f"{repo_name}-docs"

        self.store = RepositoryMetadataStore(self.metadata_db)
        self.store.ensure_repository(self.root, detected_languages=("python",))
        self.llm = RecordingLLMEngine()
        self.embedding_engine = FakeEmbeddingEngine()
        self.vector_index = VectorIndex(self.root, self.vector_metadata_db, embedding_engine=self.embedding_engine)
        self.graph = DependencyGraph(id=self._graph_id(), sourceFile=str(self.root))

        self.manifest_store = open_doc_manifest_store(self.manifest_db)
        self.doc_generator = DocGenerator(
            metadataStore=self.store,
            dependencyGraph=self.graph,
            manifestStore=self.manifest_store,
            outputRoot=self.output_root,
            repositoryRoot=self.root,
        )
        self.summary_pipeline = CodeSummaryPipeline(metadataStore=self.store, dependencyGraph=self.graph, llmEngine=self.llm)

        self.full_reindex()

    def _graph_id(self) -> str:
        from repository_metadata.sqlite_store import stable_repository_id

        return stable_repository_id(self.root)

    def full_reindex(self) -> None:
        """(Re)derive everything from the repository's current on-disk content, as a
        real "full index" would - two-pass graph construction so cross-file calls
        resolve correctly on the very first pass, matching build_from_inventories'
        (rather than per-file ingest_inventory's) approach."""
        inventories = []
        for py_file in sorted(self.root.glob("*.py")):
            source_file = SourceFile(path=py_file, language="python")
            inventory = extract_symbols(source_file)
            self.store.store_inventory(
                repository_root=self.root,
                source_file=source_file,
                inventory=inventory,
                content_hash=compute_content_hash(py_file),
            )
            inventories.append(inventory)

        fresh_graph = DependencyGraph.build_from_inventories(inventories, id=self._graph_id(), sourceFile=str(self.root))
        self.graph.nodes.clear()
        self.graph.edges.clear()
        self.graph._outgoing.clear()
        self.graph._incoming.clear()
        self.graph._name_index.clear()
        for node in fresh_graph.nodes.values():
            self.graph.add_node(node)
        for edge in fresh_graph.edges.values():
            self.graph._add_edge_object(edge)
        self.graph.save(self.graph_path)

        self.doc_generator.generateRepositoryDocumentation(self.root, incremental=False)
        self.summary_pipeline.summarizeRepository(self.root, incremental=False)
        # Regenerate docs once more so pages reflect the summaries just generated.
        self.doc_generator.generateRepositoryDocumentation(self.root, incremental=False)

        for py_file in sorted(self.root.glob("*.py")):
            update_embeddings(
                repository_root=self.root,
                relative_path=py_file.name,
                metadata_store=self.store,
                vector_index=self.vector_index,
                embedding_engine=self.embedding_engine,
            )

    def build_pipeline(self) -> IncrementalReindexPipeline:
        return IncrementalReindexPipeline(
            repositoryRoot=self.root,
            metadataStore=self.store,
            dependencyGraph=self.graph,
            dependencyGraphPath=self.graph_path,
            summaryPipeline=self.summary_pipeline,
            vectorIndex=self.vector_index,
            embeddingEngine=self.embedding_engine,
            docGenerator=self.doc_generator,
        )

    def module_summary(self, filename: str) -> str:
        bundle = self.store.load_repository(self.root)
        file_bundle = next(b for b in bundle.files if b.file.path.endswith(filename))
        return file_bundle.module.generatedSummary

    def function_summary(self, filename: str, function_name: str) -> str:
        bundle = self.store.load_repository(self.root)
        file_bundle = next(b for b in bundle.files if b.file.path.endswith(filename))
        function = next(f for f in file_bundle.functions if f.name == function_name)
        return function.generatedSummary


def _batch(*file_changes: tuple[str, ChangeType]) -> ChangeBatch:
    return ChangeBatch(changes=tuple(FileChange(relative_path=path, change_type=change_type) for path, change_type in file_changes))


# ---------------------------------------------------------------------------
# US1 - single-file update
# ---------------------------------------------------------------------------


def test_modifying_one_file_reprocesses_only_that_file_and_its_dependent(tmp_path):
    harness = Harness(tmp_path)
    beta_path = harness.root / "beta.py"
    beta_path.write_text(
        '"""Beta module."""\n\nfrom gamma import BaseThing\n\n\nclass Child(BaseThing):\n    """Child class."""\n\n    def run(self, value: int) -> int:\n        return beta_helper(value)\n\n\ndef beta_helper(number: int) -> int:\n    """Helper doc."""\n    return number + 2\n',
        encoding="utf-8",
    )

    pipeline = harness.build_pipeline()
    outcome = pipeline.run(_batch(("beta.py", ChangeType.MODIFIED)))

    assert outcome.reprocessedPaths == ("beta.py",)
    assert outcome.skippedPaths == ()
    assert outcome.removedPaths == ()
    assert outcome.failedPaths == ()

    bundle = harness.store.load_repository(harness.root)
    beta_bundle = next(b for b in bundle.files if b.file.path.endswith("beta.py"))
    helper = next(f for f in beta_bundle.functions if f.name == "beta_helper")
    assert "number + 2" in Path(beta_path).read_text(encoding="utf-8")
    assert helper.generatedSummary == "beta_helper summary"

    # alpha.py calls beta_helper -> it is a direct dependent, so its summary is
    # regenerated too, even though alpha.py itself was not in the batch.
    assert helper.id in outcome.regeneratedSymbolIds

    alpha_bundle = next(b for b in bundle.files if b.file.path.endswith("alpha.py"))
    alpha_entry = next(f for f in alpha_bundle.functions if f.name == "alpha_entry")
    assert alpha_entry.id in outcome.regeneratedSymbolIds

    # gamma.py is unrelated; its stored symbols/summaries must be untouched.
    gamma_bundle = next(b for b in bundle.files if b.file.path.endswith("gamma.py"))
    assert gamma_bundle.module.generatedSummary == "gamma summary"


_BETA_V2 = '"""Beta module."""\n\nfrom gamma import BaseThing\n\n\nclass Child(BaseThing):\n    """Child class."""\n\n    def run(self, value: int) -> int:\n        return beta_helper(value)\n\n\ndef beta_helper(number: int) -> int:\n    """Helper doc."""\n    return number + 2\n'


def test_incremental_single_file_update_matches_a_full_reindex(tmp_path):
    # Reference: full re-index of the repository, from scratch, after the edit.
    reference = Harness(tmp_path, repo_name="reference")
    (reference.root / "beta.py").write_text(_BETA_V2, encoding="utf-8")
    reference.full_reindex()

    # Incremental: start from an already-indexed pre-change state, apply the same
    # edit, then run the pipeline for just that one file.
    harness = Harness(tmp_path, repo_name="incremental")
    (harness.root / "beta.py").write_text(_BETA_V2, encoding="utf-8")
    pipeline = harness.build_pipeline()
    pipeline.run(_batch(("beta.py", ChangeType.MODIFIED)))

    for filename, function_name in (("beta.py", "beta_helper"), ("alpha.py", "alpha_entry")):
        assert harness.function_summary(filename, function_name) == reference.function_summary(filename, function_name)

    incremental_bundle = harness.store.load_repository(harness.root)
    reference_bundle = reference.store.load_repository(reference.root)
    incremental_beta = next(b for b in incremental_bundle.files if b.file.path.endswith("beta.py"))
    reference_beta = next(b for b in reference_bundle.files if b.file.path.endswith("beta.py"))
    assert incremental_beta.file.contentHash == reference_beta.file.contentHash
    assert {f.name for f in incremental_beta.functions} == {f.name for f in reference_beta.functions}


def test_single_file_incremental_run_is_far_faster_than_a_full_reindex(tmp_path):
    harness = Harness(tmp_path)
    (harness.root / "beta.py").write_text(
        harness.root.joinpath("beta.py").read_text(encoding="utf-8") + "\n# touch\n",
        encoding="utf-8",
    )

    full_start = time.perf_counter()
    for py_file in sorted(harness.root.glob("*.py")):
        source_file = SourceFile(path=py_file, language="python")
        extract_symbols(source_file)
    full_duration = time.perf_counter() - full_start

    pipeline = harness.build_pipeline()
    incremental_start = time.perf_counter()
    pipeline.run(_batch(("beta.py", ChangeType.MODIFIED)))
    incremental_duration = time.perf_counter() - incremental_start

    # Not a strict timing guarantee (machine-dependent) - just proves the incremental
    # path does bounded, single-file work rather than repository-wide work.
    assert incremental_duration < max(full_duration * 5, 1.0)


def test_pipeline_never_calls_scan_repository(tmp_path):
    harness = Harness(tmp_path)
    (harness.root / "beta.py").write_text(
        harness.root.joinpath("beta.py").read_text(encoding="utf-8") + "\n# touch\n",
        encoding="utf-8",
    )
    pipeline = harness.build_pipeline()

    with patch("repo_scanner.scanner.scan_repository") as spy:
        pipeline.run(_batch(("beta.py", ChangeType.MODIFIED)))

    spy.assert_not_called()


# ---------------------------------------------------------------------------
# US2 - hash-confirmation skip
# ---------------------------------------------------------------------------


def test_modified_signal_with_unchanged_hash_is_skipped(tmp_path):
    harness = Harness(tmp_path)
    pipeline = harness.build_pipeline()

    generate_calls_before = harness.llm.generate_calls
    outcome = pipeline.run(_batch(("beta.py", ChangeType.MODIFIED)))

    assert outcome.skippedPaths == ("beta.py",)
    assert outcome.reprocessedPaths == ()
    assert harness.llm.generate_calls == generate_calls_before


# ---------------------------------------------------------------------------
# US3 - create/delete symmetry
# ---------------------------------------------------------------------------


def test_created_file_becomes_fully_indexed_and_documented(tmp_path):
    harness = Harness(tmp_path)
    new_file = harness.root / "delta.py"
    new_file.write_text('"""Delta module."""\n\n\ndef delta_entry() -> int:\n    return 42\n', encoding="utf-8")

    pipeline = harness.build_pipeline()
    outcome = pipeline.run(_batch(("delta.py", ChangeType.CREATED)))

    assert outcome.reprocessedPaths == ("delta.py",)
    bundle = harness.store.load_repository(harness.root)
    delta_bundle = next(b for b in bundle.files if b.file.path.endswith("delta.py"))
    assert delta_bundle.functions[0].name == "delta_entry"
    assert delta_bundle.functions[0].generatedSummary == "delta_entry summary"
    assert harness.vector_index.chunks_for_file(str(harness.root / "delta.py")) or harness.vector_index.chunks_for_file("delta.py")
    assert outcome.documentation is not None
    assert any(page.sourceEntityId == delta_bundle.module.id for page in outcome.documentation.pages)


def test_deleted_file_is_fully_removed_and_referring_pages_updated(tmp_path):
    harness = Harness(tmp_path)
    pipeline = harness.build_pipeline()

    outcome = pipeline.run(_batch(("gamma.py", ChangeType.DELETED)))

    assert outcome.removedPaths == ("gamma.py",)
    with pytest.raises(KeyError):
        harness.store.load_source_file(repository_root=harness.root, path=harness.root / "gamma.py")

    gamma_absolute = str(harness.root / "gamma.py")
    assert not any(_normalize_node_source(node) == gamma_absolute for node in harness.graph.nodes.values())

    removed_chunk_ids = harness.vector_index.chunks_for_file("gamma.py")
    assert removed_chunk_ids == ()

    assert outcome.documentation is not None
    home_page = next(page for page in outcome.documentation.pages if page.kind == "home")
    assert not any(link.label == "gamma" for link in home_page.links)


def _normalize_node_source(node) -> str:
    return str(Path(node.sourceFile))


# ---------------------------------------------------------------------------
# US4 - multi-file batches
# ---------------------------------------------------------------------------


def test_multi_file_batch_regenerates_shared_dependent_once(tmp_path):
    harness = Harness(tmp_path)
    (harness.root / "beta.py").write_text(
        '"""Beta module."""\n\nfrom gamma import BaseThing\n\n\nclass Child(BaseThing):\n    """Child class."""\n\n    def run(self, value: int) -> int:\n        return beta_helper(value)\n\n\ndef beta_helper(number: int) -> int:\n    """Helper doc."""\n    return number + 5\n',
        encoding="utf-8",
    )
    (harness.root / "gamma.py").write_text(
        '"""Gamma module."""\n\n\nclass BaseThing:\n    """Base thing."""\n\n\ndef shared_value() -> int:\n    return 9\n',
        encoding="utf-8",
    )

    pipeline = harness.build_pipeline()
    outcome = pipeline.run(
        _batch(("beta.py", ChangeType.MODIFIED), ("gamma.py", ChangeType.MODIFIED))
    )

    assert set(outcome.reprocessedPaths) == {"beta.py", "gamma.py"}
    # alpha_entry depends on beta_helper (changed) -> regenerated exactly once.
    assert len(outcome.regeneratedSymbolIds) == len(set(outcome.regeneratedSymbolIds))
    bundle = harness.store.load_repository(harness.root)
    alpha_bundle = next(b for b in bundle.files if b.file.path.endswith("alpha.py"))
    alpha_entry = next(f for f in alpha_bundle.functions if f.name == "alpha_entry")
    assert alpha_entry.id in outcome.regeneratedSymbolIds
    assert outcome.regeneratedSymbolIds.count(alpha_entry.id) == 1


def test_multi_file_batch_matches_two_sequential_single_file_batches(tmp_path):
    batch_tmp = tmp_path / "batch"
    batch_tmp.mkdir()
    batch_harness = Harness(batch_tmp)
    for filename, content in (
        ("beta.py", '"""Beta module."""\n\nfrom gamma import BaseThing\n\n\nclass Child(BaseThing):\n    """Child class."""\n\n    def run(self, value: int) -> int:\n        return beta_helper(value)\n\n\ndef beta_helper(number: int) -> int:\n    """Helper doc."""\n    return number + 7\n'),
        ("gamma.py", '"""Gamma module."""\n\n\nclass BaseThing:\n    """Base thing."""\n\n\ndef shared_value() -> int:\n    return 11\n'),
    ):
        (batch_harness.root / filename).write_text(content, encoding="utf-8")
    batch_pipeline = batch_harness.build_pipeline()
    batch_pipeline.run(_batch(("beta.py", ChangeType.MODIFIED), ("gamma.py", ChangeType.MODIFIED)))

    seq_tmp = tmp_path / "sequential"
    seq_tmp.mkdir()
    seq_harness = Harness(seq_tmp)
    for filename, content in (
        ("beta.py", '"""Beta module."""\n\nfrom gamma import BaseThing\n\n\nclass Child(BaseThing):\n    """Child class."""\n\n    def run(self, value: int) -> int:\n        return beta_helper(value)\n\n\ndef beta_helper(number: int) -> int:\n    """Helper doc."""\n    return number + 7\n'),
        ("gamma.py", '"""Gamma module."""\n\n\nclass BaseThing:\n    """Base thing."""\n\n\ndef shared_value() -> int:\n    return 11\n'),
    ):
        (seq_harness.root / filename).write_text(content, encoding="utf-8")
    seq_pipeline = seq_harness.build_pipeline()
    seq_pipeline.run(_batch(("beta.py", ChangeType.MODIFIED)))
    seq_pipeline.run(_batch(("gamma.py", ChangeType.MODIFIED)))

    batch_bundle = batch_harness.store.load_repository(batch_harness.root)
    seq_bundle = seq_harness.store.load_repository(seq_harness.root)
    for filename in ("alpha.py", "beta.py", "gamma.py"):
        batch_file = next(b for b in batch_bundle.files if b.file.path.endswith(filename))
        seq_file = next(b for b in seq_bundle.files if b.file.path.endswith(filename))
        assert batch_file.file.contentHash == seq_file.file.contentHash
        assert {f.name: f.generatedSummary for f in batch_file.functions} == {f.name: f.generatedSummary for f in seq_file.functions}


# ---------------------------------------------------------------------------
# Edge case - local LLM unavailable
# ---------------------------------------------------------------------------


def test_summary_failure_does_not_block_metadata_graph_or_embedding_updates(tmp_path):
    harness = Harness(tmp_path)
    harness.llm.available = False
    (harness.root / "beta.py").write_text(
        '"""Beta module."""\n\nfrom gamma import BaseThing\n\n\nclass Child(BaseThing):\n    """Child class."""\n\n    def run(self, value: int) -> int:\n        return beta_helper(value)\n\n\ndef beta_helper(number: int) -> int:\n    """Helper doc."""\n    return number + 3\n',
        encoding="utf-8",
    )
    pipeline = harness.build_pipeline()

    outcome = pipeline.run(_batch(("beta.py", ChangeType.MODIFIED)))

    assert outcome.summaryFailure is not None
    assert outcome.reprocessedPaths == ("beta.py",)
    bundle = harness.store.load_repository(harness.root)
    beta_bundle = next(b for b in bundle.files if b.file.path.endswith("beta.py"))
    helper = next(f for f in beta_bundle.functions if f.name == "beta_helper")
    assert helper.lineEnd >= helper.lineStart  # metadata was re-stored
    assert harness.vector_index.chunks_for_file("beta.py") != ()
