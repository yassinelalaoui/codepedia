from __future__ import annotations

from pathlib import Path
from shutil import copytree

import pytest

from dependency_graph import DependencyGraph
from local_llm import PromptEnvelope
from local_llm.models import AvailabilityStatus
from parser_engine import SourceFile, extract_symbols
from provider_routing import FailoverExecutor, ProviderRef
from repository_metadata import CodeSummaryPipeline, DependencyEdge, LocalLLMUnavailableError, RepositoryMetadataStore, compute_content_hash
from repository_metadata.sqlite_store import stable_repository_id, stable_source_file_id


def _fixture_root() -> Path:
    return Path("tests/integration/fixtures/repository-metadata/sample-repo")


def _copy_fixture_repo(tmp_path: Path) -> Path:
    destination = tmp_path / "sample-repo"
    copytree(_fixture_root(), destination)
    return destination


def _inventories_and_graph(root: Path):
    files = [root / "alpha.py", root / "beta.py", root / "gamma.py"]
    inventories = [extract_symbols(SourceFile(path=path, language="python")) for path in files]
    graph = DependencyGraph.build_from_inventories(inventories, sourceFile=str(root))
    repository_id = stable_repository_id(root)
    edges = [
        DependencyEdge(
            sourceId=edge.sourceId,
            targetId=edge.targetId,
            type=edge.type,
            sourceFileId=stable_source_file_id(repository_id, edge.sourceFile or root),
            metadata=dict(edge.metadata),
        )
        for edge in graph.edges.values()
    ]
    return inventories, edges, graph


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

    def isAvailable(self) -> bool:
        return self.available

    def generate(self, prompt: str | PromptEnvelope) -> str:
        self.generate_calls += 1
        envelope = prompt if isinstance(prompt, PromptEnvelope) else PromptEnvelope.from_prompt(prompt)
        rendered = envelope.to_prompt_text()
        self.prompts.append(rendered)
        symbol_line = next((line for line in rendered.splitlines() if line.startswith("Symbol name: ")), "Symbol name: unknown")
        symbol_name = symbol_line.split(": ", 1)[1]
        return f"{symbol_name} summary"


def _wrap(engine: RecordingLLMEngine) -> FailoverExecutor:
    """CodeSummaryPipeline now takes a `provider_routing.FailoverExecutor`
    wrapping the summary chain rather than a raw engine (spec 029) - a
    single-provider chain is regression-equivalent to today's direct-engine
    behavior."""
    return FailoverExecutor("summary", ((ProviderRef("local", engine.modelName), engine),))


def test_summary_pipeline_generates_and_persists_summaries(tmp_path):
    root = _copy_fixture_repo(tmp_path)
    inventories, edges, graph = _inventories_and_graph(root)
    store = RepositoryMetadataStore(tmp_path / "repo.sqlite")
    store.ensure_repository(root, detected_languages=("python",))

    for inventory in inventories:
        source_path = Path(inventory.sourceFile)
        store.store_inventory(
            repository_root=root,
            source_file=SourceFile(path=source_path, language="python"),
            inventory=inventory,
            dependency_edges=edges,
            content_hash=compute_content_hash(source_path),
        )

    engine = RecordingLLMEngine()
    pipeline = CodeSummaryPipeline(metadataStore=store, dependencyGraph=graph, llmEngine=_wrap(engine))

    results = pipeline.summarizeRepository(root, incremental=False)
    reopened = store.load_repository(root)

    assert pipeline.isReady() is True
    assert len(results) == 9
    assert "inner" not in {result.symbolName for result in results}
    assert all(result.generatedSummary.endswith("summary") for result in results)

    alpha_bundle = next(bundle for bundle in reopened.files if bundle.file.path.endswith("alpha.py"))
    beta_bundle = next(bundle for bundle in reopened.files if bundle.file.path.endswith("beta.py"))
    gamma_bundle = next(bundle for bundle in reopened.files if bundle.file.path.endswith("gamma.py"))

    assert alpha_bundle.module.generatedSummary == "alpha summary"
    assert alpha_bundle.functions[0].generatedSummary == "alpha_entry summary"
    assert beta_bundle.module.generatedSummary == "beta summary"
    assert beta_bundle.classes[0].generatedSummary == "Child summary"
    assert beta_bundle.functions[0].generatedSummary == "run summary"
    assert beta_bundle.functions[1].generatedSummary == "beta_helper summary"
    assert gamma_bundle.module.generatedSummary == "gamma summary"
    assert gamma_bundle.classes[0].generatedSummary == "BaseThing summary"
    assert gamma_bundle.functions[0].generatedSummary == "shared_value summary"
    assert any("Imports:" in prompt and "beta_helper" in prompt for prompt in engine.prompts)
    assert any("Direct callers:" in prompt and "alpha_entry" in prompt for prompt in engine.prompts)


def test_summary_pipeline_refuses_to_run_without_local_llm(tmp_path):
    root = _copy_fixture_repo(tmp_path)
    inventories, edges, graph = _inventories_and_graph(root)
    store = RepositoryMetadataStore(tmp_path / "repo.sqlite")
    store.ensure_repository(root, detected_languages=("python",))

    for inventory in inventories:
        source_path = Path(inventory.sourceFile)
        store.store_inventory(
            repository_root=root,
            source_file=SourceFile(path=source_path, language="python"),
            inventory=inventory,
            dependency_edges=edges,
            content_hash=compute_content_hash(source_path),
        )

    engine = RecordingLLMEngine(available=False)
    pipeline = CodeSummaryPipeline(metadataStore=store, dependencyGraph=graph, llmEngine=_wrap(engine))

    with pytest.raises(LocalLLMUnavailableError):
        pipeline.summarizeRepository(root)

    assert engine.generate_calls == 0


def test_summary_pipeline_regenerates_impacted_symbols_only(tmp_path):
    root = _copy_fixture_repo(tmp_path)
    inventories, edges, graph = _inventories_and_graph(root)
    store = RepositoryMetadataStore(tmp_path / "repo.sqlite")
    store.ensure_repository(root, detected_languages=("python",))

    for inventory in inventories:
        source_path = Path(inventory.sourceFile)
        store.store_inventory(
            repository_root=root,
            source_file=SourceFile(path=source_path, language="python"),
            inventory=inventory,
            dependency_edges=edges,
            content_hash=compute_content_hash(source_path),
        )

    engine = RecordingLLMEngine()
    pipeline = CodeSummaryPipeline(metadataStore=store, dependencyGraph=graph, llmEngine=_wrap(engine))

    beta_bundle = next(bundle for bundle in store.load_repository(root).files if bundle.file.path.endswith("beta.py"))
    beta_helper_id = beta_bundle.functions[1].id
    results = pipeline.summarizeImpactedSymbols(root, [beta_helper_id])

    assert {result.symbolName for result in results} == {"beta_helper", "alpha_entry", "run"}
