"""`codepedia home` (contracts/home-command.md).

The command's own contract: no positional argument, loopback by default, a port
that does not collide with `serve`, a token in the printed URL, and the
entry-point wiring applying to it as it does to every other entry
point.
"""

from __future__ import annotations

import inspect

import pytest
from typer.testing import CliRunner

import cli.main
from cli import paths as cli_paths
from cli.home_command import startup_lines
from cli.main import DEFAULT_HOME_PORT, DEFAULT_HOST, app


@pytest.fixture()
def cli_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: home)
    monkeypatch.setattr(cli.config.paths, "codepedia_home", lambda: home)
    return home


def test_home_is_registered_as_a_command():
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "home" in result.output


def test_home_takes_no_positional_argument():
    """The point of the command: it is the entry point you reach for when you
    do not yet have a repository in mind (spec FR-001)."""
    parameters = inspect.signature(cli.main.home).parameters

    assert set(parameters) == {"host", "port"}


def test_defaults_are_loopback_and_a_port_that_does_not_clash_with_serve():
    parameters = inspect.signature(cli.main.home).parameters

    assert parameters["host"].default.default == DEFAULT_HOST == "127.0.0.1"
    assert parameters["port"].default.default == DEFAULT_HOME_PORT == 8100
    # Constitution 2.2, and no collision with a directly-run `serve` on 8000.
    assert DEFAULT_HOME_PORT != cli.main.DEFAULT_PORT


def test_there_is_no_disclosure_gate_to_be_behind():
    """Constitution 2.1 v4.0.0: nothing leaves the machine, so nothing is
    disclosed. The gate the hub used to sit behind was removed with the remote
    providers it warned about, and no entry point may reintroduce one
    silently."""
    assert not hasattr(cli.main, "_DISCLOSURE_GATED_COMMANDS")


# -- what it prints ---------------------------------------------------------


def test_startup_lines_carry_the_token_in_the_url():
    lines = startup_lines("127.0.0.1", 8100, "s3cr3t")

    assert "http://127.0.0.1:8100/?token=s3cr3t" in lines[0]


def test_startup_lines_say_what_the_token_authorises():
    """It authorises more than the wiki's does - starting a long-running
    analysis of any path, and deleting stored analyses - so it says so."""
    lines = startup_lines("127.0.0.1", 8100, "s3cr3t")

    assert "Keep that URL private" in lines[1]
    assert "starting and removing analyses" in lines[1]


def test_a_loopback_bind_prints_no_warning():
    assert len(startup_lines("127.0.0.1", 8100, "t")) == 2
    assert len(startup_lines("localhost", 8100, "t")) == 2


def test_a_non_loopback_bind_warns_that_it_is_reachable():
    """Constitution 2.2: leaving the machine takes an explicit action, and that
    action is called out when taken."""
    lines = startup_lines("0.0.0.0", 8100, "t")

    assert len(lines) == 3
    assert "WARNING" in lines[2]
    assert "reachable from other machines" in lines[2]


def test_a_bind_failure_is_reported_cleanly_rather_than_as_a_traceback(cli_home, monkeypatch):
    """uvicorn calls `sys.exit` on a bind failure instead of letting the OSError
    out - the same quirk `cli/server.py` documents."""
    import cli.home_command as home_command
    from cli.errors import ServerBindError

    def fake_run(app, *, host, port):
        raise SystemExit(3)

    monkeypatch.setattr(home_command.uvicorn, "run", fake_run)

    with pytest.raises(ServerBindError) as caught:
        home_command.run_home("127.0.0.1", 8100)

    assert "may already be in use" in str(caught.value)


def test_starting_sweeps_interrupted_runs_before_serving(cli_home, monkeypatch):
    """Spec FR-026d: a run whose hub died must not read as still in progress."""
    from hub_server.run_log import RunLog

    log = RunLog()
    log.append(run_id="orphan", repository_path="C:/repo", kind="index")

    import cli.home_command as home_command

    monkeypatch.setattr(home_command.uvicorn, "run", lambda app, *, host, port: None)
    home_command.run_home("127.0.0.1", 8100)

    assert RunLog().recent()[0].outcome == "interrupted"
