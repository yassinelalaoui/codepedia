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
    # llmProvider/remoteLlmModel (026) were removed when 029 introduced
    # provider chains, and the chains themselves went at constitution v4.0.0.
    # `config` is the whole provider interface again.
    assert "llm_provider" not in parameters
    assert "remote_llm_model" not in parameters


@pytest.fixture()
def cli_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(cli.paths, "codepedia_home", lambda: home)
    return home


def test_the_provider_command_group_is_gone(cli_home):
    """`codepedia provider ...` configured chains that no longer exist.

    Every stage runs one local model (constitution 2.1/2.3 v4.0.0), named by
    `codepedia config`, so there is nothing for this group to set.
    """
    runner = CliRunner()

    result = runner.invoke(app, ["provider", "mode", "full-local"])

    assert result.exit_code != 0
    assert "No such command" in result.output


def test_config_sets_both_stage_models(cli_home):
    runner = CliRunner()

    result = runner.invoke(app, ["config", "--llm-model", "my-llm", "--embedding-model", "my-embed"])

    assert result.exit_code == 0, result.output
    assert "my-llm" in result.output
    assert "my-embed" in result.output


def test_version_flag_output_is_a_bare_version_string_matching_the_package():
    runner = CliRunner()

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    output = result.output.strip()
    assert output == importlib.metadata.version("codepedia")
    # contracts/packaging-interface.md: "prints the installed codepedia
    # version ... and exits" - nothing else on the line.
    assert re.fullmatch(r"[0-9][0-9A-Za-z.+\-]*", output)
