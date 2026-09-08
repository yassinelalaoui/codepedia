"""Supervising a child process (research.md §7, §8).

Two properties here are the ones that would fail catastrophically and quietly:

- A child that prints a lot must not deadlock. An undrained pipe fills and the
  child blocks on its next write - a served wiki would simply stop answering,
  with no error anywhere.
- A terminated child's staging directory must be removed by the hub, because
  `TerminateProcess` does not run `run_index`'s own cleanup handler.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from cli import paths as cli_paths
from cli.progress_stream import SENTINEL
from hub_server import children

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def hub_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".codepedia"
    (home / "repos").mkdir(parents=True)
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: home)
    return home


def launch_python(script: str, **kwargs):
    """Launch a bare interpreter running `script`, drained exactly as the hub
    drains a real child."""
    events = kwargs.pop("events", [])
    lines = kwargs.pop("lines", [])
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    child = children.ChildProcess(
        kind="index",
        repositoryPath=str(REPO_ROOT),
        process=process,
        onEvent=events.append,
        onLine=lines.append,
    )
    child.start_reader()
    return child, events, lines


def test_a_chatty_child_does_not_deadlock():
    """Far more than a pipe buffer's worth of output. Without a reader thread
    draining continuously, this hangs forever."""
    script = "for i in range(20000): print('x' * 100)"
    lines: list[str] = []

    child, _, lines = launch_python(script, lines=lines)
    code = child.process.wait(timeout=60)

    assert code == 0, "the child deadlocked on a full stdout pipe"


def test_events_and_ordinary_output_are_separated():
    """Spec FR-016: everything that is not an event still reaches the terminal."""
    payload = json.dumps({"seq": 1, "type": "stage", "stage": "SCANNING", "label": "Scanning repository"})
    script = (
        "print('Scanning repository')\n"
        f"print({SENTINEL!r} + ' ' + {payload!r})\n"
        "print('  [1/2] function alpha')\n"
    )
    events: list = []
    lines: list[str] = []

    child, events, lines = launch_python(script, events=events, lines=lines)
    child.process.wait(timeout=30)
    time.sleep(0.3)

    assert [event.type for event in events] == ["stage"]
    # The human-readable lines survive untouched, sentinel lines excluded.
    assert "Scanning repository" in lines
    assert "  [1/2] function alpha" in lines
    assert not any(line.startswith(SENTINEL) for line in lines)


def test_a_malformed_event_line_does_not_stop_the_drain():
    """Reader obligation 3: degradation is "the page shows less", never a hang."""
    script = (
        f"print({SENTINEL!r} + ' not json')\n"
        "print('still running')\n"
        f"print({SENTINEL!r} + ' ' + '{{\"seq\": 2, \"type\": \"stage\", \"stage\": \"PARSING\"}}')\n"
    )
    events: list = []
    lines: list[str] = []

    child, events, lines = launch_python(script, events=events, lines=lines)
    child.process.wait(timeout=30)
    time.sleep(0.3)

    assert "still running" in lines
    assert [event.type for event in events] == ["stage"]


def test_undecodable_bytes_do_not_kill_the_reader():
    """Reader obligation 5: a repository path can carry anything, and a decode
    error must not take the child down with it."""
    script = (
        "import sys\n"
        "sys.stdout.buffer.write(b'\\xff\\xfe broken bytes\\n')\n"
        "sys.stdout.buffer.flush()\n"
        "print('after the bad bytes')\n"
    )
    lines: list[str] = []

    child, _, lines = launch_python(script, lines=lines)
    child.process.wait(timeout=30)
    time.sleep(0.3)

    assert "after the bad bytes" in lines


def test_terminate_stops_a_child_that_would_otherwise_run_forever():
    child, _, _ = launch_python("import time\nwhile True: time.sleep(0.1)")

    child.terminate()

    assert child.process.poll() is not None
    assert not child.is_running()


# -- staging cleanup --------------------------------------------------------


def test_the_staging_directory_of_a_killed_child_is_removed(hub_home, tmp_path):
    """Spec FR-012a: `TerminateProcess` does not run the pipeline's own
    `except` cleanup, so the hub has to do it."""
    repository = tmp_path / "project"
    repository.mkdir()
    state_dir = cli_paths.repo_state_dir(repository)
    staging = state_dir.parent / f"{state_dir.name}.staging-4242"
    staging.mkdir(parents=True)
    (staging / "docs").mkdir()

    assert children.discard_staging(str(repository), 4242) is True
    assert not staging.exists()


def test_cleanup_never_touches_residue_it_did_not_create(hub_home, tmp_path):
    """Explicitly out of scope, and deleting a directory belonging to another
    process's live run would be a real bug."""
    repository = tmp_path / "project"
    repository.mkdir()
    state_dir = cli_paths.repo_state_dir(repository)
    mine = state_dir.parent / f"{state_dir.name}.staging-4242"
    someone_elses = state_dir.parent / f"{state_dir.name}.staging-9999"
    for directory in (mine, someone_elses):
        directory.mkdir(parents=True)

    children.discard_staging(str(repository), 4242)

    assert not mine.exists()
    assert someone_elses.exists(), "cleanup reached beyond its own child's directory"


def test_cleanup_of_a_child_that_left_nothing_behind_is_harmless(hub_home, tmp_path):
    repository = tmp_path / "project"
    repository.mkdir()

    assert children.discard_staging(str(repository), 4242) is False


def test_the_final_state_directory_is_never_mistaken_for_staging(hub_home, tmp_path):
    """The name is `<state_id>.staging-<pid>`; the real one is `<state_id>`.
    Confusing them would delete a successful analysis."""
    repository = tmp_path / "project"
    repository.mkdir()
    state_dir = cli_paths.repo_state_dir(repository)
    state_dir.mkdir(parents=True)
    (state_dir / "docs").mkdir()

    children.discard_staging(str(repository), 4242)

    assert state_dir.exists()
    assert (state_dir / "docs").exists()


# -- ports ------------------------------------------------------------------


def test_free_port_returns_a_usable_loopback_port():
    port = children.free_port()

    assert 1024 < port < 65536


def test_the_port_free_port_returns_can_actually_be_bound():
    """Bind-then-release leaves a theoretical window, but the port it names has
    to be usable the moment after - that is the whole contract."""
    import socket

    port = children.free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", port))
        server.listen(1)
        assert server.getsockname()[1] == port


# -- the environment the child gets ----------------------------------------


def test_children_get_the_progress_flag_and_nothing_else_does(monkeypatch):
    """The single place the flag is set - spec FR-002 rests on this."""
    monkeypatch.delenv("CODEPEDIA_PROGRESS_STREAM", raising=False)

    environment = children.child_environment()

    assert environment["CODEPEDIA_PROGRESS_STREAM"] == "1"
    # And the parent's own environment is untouched.
    import os

    assert "CODEPEDIA_PROGRESS_STREAM" not in os.environ


def test_children_run_unbuffered_so_progress_arrives_as_it_happens():
    """Without this the interpreter block-buffers into a pipe and progress
    arrives in 8KB clumps regardless of the child's own flushing."""
    assert children.child_environment()["PYTHONUNBUFFERED"] == "1"
