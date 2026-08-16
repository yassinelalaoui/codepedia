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


class _StubEmbeddingEngine:
    def __init__(self, status: EmbeddingAvailabilityStatus) -> None:
        self._status = status
        self.checked = False

    def checkAvailability(self) -> EmbeddingAvailabilityStatus:
        self.checked = True
        return self._status


def test_check_ai_dependencies_passes_when_both_available():
    llm = _StubLLMEngine(AvailabilityStatus(True, True, True, "ok"))
    embedding = _StubEmbeddingEngine(EmbeddingAvailabilityStatus(True, True, True, "ok"))

    check_ai_dependencies(llm, embedding)  # must not raise

    assert llm.checked and embedding.checked


def test_check_ai_dependencies_raises_with_llm_message_and_skips_embedding_check():
    llm = _StubLLMEngine(AvailabilityStatus(False, False, False, "llm service unreachable at http://localhost:11434"))
    embedding = _StubEmbeddingEngine(EmbeddingAvailabilityStatus(True, True, True, "ok"))

    with pytest.raises(LocalModelUnavailableError, match="llm service unreachable"):
        check_ai_dependencies(llm, embedding)

    assert not embedding.checked  # short-circuits once the LLM check already failed


def test_check_ai_dependencies_raises_with_embedding_message_when_llm_is_fine():
    llm = _StubLLMEngine(AvailabilityStatus(True, True, True, "ok"))
    embedding = _StubEmbeddingEngine(EmbeddingAvailabilityStatus(False, True, False, "embedding model not installed"))

    with pytest.raises(LocalModelUnavailableError, match="embedding model not installed"):
        check_ai_dependencies(llm, embedding)


def test_version_flag_prints_the_installed_package_version_and_exits_zero():
    runner = CliRunner()

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == importlib.metadata.version("repo-scanner")
