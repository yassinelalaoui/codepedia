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
import cli.disclosure
import cli.index_command
import cli.main
import cli.serve_command
import cli.server
import provider_routing.factory
from cli.config import CLIConfiguration
from cli.errors import IndexNotFoundError, LocalModelUnavailableError, RepositoryNotFoundError, ServerBindError
from cli.index_command import run_index
from cli.serve_command import run_serve
from embedding_engine.models import EmbeddingAvailabilityStatus
from local_llm import GenerationFailedError, PromptEnvelope
from local_llm.models import AvailabilityStatus
from repo_watcher import ChangeBatch, ChangeType, FileChange


def _local_config(**overrides: object) -> CLIConfiguration:
    """A `CLIConfiguration` routing all three stages through `local:` chain
    entries matching `fake_engines`' test doubles (spec 029 changed the
    fresh-install defaults to remote providers - these tests exercise the
    CLI orchestration itself, not real/fake remote providers, so they pin
    local chains explicitly). Already disclosure-acknowledged for its own
    signature, so a `CliRunner` invocation isn't blocked by the gate."""
    defaults: dict[str, object] = dict(
        embeddingChain=("local:test-embed",),
        summaryChain=("local:test-llm",),
        chatChain=("local:test-llm",),
    )
    defaults.update(overrides)
    base = CLIConfiguration(**defaults)
    return CLIConfiguration(**{**base.to_dict(), "disclosureAcknowledgedSignature": cli.config.disclosure_signature(base)})


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
        generate_timeout: float = 120.0,
    ) -> None:
        self.modelName = model_name
        self.endpointUrl = endpoint_url
        self.service_reachable = service_reachable
        self.model_installed = model_installed
        self._installed_models = installed_models
        self.generateTimeout = generate_timeout
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

    def isAvailable(self) -> bool:
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

    def isAvailable(self) -> bool:
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
def fake_engines(cli_home, monkeypatch):
    """Patch every module that constructs local engines to return
    lightweight, in-memory test doubles instead of real Ollama-backed ones,
    and seed `cli_home`'s config file with an already-acknowledged, all-local
    chain configuration (spec 029's fresh-install defaults are remote - a
    plain CLI invocation with no prior config would otherwise route through
    real Groq/OpenAI factories these doubles don't intercept, and would
    block on the disclosure gate).

    The doubles report a model as installed only if it's in
    `INSTALLED_LLM_MODELS`/`INSTALLED_EMBEDDING_MODELS`, so `config`'s
    not-installed warning (spec US3) has something real to detect.
    """

    def llm_factory(
        model_name: str, endpoint_url: str = "http://localhost:11434", *, generate_timeout: float = 120.0, **_: object
    ) -> RecordingLLMEngine:
        return RecordingLLMEngine(
            model_name=model_name,
            endpoint_url=endpoint_url,
            model_installed=model_name in INSTALLED_LLM_MODELS,
            installed_models=INSTALLED_LLM_MODELS,
            generate_timeout=generate_timeout,
        )

    def embedding_factory(model_name: str = "test-embed", endpoint_url: str = "http://localhost:11434", **_: object) -> FakeEmbeddingEngine:
        return FakeEmbeddingEngine(
            model_name=model_name,
            endpoint_url=endpoint_url,
            model_installed=model_name in INSTALLED_EMBEDDING_MODELS,
            installed_models=INSTALLED_EMBEDDING_MODELS,
        )

    for module in (cli.config_command, provider_routing.factory):
        monkeypatch.setattr(module, "create_local_llm_engine", llm_factory)
        monkeypatch.setattr(module, "create_embedding_engine", embedding_factory)

    cli.config.save_config(_local_config())

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
    result = run_index(root, config=_local_config())

    state_dirs = _repo_state_dirs(cli_home)
    assert len(state_dirs) == 1
    state_dir = state_dirs[0]

    assert (state_dir / "repository-metadata.sqlite").exists()
    assert (state_dir / "dependency-graph.sqlite").exists()
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

    first = run_index(root, config=_local_config())
    first.vectorIndex.close()
    first_state_dirs = _repo_state_dirs(cli_home)
    assert len(first_state_dirs) == 1

    # Modify a file so the second run has something new to pick up.
    (root / "beta.py").write_text((root / "beta.py").read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")

    second = run_index(root, config=_local_config())
    second_state_dirs = _repo_state_dirs(cli_home)
    assert len(second_state_dirs) == 1
    assert second_state_dirs[0] == first_state_dirs[0]  # same state dir, replaced in place
    assert not list(cli_home.glob("repos/*.staging-*"))
    assert watcher_calls == []  # index is always a full run, never incremental
    second.vectorIndex.close()


def test_run_index_failure_on_rerun_leaves_prior_successful_state_untouched(tmp_path, cli_home, fake_engines, monkeypatch):
    root = _copy_fixture_repo(tmp_path)

    first = run_index(root, config=_local_config())
    first.vectorIndex.close()
    state_dir = _repo_state_dirs(cli_home)[0]
    before_files = {p: p.read_bytes() for p in state_dir.rglob("*") if p.is_file()}

    def failing_summarize(self, *args, **kwargs):
        raise RuntimeError("simulated local LLM crash mid-run")

    monkeypatch.setattr(cli.index_command.CodeSummaryPipeline, "summarizeRepository", failing_summarize)

    with pytest.raises(RuntimeError, match="simulated local LLM crash"):
        run_index(root, config=_local_config())

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
    result = run_index(root, config=_local_config())

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


def test_run_index_uses_documented_defaults_when_no_config_saved(cli_home):
    assert not cli.config.paths.config_path().exists()

    default_config = cli.config.load_config()

    # spec 029: a fresh install's documented defaults are the named remote
    # chains, not a local model - full-local is opt-in via `provider mode
    # full-local`. `llmModel` (a `local:` chain entry's connection setting)
    # keeps its own separate local-oriented default regardless.
    assert default_config.llmModel == cli.config.DEFAULT_LLM_MODEL
    assert default_config.embeddingChain == cli.config.DEFAULT_EMBEDDING_CHAIN
    assert default_config.summaryChain == cli.config.DEFAULT_SUMMARY_CHAIN
    assert default_config.chatChain == cli.config.DEFAULT_CHAT_CHAIN


def test_run_index_against_empty_repository_completes_without_error(tmp_path, cli_home, fake_engines):
    empty_root = tmp_path / "empty-repo"
    empty_root.mkdir()

    result = run_index(empty_root, config=_local_config())

    assert result.docsRoot.exists()
    assert (result.docsRoot / "index.html").exists()
    result.vectorIndex.close()


# ---------------------------------------------------------------------------
# US2 - serve
# ---------------------------------------------------------------------------


def test_run_serve_watcher_wired_to_reindex_pipeline(tmp_path, cli_home, fake_engines):
    root = _copy_fixture_repo(tmp_path)
    indexed = run_index(root, config=_local_config())
    indexed.vectorIndex.close()

    served = run_serve(root, config=_local_config())
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
        run_serve(root, config=_local_config())


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


def test_configured_summary_chain_is_used_by_a_subsequent_index_run(tmp_path, cli_home, fake_engines):
    """The model a `local:` summary chain entry uses now comes from the
    chain entry itself (`provider chain set summary local:<model>`), not
    `config --llm-model` (research.md §10 - that field only supplies
    connection settings for whichever `local:` entry is configured)."""
    runner = CliRunner()
    save_result = runner.invoke(
        cli.main.app, ["provider", "chain", "set", "summary", "local:my-custom-model"], input="y\n"
    )
    assert save_result.exit_code == 0, save_result.output

    root = _copy_fixture_repo(tmp_path)
    config = cli.config.load_config()
    assert config.summaryChain == ("local:my-custom-model",)

    result = run_index(root, config=config)
    ref, engine = result.llmEngine.chain[0]
    assert str(ref) == "local:my-custom-model"
    assert engine.modelName == "my-custom-model"


def test_configured_llm_generate_timeout_is_shown_and_used_by_a_subsequent_index_run(tmp_path, cli_home, fake_engines):
    """Regression test: the generation timeout used to be a hardcoded
    constant with no `config` knob at all - a user whose local model
    genuinely needs longer than the default had no way to raise it short of
    editing source. `--llm-generate-timeout` closes that gap."""
    runner = CliRunner()

    show_result = runner.invoke(cli.main.app, ["config"])
    assert show_result.exit_code == 0
    assert "120" in show_result.output  # documented default (research.md)

    save_result = runner.invoke(cli.main.app, ["config", "--llm-generate-timeout", "300"])
    assert save_result.exit_code == 0
    assert "300" in save_result.output

    root = _copy_fixture_repo(tmp_path)
    config = cli.config.load_config()
    assert config.llmGenerateTimeout == 300.0

    result = run_index(root, config=config)
    _ref, engine = result.llmEngine.chain[0]
    assert engine.generateTimeout == 300.0
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
    cli.config.save_config(_local_config())

    def unreachable_llm_factory(model_name: str, endpoint_url: str = "http://localhost:11434", **_: object) -> RecordingLLMEngine:
        return RecordingLLMEngine(model_name=model_name, service_reachable=False, model_installed=False)

    monkeypatch.setattr(provider_routing.factory, "create_local_llm_engine", unreachable_llm_factory)
    monkeypatch.setattr(provider_routing.factory, "create_embedding_engine", lambda *a, **k: FakeEmbeddingEngine())

    runner = CliRunner()

    index_result = runner.invoke(cli.main.app, ["index", str(root)])
    assert index_result.exit_code == 1
    assert "summary" in index_result.output
    assert scan_calls == []

    serve_result = runner.invoke(cli.main.app, ["serve", str(root)])
    assert serve_result.exit_code == 1
    assert "summary" in serve_result.output


def test_index_and_serve_fail_clearly_when_model_not_installed(tmp_path, cli_home, monkeypatch):
    root = _copy_fixture_repo(tmp_path)
    cli.config.save_config(_local_config())

    def model_missing_factory(model_name: str, endpoint_url: str = "http://localhost:11434", **_: object) -> RecordingLLMEngine:
        return RecordingLLMEngine(model_name=model_name, service_reachable=True, model_installed=False)

    monkeypatch.setattr(provider_routing.factory, "create_local_llm_engine", model_missing_factory)
    monkeypatch.setattr(provider_routing.factory, "create_embedding_engine", lambda *a, **k: FakeEmbeddingEngine())

    runner = CliRunner()

    index_result = runner.invoke(cli.main.app, ["index", str(root)])
    assert index_result.exit_code == 1

    serve_result = runner.invoke(cli.main.app, ["serve", str(root)])
    assert serve_result.exit_code == 1

    # check_ai_dependencies (spec 029's C1 fix) now names the unavailable
    # *stage* - a multi-provider chain has no single engine's specific
    # status message to surface faithfully at the pre-flight check.
    assert "summary" in index_result.output


def test_index_fails_clearly_when_generation_times_out_mid_run(tmp_path, cli_home, fake_engines, monkeypatch):
    """Regression test: the pre-flight availability check passes (service
    reachable, model installed), but real summary generation deep inside the
    run raises GenerationFailedError (e.g. a slow local model timing out).
    That must still reach the terminal as a clean, actionable message via
    report_and_exit - this used to crash with a raw traceback because
    `index`/`serve` only caught the upfront availability-check error type,
    not failures from the generation calls made during summarization."""
    root = _copy_fixture_repo(tmp_path)

    def timed_out_summarize(self, *args, **kwargs):
        raise GenerationFailedError(
            "Local LLM at http://localhost:11434 did not respond within 120s "
            "while generating with model 'test-llm'.",
            endpointUrl="http://localhost:11434",
            modelName="test-llm",
        )

    monkeypatch.setattr(cli.index_command.CodeSummaryPipeline, "summarizeRepository", timed_out_summarize)

    runner = CliRunner()
    result = runner.invoke(cli.main.app, ["index", str(root)])

    assert result.exit_code == 1
    assert "did not respond within 120s" in result.output
    assert "Traceback" not in result.output


def test_serve_bind_failure_reports_actionable_message_not_raw_exception(tmp_path, cli_home, fake_engines, monkeypatch):
    root = _copy_fixture_repo(tmp_path)
    indexed = run_index(root, config=_local_config())
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


def test_none_of_the_failure_scenarios_leak_a_traceback(tmp_path, cli_home, fake_engines, monkeypatch):
    root = _copy_fixture_repo(tmp_path)
    runner = CliRunner()

    scenarios = []

    # Invalid path.
    scenarios.append(runner.invoke(cli.main.app, ["index", str(tmp_path / "missing")]))

    # LLM unreachable.
    def unreachable_llm_factory(model_name: str, endpoint_url: str = "http://localhost:11434", **_: object) -> RecordingLLMEngine:
        return RecordingLLMEngine(model_name=model_name, service_reachable=False, model_installed=False)

    monkeypatch.setattr(provider_routing.factory, "create_local_llm_engine", unreachable_llm_factory)
    monkeypatch.setattr(provider_routing.factory, "create_embedding_engine", lambda *a, **k: FakeEmbeddingEngine())
    scenarios.append(runner.invoke(cli.main.app, ["index", str(root)]))

    # Generation fails mid-run (after the availability check already passed).
    monkeypatch.setattr(provider_routing.factory, "create_local_llm_engine", fake_engines[0])
    monkeypatch.setattr(provider_routing.factory, "create_embedding_engine", fake_engines[1])

    def timed_out_summarize(self, *args, **kwargs):
        raise GenerationFailedError(
            "Local LLM did not respond within 120s.", endpointUrl="http://localhost:11434", modelName="test-llm"
        )

    monkeypatch.setattr(cli.index_command.CodeSummaryPipeline, "summarizeRepository", timed_out_summarize)
    scenarios.append(runner.invoke(cli.main.app, ["index", str(root)]))

    for result in scenarios:
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# Disclosure gate (spec 029: FR-012/FR-013)
# ---------------------------------------------------------------------------


def test_index_shows_disclosure_naming_default_providers_and_blocks_until_acknowledged(tmp_path, cli_home):
    """A fresh install (no prior config) shows the blocking disclosure before
    any engine is touched, naming the exact default providers and the
    full-local opt-out (spec FR-012/FR-013)."""
    root = _copy_fixture_repo(tmp_path)
    runner = CliRunner()

    declined = runner.invoke(cli.main.app, ["index", str(root)], input="n\n")

    assert declined.exit_code != 0
    assert "openai:text-embedding-3-small" in declined.output
    assert "groq:llama-3.3-70b-versatile" in declined.output
    assert "provider mode full-local" in declined.output
    assert _repo_state_dirs(cli_home) == []


def test_index_does_not_reshow_disclosure_once_acknowledged(tmp_path, cli_home, fake_engines, no_bind_server):
    """`fake_engines` already seeds an acknowledged local configuration -
    the CLI-runner invocations throughout this file only succeed without
    feeding any confirmation input because the signature already matches
    (SC-006's "only shown at meaningful configuration moments")."""
    root = _copy_fixture_repo(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli.main.app, ["index", str(root)])

    assert result.exit_code == 0, result.output
    assert "Continue with this configuration?" not in result.output
