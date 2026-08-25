"""Verifies the `index`/`serve`/`config`/`scan` command surface matches
`specs/019-cli-orchestrator/contracts/cli-interface.md`, and the `--version`
flag matches `specs/020-cli-packaging/contracts/packaging-interface.md`."""

from __future__ import annotations

import importlib.metadata
import inspect
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cli.paths
from cli.main import app


def _command(name: str):
    for cmd in app.registered_commands:
        if cmd.name == name:
            return cmd
    raise AssertionError(f"no '{name}' command registered on cli.main.app")


def _param_default(callback, name: str):
    parameters = inspect.signature(callback).parameters
    default = parameters[name].default
    return getattr(default, "default", default)


def test_scan_command_unchanged_from_spec_001():
    cmd = _command("scan")
    parameters = inspect.signature(cmd.callback).parameters
    assert "repo_path" in parameters
    # `from __future__ import annotations` makes this a postponed (string) annotation.
    assert parameters["repo_path"].annotation in (Path, "Path")


def test_index_command_accepts_path_host_port_with_documented_defaults():
    cmd = _command("index")
    assert _param_default(cmd.callback, "path") == Path(".")
    assert _param_default(cmd.callback, "host") == "127.0.0.1"
    assert _param_default(cmd.callback, "port") == 8000


def test_serve_command_has_same_path_host_port_shape_as_index():
    cmd = _command("serve")
    assert _param_default(cmd.callback, "path") == Path(".")
    assert _param_default(cmd.callback, "host") == "127.0.0.1"
    assert _param_default(cmd.callback, "port") == 8000


def test_config_command_accepts_optional_model_endpoint_and_show_flags():
    cmd = _command("config")
    parameters = inspect.signature(cmd.callback).parameters
    for name in ("llm_model", "llm_endpoint", "embedding_model", "embedding_endpoint"):
        assert _param_default(cmd.callback, name) is None
    assert _param_default(cmd.callback, "show") is False
    # llmProvider/remoteLlmModel (026) were removed - superseded entirely by
    # `provider chain set`/`provider mode full-local` (029).
    assert "llm_provider" not in parameters
    assert "remote_llm_model" not in parameters


@pytest.fixture()
def cli_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(cli.paths, "repo_scanner_home", lambda: home)
    return home


def test_provider_mode_full_local_switches_all_three_chains(cli_home):
    runner = CliRunner()

    # Two confirmations expected: the main callback's gate (fresh install,
    # signature never acknowledged) and `run_provider_mode_full_local`'s own
    # immediate re-check against the just-saved all-local configuration
    # (research.md §13's M1 fix).
    result = runner.invoke(app, ["provider", "mode", "full-local"], input="y\ny\n")

    assert result.exit_code == 0, result.output
    assert "local:nomic-embed-text" in result.output
    assert "local:qwen2.5-coder" in result.output


def test_provider_chain_set_replaces_one_stage_only(cli_home):
    runner = CliRunner()

    result = runner.invoke(app, ["provider", "chain", "set", "chat", "groq:llama-3.3-70b-versatile"], input="y\ny\n")

    assert result.exit_code == 0, result.output
    assert "groq:llama-3.3-70b-versatile" in result.output


def test_provider_chain_set_rejects_unknown_stage(cli_home):
    runner = CliRunner()

    result = runner.invoke(app, ["provider", "chain", "set", "bogus", "groq:llama-3.3-70b-versatile"], input="y\ny\n")

    assert result.exit_code != 0


def test_version_flag_output_is_a_bare_version_string_matching_the_package():
    runner = CliRunner()

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    output = result.output.strip()
    assert output == importlib.metadata.version("repo-scanner")
    # contracts/packaging-interface.md: "prints the installed repo-scanner
    # version ... and exits" - nothing else on the line.
    assert re.fullmatch(r"[0-9][0-9A-Za-z.+\-]*", output)
