from __future__ import annotations

from pathlib import Path
from shutil import copytree

from dependency_graph import DependencyGraph
from local_llm.models import AvailabilityStatus
from parser_engine import SourceFile, extract_symbols
from repository_metadata import DependencyEdge, RepositoryMetadataStore, compute_content_hash
from repository_metadata.sqlite_store import stable_repository_id, stable_source_file_id


def fixture_root() -> Path:
    return Path("tests/integration/fixtures/repository-metadata/sample-repo")


def copy_fixture_repo(tmp_path: Path) -> Path:
    destination = tmp_path / "sample-repo"
    copytree(fixture_root(), destination)
    return destination


def build_indexed_repo(tmp_path: Path):
    """Index the alpha/beta/gamma sample repo and return (root, store, graph)."""
    root = copy_fixture_repo(tmp_path)
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
    return root, store, graph


class RecordingLLMEngine:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.modelName = "llama3"
        self.endpointUrl = "http://localhost:11434"

    def checkAvailability(self) -> AvailabilityStatus:
        if self.available:
            return AvailabilityStatus(True, True, True, "available")
        return AvailabilityStatus(False, False, False, "local model unavailable")

    def isAvailableLocally(self) -> bool:
        return self.available

    def generate(self, prompt) -> str:
        from local_llm import PromptEnvelope

        envelope = prompt if isinstance(prompt, PromptEnvelope) else PromptEnvelope.from_prompt(prompt)
        rendered = envelope.to_prompt_text()
        symbol_line = next((line for line in rendered.splitlines() if line.startswith("Symbol name: ")), "Symbol name: unknown")
        symbol_name = symbol_line.split(": ", 1)[1]
        return f"{symbol_name} summary"
