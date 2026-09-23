"""Spec FR-002 / SC-008: the CLI prints exactly what it printed before.

Feature 037 adds a progress channel so `codepedia home` can draw a bar for a
running analysis. The whole design rests on that channel being invisible unless
a parent process asks for it (research.md §2), and this file is where that claim
is checked rather than asserted.

These tests drive the CLI as a **real subprocess**, which is both the strictest
form of the check - it sees actual bytes on an actual pipe, including any
buffering or encoding surprise - and the exact path `hub_server.children` uses.

They deliberately do not need working providers. `VALIDATING` and
`CHECKING_MODELS` are announced before `check_ai_dependencies` can reject an
unreachable chain (`cli/index_command.py:184`, `:239`), so a run that fails
immediately still proves the gate in both directions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cli.config import CLIConfiguration
from cli.progress_stream import ENV_VAR, SENTINEL

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
FIXTURE_REPO = REPO_ROOT / "tests" / "integration" / "fixtures" / "repository-metadata" / "sample-repo"


def _run_cli(args: list[str], *, home: Path, progress_stream: bool) -> subprocess.CompletedProcess[str]:
    """Invoke `python -m cli ...` with `~/.codepedia` redirected into `home`.

    `USERPROFILE`/`HOME` is what `cli.paths.codepedia_home` resolves through, so
    redirecting it keeps a child process off the real developer machine the same
    way the `cli_home` fixture does for in-process tests.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    env["PYTHONIOENCODING"] = "utf-8"
    env["USERPROFILE"] = str(home)
    env["HOME"] = str(home)
    # Never inherit the flag from whatever launched pytest: these tests assert
    # on its presence and absence, so it has to be set here and nowhere else.
    env.pop(ENV_VAR, None)
    if progress_stream:
        env[ENV_VAR] = "1"

    return subprocess.run(
        [sys.executable, "-m", "cli", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


def _seed_config(home: Path) -> None:
    """Write a config naming deliberately unreachable models.

    These tests only need the run to *start*: `VALIDATING` and
    `CHECKING_MODELS` are both announced before availability is checked, so a
    model that does not exist is enough and keeps the test off the network and
    off Ollama entirely.
    """
    config = CLIConfiguration(llmModel="test-llm", embeddingModel="test-embed")
    target = home / ".codepedia"
    target.mkdir(parents=True, exist_ok=True)
    (target / "config.json").write_text(json.dumps(config.to_dict()), encoding="utf-8")


@pytest.fixture()
def child_home(tmp_path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    _seed_config(home)
    return home


def test_module_entry_point_exists(child_home):
    """`python -m cli` must work: it is how the hub launches every child."""
    result = _run_cli(["--help"], home=child_home, progress_stream=False)

    assert result.returncode == 0
    assert "index" in result.stdout
    assert "serve" in result.stdout


def test_help_carries_no_sentinel_even_when_enabled(child_home):
    result = _run_cli(["--help"], home=child_home, progress_stream=True)

    assert SENTINEL not in result.stdout


def test_index_emits_no_sentinel_line_when_variable_unset(child_home):
    """The FR-002 guard.

    If someone later makes emission unconditional, this fails - which is the
    entire point of it existing.
    """
    result = _run_cli(["index", str(FIXTURE_REPO)], home=child_home, progress_stream=False)

    combined = result.stdout + result.stderr
    assert SENTINEL not in combined, "the CLI leaked progress events without being asked"


def test_serve_emits_no_sentinel_line_when_variable_unset(child_home):
    result = _run_cli(["serve", str(FIXTURE_REPO)], home=child_home, progress_stream=False)

    combined = result.stdout + result.stderr
    assert SENTINEL not in combined


def test_index_emits_sentinel_lines_when_variable_set(child_home):
    """The other direction: the gate opens when the hub asks.

    Without this, a gate that was accidentally welded shut would still pass the
    test above and the homepage would show nothing forever.
    """
    result = _run_cli(["index", str(FIXTURE_REPO)], home=child_home, progress_stream=True)

    assert SENTINEL in result.stdout


def test_human_readable_stage_lines_survive_alongside_events(child_home):
    """Spec FR-016: the channel adds, it never removes or replaces.

    The stage wording the terminal prints must still be there when events are
    switched on, because that terminal output is what a person watching a
    hub-launched run in their console still relies on.
    """
    with_events = _run_cli(["index", str(FIXTURE_REPO)], home=child_home, progress_stream=True)
    without_events = _run_cli(["index", str(FIXTURE_REPO)], home=child_home, progress_stream=False)

    human_only = [line for line in with_events.stdout.splitlines() if not line.startswith(SENTINEL)]
    baseline = without_events.stdout.splitlines()

    assert human_only == baseline, "enabling the progress stream changed the human-readable output"
