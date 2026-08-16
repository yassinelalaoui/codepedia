"""US1 (index), US2 (serve), US3 (config->index wiring), and US4 (actionable
errors) integration tests for the CLI orchestrator (specs/019-cli-orchestrator)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from shutil import copytree
from urllib.request import urlopen

import pytest
from typer.testing import CliRunner

import cli.config
import cli.config_command
import cli.index_command
import cli.main
import cli.serve_command
import cli.server
from cli.config import CLIConfiguration
from cli.errors import IndexNotFoundError, LocalModelUnavailableError, RepositoryNotFoundError, ServerBindError
from cli.index_command import run_index
from cli.serve_command import run_serve
from embedding_engine.models import EmbeddingAvailabilityStatus
from local_llm import PromptEnvelope
from local_llm.models import AvailabilityStatus
from repo_watcher import ChangeBatch, ChangeType, FileChange


# ---------------------------------------------------------------------------
# Shared fixtures and test doubles
# ---------------------------------------------------------------------------


def _fixture_root() -> Path:
    return Path("tests/integration/fixtures/repository-metadata/sample-repo")


def _copy_fixture_repo(tmp_path: Path, name: str = "repo") -> Path:
    destination = tmp_path / name
    copytree(_fixture_root(), destination)
    return destination


class RecordingLLMEngine:
    def __init__(
        self,
        *,
        model_name: str = "test-llm",
        endpoint_url: str = "http://localhost:11434",
        service_reachable: bool = True,
        model_installed: bool = True,
        installed_models: tuple[str, ...] = ("test-llm",),
    ) -> None:
        self.modelName = model_name
        self.endpointUrl = endpoint_url
        self.service_reachable = service_reachable
        self.model_installed = model_installed
        self._installed_models = installed_models
        self.generate_calls = 0

    @property
    def available(self) -> bool:
        return self.service_reachable and self.model_installed

    def checkAvailability(self) -> AvailabilityStatus:
        if not self.service_reachable:
            message = f"Local LLM service at {self.endpointUrl} is unavailable for model '{self.modelName}'."
        elif not self.model_installed:
            message = f"Local model '{self.modelName}' is not installed at {self.endpointUrl}."
        else:
            message = f"Local model '{self.modelName}' is available at {self.endpointUrl}."
        return AvailabilityStatus(self.available, self.service_reachable, self.model_installed, message)

    def isAvailableLocally(self) -> bool:
        return self.available

    def generate(self, prompt: str | PromptEnvelope) -> str:
        self.generate_calls += 1
        envelope = prompt if isinstance(prompt, PromptEnvelope) else PromptEnvelope.from_prompt(prompt)
        rendered = envelope.to_prompt_text()
        symbol_line = next((line for line in rendered.splitlines() if line.startswith("Symbol name: ")), "Symbol name: unknown")
        symbol_name = symbol_line.split(": ", 1)[1]
        return f"{symbol_name} summary"

    def listInstalledModels(self) -> tuple[str, ...]:
        return self._installed_models


class FakeEmbeddingEngine:
    def __init__(
        self,
        *,
        model_name: str = "test-embed",
        endpoint_url: str = "http://localhost:11434",
        runtime_reachable: bool = True,
        model_installed: bool = True,
        installed_models: tuple[str, ...] = ("test-embed",),
    ) -> None:
        self.modelName = model_name
        self.endpointUrl = endpoint_url
        self.runtime_reachable = runtime_reachable
        self.model_installed = model_installed
        self._installed_models = installed_models

    @property
    def available(self) -> bool:
        return self.runtime_reachable and self.model_installed

    def checkAvailability(self) -> EmbeddingAvailabilityStatus:
        if not self.runtime_reachable:
            message = f"The local embedding runtime at {self.endpointUrl} is not running."
        elif not self.model_installed:
            message = f"The local embedding model '{self.modelName}' is not installed at {self.endpointUrl}."
        else:
            message = f"The local embedding model '{self.modelName}' is available at {self.endpointUrl}."
        return EmbeddingAvailabilityStatus(self.available, self.runtime_reachable, self.model_installed, message)

    def isAvailableLocally(self) -> bool:
        return self.available

    def embed(self, text: str) -> tuple[float, ...]:
        seed = sum(text.encode("utf-8")) % 1000
        return (float(seed), float(len(text)), 1.0)

    def listInstalledModels(self) -> tuple[str, ...]:
        return self._installed_models


@pytest.fixture()
def cli_home(tmp_path, monkeypatch):
    """Redirect every `~/.repo-scanner/...` path this package computes to a
    temp directory, so tests never touch the real developer machine."""
    home = tmp_path / "home"
    monkeypatch.setattr(cli.config.paths, "repo_scanner_home", lambda: home)
    return home


INSTALLED_LLM_MODELS = (cli.config.DEFAULT_LLM_MODEL, "test-llm", "my-custom-model")
INSTALLED_EMBEDDING_MODELS = (CLIConfiguration().embeddingModel, "test-embed")


@pytest.fixture()
def fake_engines(monkeypatch):
    """Patch every module that constructs local engines to return
    lightweight, in-memory test doubles instead of real Ollama-backed ones.

    The doubles report a model as installed only if it's in
    `INSTALLED_LLM_MODELS`/`INSTALLED_EMBEDDING_MODELS`, so `config`'s
    not-installed warning (spec US3) has something real to detect.
    """

    def llm_factory(model_name: str, endpoint_url: str = "http://localhost:11434", **_: object) -> RecordingLLMEngine:
        return RecordingLLMEngine(
            model_name=model_name,
            endpoint_url=endpoint_url,
            model_installed=model_name in INSTALLED_LLM_MODELS,
            installed_models=INSTALLED_LLM_MODELS,
        )

    def embedding_factory(model_name: str = "test-embed", endpoint_url: str = "http://localhost:11434", **_: object) -> FakeEmbeddingEngine:
        return FakeEmbeddingEngine(
            model_name=model_name,
            endpoint_url=endpoint_url,
            model_installed=model_name in INSTALLED_EMBEDDING_MODELS,
            installed_models=INSTALLED_EMBEDDING_MODELS,
        )

    for module in (cli.index_command, cli.serve_command, cli.config_command):
        monkeypatch.setattr(module, "create_local_llm_engine", llm_factory)
        monkeypatch.setattr(module, "create_embedding_engine", embedding_factory)

    return llm_factory, embedding_factory


@pytest.fixture()
def no_bind_server(monkeypatch):
    """Prevent `start_local_server` from actually binding a socket/blocking."""
    calls: list[tuple] = []

    def fake_uvicorn_run(app, *, host, port):
        calls.append((host, port))

    monkeypatch.setattr(cli.server.uvicorn, "run", fake_uvicorn_run)
    return calls


def _repo_state_dirs(home: Path) -> list[Path]:
    repos_dir = home / "repos"
    if not repos_dir.exists():
        return []
    return list(repos_dir.iterdir())


# ---------------------------------------------------------------------------
# US1 - index
# ---------------------------------------------------------------------------


def test_run_index_populates_repository_state(tmp_path, cli_home, fake_engines):
    root = _copy_fixture_repo(tmp_path)
    result = run_index(root, config=CLIConfiguration())

    state_dirs = _repo_state_dirs(cli_home)
    assert len(state_dirs) == 1
    state_dir = state_dirs[0]

    assert (state_dir / "repository-metadata.sqlite").exists()
    assert (state_dir / "dependency-graph.sqlite").exists()
    # vector_index (006/007) only ever writes a real sqlite file at its
    # metadataPath; indexPath is recorded as a string field inside it, not
    # a separate file on disk.
    assert (state_dir / "vector-metadata.sqlite").exists()
    assert (state_dir / "doc-manifest.sqlite").exists()
    assert (state_dir / "docs" / "index.html").exists()
    module_pages = list((state_dir / "docs").glob("**/*.html"))
    assert len(module_pages) > 1  # home page + at least one module page

    assert result.docsRoot == state_dir / "docs"
    result.vectorIndex.close()


def test_run_index_rerun_replaces_prior_state_and_never_uses_watcher(tmp_path, cli_home, fake_engines, monkeypatch):
    root = _copy_fixture_repo(tmp_path)

    watcher_calls: list[object] = []
    monkeypatch.setattr(cli.index_command, "RepositoryWatcher", lambda **kwargs: watcher_calls.append(kwargs))

    first = run_index(root, config=CLIConfiguration())
    first.vectorIndex.close()
    first_state_dirs = _repo_state_dirs(cli_home)
    assert len(first_state_dirs) == 1

    # Modify a file so the second run has something new to pick up.
    (root / "beta.py").write_text((root / "beta.py").read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")

    second = run_index(root, config=CLIConfiguration())
    second_state_dirs = _repo_state_dirs(cli_home)
    assert len(second_state_dirs) == 1
    assert second_state_dirs[0] == first_state_dirs[0]  # same state dir, replaced in place
    assert not list(cli_home.glob("repos/*.staging-*"))
    assert watcher_calls == []  # index is always a full run, never incremental
    second.vectorIndex.close()


def test_run_index_failure_on_rerun_leaves_prior_successful_state_untouched(tmp_path, cli_home, fake_engines, monkeypatch):
    root = _copy_fixture_repo(tmp_path)

    first = run_index(root, config=CLIConfiguration())
    first.vectorIndex.close()
    state_dir = _repo_state_dirs(cli_home)[0]
    before_files = {p: p.read_bytes() for p in state_dir.rglob("*") if p.is_file()}

    def failing_summarize(self, *args, **kwargs):
        raise RuntimeError("simulated local LLM crash mid-run")

    monkeypatch.setattr(cli.index_command.CodeSummaryPipeline, "summarizeRepository", failing_summarize)

    with pytest.raises(RuntimeError, match="simulated local LLM crash"):
        run_index(root, config=CLIConfiguration())

    after_files = {p: p.read_bytes() for p in state_dir.rglob("*") if p.is_file()}
    assert before_files == after_files
    assert not list(cli_home.glob("repos/*.staging-*"))


def test_cli_runner_index_prints_url_and_stage_names_in_order(tmp_path, cli_home, fake_engines, no_bind_server):
    root = _copy_fixture_repo(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli.main.app, ["index", str(root)])

    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:8000/" in result.output
    stage_order = [
        "Validating repository",
        "Checking local model availability",
        "Scanning repository",
        "Parsing and extracting symbols",
        "Building dependency graph",
        "Generating documentation structure",
        "Generating summaries",
        "Generating documentation content",
        "Updating embeddings",
    ]
    positions = [result.output.index(stage) for stage in stage_order]
    assert positions == sorted(positions)
    assert no_bind_server == [("127.0.0.1", 8000)]


def test_index_wiki_is_browsable_over_real_http(tmp_path, cli_home, fake_engines):
    root = _copy_fixture_repo(tmp_path)
    result = run_index(root, config=CLIConfiguration())

    port = 18321
    server_thread = threading.Thread(
        target=cli.server.start_local_server,
        args=(result.vectorIndex, result.embeddingEngine, result.llmEngine, result.docsRoot, "127.0.0.1", port),
        daemon=True,
    )
    server_thread.start()
    try:
        deadline = time.time() + 10
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                with urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
                    body = response.read().decode("utf-8")
                    assert response.status == 200
                    assert "<html" in body.lower()
                    break
            except Exception as exc:  # noqa: BLE001 - server may not be up yet
                last_error = exc
                time.sleep(0.2)
        else:
            raise AssertionError(f"server never became reachable: {last_error}")
    finally:
        result.vectorIndex.close()


def test_run_index_uses_documented_defaults_when_no_config_saved(tmp_path, cli_home, fake_engines):
    root = _copy_fixture_repo(tmp_path)
    assert not cli.config.paths.config_path().exists()

    default_config = cli.config.load_config()
    assert default_config.llmModel == cli.config.DEFAULT_LLM_MODEL

    result = run_index(root, config=default_config)
    assert result.llmEngine.modelName == cli.config.DEFAULT_LLM_MODEL
    result.vectorIndex.close()


def test_run_index_against_empty_repository_completes_without_error(tmp_path, cli_home, fake_engines):
    empty_root = tmp_path / "empty-repo"
    empty_root.mkdir()

    result = run_index(empty_root, config=CLIConfiguration())

    assert result.docsRoot.exists()
    assert (result.docsRoot / "index.html").exists()
    result.vectorIndex.close()


# ---------------------------------------------------------------------------
# US2 - serve
# ---------------------------------------------------------------------------


def test_run_serve_watcher_wired_to_reindex_pipeline(tmp_path, cli_home, fake_engines):
    root = _copy_fixture_repo(tmp_path)
    indexed = run_index(root, config=CLIConfiguration())
    indexed.vectorIndex.close()

    served = run_serve(root, config=CLIConfiguration())
    try:
        assert served.watcher is not None
        assert served.watcher.isRunning()

        beta_path = root / "beta.py"
        beta_path.write_text(
            beta_path.read_text(encoding="utf-8") + "\n\ndef beta_extra(value: int) -> int:\n    return value + 1\n",
            encoding="utf-8",
        )
        batch = ChangeBatch(changes=(FileChange(relative_path="beta.py", change_type=ChangeType.MODIFIED),))

        # Drive the pipeline directly rather than waiting on real filesystem
        # debouncing - this confirms the watcher-to-pipeline wiring itself.
        served.watcher._on_batch(batch)

        bundle = served.watcher._metadata_store.load_repository(root)
        beta_bundle = next(b for b in bundle.files if b.file.path.endswith("beta.py"))
        assert any(f.name == "beta_extra" for f in beta_bundle.functions)
    finally:
        served.watcher.stop()
        served.vectorIndex.close()


def test_run_serve_without_prior_index_raises_index_not_found(tmp_path, cli_home, fake_engines):
    root = _copy_fixture_repo(tmp_path)

    with pytest.raises(IndexNotFoundError):
        run_serve(root, config=CLIConfiguration())


def test_cli_runner_serve_without_prior_index_exits_nonzero_without_starting_server(tmp_path, cli_home, fake_engines, no_bind_server):
    root = _copy_fixture_repo(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli.main.app, ["serve", str(root)])

    assert result.exit_code == 1
    assert "index" in result.output.lower()
    assert no_bind_server == []


# ---------------------------------------------------------------------------
# US3 - config -> index wiring
# ---------------------------------------------------------------------------


def test_cli_runner_config_scenarios(tmp_path, cli_home, fake_engines):
    runner = CliRunner()

    show_result = runner.invoke(cli.main.app, ["config"])
    assert show_result.exit_code == 0
    assert cli.config.DEFAULT_LLM_MODEL in show_result.output

    installed_result = runner.invoke(cli.main.app, ["config", "--llm-model", "test-llm"])
    assert installed_result.exit_code == 0
    assert "Configuration saved." in installed_result.output
    assert "Warning" not in installed_result.output

    not_installed_result = runner.invoke(cli.main.app, ["config", "--embedding-model", "not-installed-model"])
    assert not_installed_result.exit_code == 0
    assert "Warning" in not_installed_result.output
    assert "not-installed-model" in not_installed_result.output

    invalid_endpoint_result = runner.invoke(cli.main.app, ["config", "--llm-endpoint", "https://example.com"])
    assert invalid_endpoint_result.exit_code == 1
    saved = cli.config.load_config()
    assert saved.llmEndpointUrl == "http://localhost:11434"  # unchanged - invalid endpoint was never written


def test_configured_llm_model_is_used_by_a_subsequent_index_run(tmp_path, cli_home, fake_engines):
    runner = CliRunner()
    save_result = runner.invoke(cli.main.app, ["config", "--llm-model", "my-custom-model"])
    assert save_result.exit_code == 0

    root = _copy_fixture_repo(tmp_path)
    config = cli.config.load_config()
    assert config.llmModel == "my-custom-model"

    result = run_index(root, config=config)
    assert result.llmEngine.modelName == "my-custom-model"
    result.vectorIndex.close()


def test_config_before_any_provider_reachable_still_reports_without_failing(tmp_path, cli_home, monkeypatch):
    def unreachable_llm_factory(model_name: str, endpoint_url: str = "http://localhost:11434", **_: object) -> RecordingLLMEngine:
        return RecordingLLMEngine(model_name=model_name, service_reachable=False, model_installed=False)

    def unreachable_embedding_factory(model_name: str = "test-embed", endpoint_url: str = "http://localhost:11434", **_: object) -> FakeEmbeddingEngine:
        return FakeEmbeddingEngine(model_name=model_name, runtime_reachable=False, model_installed=False)

    monkeypatch.setattr(cli.config_command, "create_local_llm_engine", unreachable_llm_factory)
    monkeypatch.setattr(cli.config_command, "create_embedding_engine", unreachable_embedding_factory)

    runner = CliRunner()
    result = runner.invoke(cli.main.app, ["config"])

    assert result.exit_code == 0
    assert "unavailable" in result.output.lower()


# ---------------------------------------------------------------------------
# US4 - actionable errors
# ---------------------------------------------------------------------------


def test_index_on_nonexistent_path_fails_clearly_with_no_side_effects(tmp_path, cli_home, fake_engines):
    runner = CliRunner()
    missing = tmp_path / "does-not-exist"

    result = runner.invoke(cli.main.app, ["index", str(missing)])

    assert result.exit_code == 1
    assert str(missing) in result.output
    assert "does not exist" in result.output
    assert _repo_state_dirs(cli_home) == []
    assert "Traceback" not in result.output


def test_index_and_serve_fail_clearly_when_llm_service_unreachable(tmp_path, cli_home, monkeypatch):
    root = _copy_fixture_repo(tmp_path)
    scan_calls: list[object] = []
    monkeypatch.setattr(cli.index_command, "scan_repository", lambda *a, **k: scan_calls.append(1))

    def unreachable_llm_factory(model_name: str, endpoint_url: str = "http://localhost:11434", **_: object) -> RecordingLLMEngine:
        return RecordingLLMEngine(model_name=model_name, service_reachable=False, model_installed=False)

    for module in (cli.index_command, cli.serve_command):
        monkeypatch.setattr(module, "create_local_llm_engine", unreachable_llm_factory)
        monkeypatch.setattr(module, "create_embedding_engine", lambda *a, **k: FakeEmbeddingEngine())

    runner = CliRunner()

    index_result = runner.invoke(cli.main.app, ["index", str(root)])
    assert index_result.exit_code == 1
    assert "11434" in index_result.output
    assert scan_calls == []

    serve_result = runner.invoke(cli.main.app, ["serve", str(root)])
    assert serve_result.exit_code == 1
    assert "11434" in serve_result.output


def test_index_and_serve_fail_clearly_when_model_not_installed(tmp_path, cli_home, monkeypatch):
    root = _copy_fixture_repo(tmp_path)

    def model_missing_factory(model_name: str, endpoint_url: str = "http://localhost:11434", **_: object) -> RecordingLLMEngine:
        return RecordingLLMEngine(model_name=model_name, service_reachable=True, model_installed=False)

    for module in (cli.index_command, cli.serve_command):
        monkeypatch.setattr(module, "create_local_llm_engine", model_missing_factory)
        monkeypatch.setattr(module, "create_embedding_engine", lambda *a, **k: FakeEmbeddingEngine())

    runner = CliRunner()

    index_result = runner.invoke(cli.main.app, ["index", str(root)])
    assert index_result.exit_code == 1

    serve_result = runner.invoke(cli.main.app, ["serve", str(root)])
    assert serve_result.exit_code == 1

    # Distinctly worded from the service-unreachable case (previous test):
    # names the specific model and says "not installed" rather than the
    # service being down.
    assert "not installed" in index_result.output
    assert "qwen2.5-coder" in index_result.output


def test_serve_bind_failure_reports_actionable_message_not_raw_exception(tmp_path, cli_home, fake_engines, monkeypatch):
    root = _copy_fixture_repo(tmp_path)
    indexed = run_index(root, config=CLIConfiguration())
    indexed.vectorIndex.close()

    def bind_failure(app, *, host, port):
        raise SystemExit(3)

    monkeypatch.setattr(cli.server.uvicorn, "run", bind_failure)

    runner = CliRunner()
    result = runner.invoke(cli.main.app, ["serve", str(root)])

    assert result.exit_code == 1
    assert "127.0.0.1:8000" in result.output
    assert "already be in use" in result.output
    assert "Traceback" not in result.output


def test_none_of_the_failure_scenarios_leak_a_traceback(tmp_path, cli_home, monkeypatch):
    root = _copy_fixture_repo(tmp_path)
    runner = CliRunner()

    scenarios = []

    # Invalid path.
    scenarios.append(runner.invoke(cli.main.app, ["index", str(tmp_path / "missing")]))

    # LLM unreachable.
    def unreachable_llm_factory(model_name: str, endpoint_url: str = "http://localhost:11434", **_: object) -> RecordingLLMEngine:
        return RecordingLLMEngine(model_name=model_name, service_reachable=False, model_installed=False)

    monkeypatch.setattr(cli.index_command, "create_local_llm_engine", unreachable_llm_factory)
    monkeypatch.setattr(cli.index_command, "create_embedding_engine", lambda *a, **k: FakeEmbeddingEngine())
    scenarios.append(runner.invoke(cli.main.app, ["index", str(root)]))

    for result in scenarios:
        assert result.exit_code != 0
        assert "Traceback" not in result.output
