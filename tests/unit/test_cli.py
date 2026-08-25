"""Unit tests for `cli.config`, `cli.paths`, `cli.availability`, and the
`--version` flag (specs/019-cli-orchestrator, specs/020-cli-packaging)."""

from __future__ import annotations

import importlib.metadata

import pytest
from typer.testing import CliRunner

import cli.config
import cli.paths
from cli.availability import check_ai_dependencies
from cli.config import CLIConfiguration, load_config, save_config
from cli.errors import LocalModelUnavailableError
from cli.main import app
from embedding_engine.models import EmbeddingAvailabilityStatus
from local_llm.models import AvailabilityStatus


@pytest.fixture()
def cli_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(cli.paths, "repo_scanner_home", lambda: home)
    return home


def test_load_config_returns_documented_defaults_when_no_file_exists(cli_home):
    assert not cli.paths.config_path().exists()

    config = load_config()

    assert config == CLIConfiguration()
    assert config.llmModel == cli.config.DEFAULT_LLM_MODEL


def test_save_then_load_round_trips_the_same_values(cli_home):
    original = CLIConfiguration(
        llmModel="my-model",
        llmEndpointUrl="http://localhost:11434",
        embeddingModel="my-embed-model",
        embeddingEndpointUrl="http://127.0.0.1:11434",
    )

    save_config(original)
    loaded = load_config()

    assert loaded == original
    assert cli.paths.config_path().exists()


def test_save_config_rejects_invalid_endpoint_before_writing_anything(cli_home):
    invalid = CLIConfiguration(llmEndpointUrl="https://not-local.example.com")

    with pytest.raises(ValueError):
        save_config(invalid)

    assert not cli.paths.config_path().exists()


def test_llm_generate_timeout_defaults_and_round_trips(cli_home):
    """Regression test: the LLM generation timeout used to be a hardcoded
    5-second constant shared with the (much faster) availability check,
    with no way for a user whose local model is genuinely slower than that
    to configure it. It's now its own field, defaulting to a more realistic
    120s, and configurable via `repo-scanner config --llm-generate-timeout`."""
    default = load_config()
    assert default.llmGenerateTimeout == 120.0

    save_config(CLIConfiguration(llmGenerateTimeout=300.0))
    reloaded = load_config()

    assert reloaded.llmGenerateTimeout == 300.0


def test_save_config_rejects_non_positive_generate_timeout(cli_home):
    with pytest.raises(ValueError):
        save_config(CLIConfiguration(llmGenerateTimeout=0))

    assert not cli.paths.config_path().exists()


def test_chain_fields_round_trip_through_save_and_load(cli_home):
    original = CLIConfiguration(
        embeddingChain=("local:nomic-embed-text",),
        summaryChain=("groq:llama-3.3-70b-versatile", "local:qwen2.5-coder"),
        chatChain=("groq:llama-3.3-70b-versatile",),
        disclosureAcknowledgedSignature="abc123",
    )

    save_config(original)
    loaded = load_config()

    assert loaded == original


def test_config_file_predating_this_feature_loads_with_remote_defaults(cli_home):
    cli.paths.config_path().parent.mkdir(parents=True, exist_ok=True)
    cli.paths.config_path().write_text(
        '{"llmModel": "qwen2.5-coder", "llmEndpointUrl": "http://localhost:11434"}', encoding="utf-8"
    )

    loaded = load_config()

    assert loaded.embeddingChain == cli.config.DEFAULT_EMBEDDING_CHAIN
    assert loaded.summaryChain == cli.config.DEFAULT_SUMMARY_CHAIN
    assert loaded.chatChain == cli.config.DEFAULT_CHAT_CHAIN
    assert loaded.llmModel == "qwen2.5-coder"


def test_save_config_rejects_empty_chain(cli_home):
    with pytest.raises(ValueError):
        save_config(CLIConfiguration(summaryChain=()))

    assert not cli.paths.config_path().exists()


def test_save_config_rejects_unparseable_chain_entry(cli_home):
    with pytest.raises(ValueError):
        save_config(CLIConfiguration(chatChain=("not-a-valid-entry",)))

    assert not cli.paths.config_path().exists()


def test_llm_provider_and_remote_llm_model_are_no_longer_accepted_fields():
    import dataclasses

    field_names = {field.name for field in dataclasses.fields(CLIConfiguration)}
    assert "llmProvider" not in field_names
    assert "remoteLlmModel" not in field_names


def test_state_id_is_stable_and_filesystem_safe(tmp_path):
    root = tmp_path / "some-repo"
    first = cli.paths.state_id(root)
    second = cli.paths.state_id(root)

    assert first == second
    assert len(first) == 16
    assert all(ch in "0123456789abcdef" for ch in first)


def test_state_id_differs_per_repository_path(tmp_path):
    first = cli.paths.state_id(tmp_path / "repo-a")
    second = cli.paths.state_id(tmp_path / "repo-b")

    assert first != second


def test_repo_state_dir_is_scoped_under_repo_scanner_home(tmp_path, monkeypatch):
    home = tmp_path / "custom-home"
    monkeypatch.setattr(cli.paths, "repo_scanner_home", lambda: home)

    state_dir = cli.paths.repo_state_dir(tmp_path / "some-repo")

    assert state_dir.parent.parent == home
    assert state_dir.parent.name == "repos"


class _StubLLMEngine:
    def __init__(self, status: AvailabilityStatus) -> None:
        self._status = status
        self.checked = False

    def checkAvailability(self) -> AvailabilityStatus:
        self.checked = True
        return self._status

    def isAvailable(self) -> bool:
        self.checked = True
        return self._status.available


class _StubEmbeddingEngine:
    def __init__(self, status: EmbeddingAvailabilityStatus) -> None:
        self._status = status
        self.checked = False

    def checkAvailability(self) -> EmbeddingAvailabilityStatus:
        self.checked = True
        return self._status

    def isAvailable(self) -> bool:
        self.checked = True
        return self._status.available


def test_check_ai_dependencies_passes_when_both_available():
    llm = _StubLLMEngine(AvailabilityStatus(True, True, True, "ok"))
    embedding = _StubEmbeddingEngine(EmbeddingAvailabilityStatus(True, True, True, "ok"))

    check_ai_dependencies(summary=llm, embeddings=embedding)  # must not raise

    assert llm.checked and embedding.checked


def test_check_ai_dependencies_raises_naming_the_stage_and_skips_later_checks():
    llm = _StubLLMEngine(AvailabilityStatus(False, False, False, "llm service unreachable at http://localhost:11434"))
    embedding = _StubEmbeddingEngine(EmbeddingAvailabilityStatus(True, True, True, "ok"))

    with pytest.raises(LocalModelUnavailableError, match="summary"):
        check_ai_dependencies(summary=llm, embeddings=embedding)

    assert not embedding.checked  # short-circuits once the summary check already failed


def test_check_ai_dependencies_raises_with_embedding_message_when_llm_is_fine():
    llm = _StubLLMEngine(AvailabilityStatus(True, True, True, "ok"))
    embedding = _StubEmbeddingEngine(EmbeddingAvailabilityStatus(False, True, False, "embedding model not installed"))

    with pytest.raises(LocalModelUnavailableError, match="embeddings"):
        check_ai_dependencies(summary=llm, embeddings=embedding)


def test_version_flag_prints_the_installed_package_version_and_exits_zero():
    runner = CliRunner()

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == importlib.metadata.version("repo-scanner")
