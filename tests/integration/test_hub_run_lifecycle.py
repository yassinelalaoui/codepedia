"""How a run begins, advances, and ends (spec FR-012a, FR-015, FR-021 to FR-026).

Two of these were asked for by name in the feature brief: one proving the bar
still advances when a stage takes minutes, and one proving a *failed* run ends
in a clear terminal state rather than a stalled bar.

Both drive a scripted fake child rather than the real pipeline. That is not a
shortcut - it is the only way to exercise a stage that takes minutes, or a child
killed before it can say anything, deterministically and in under a second.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from chat_api.security import TOKEN_HEADER
from cli import paths as cli_paths
from cli.progress_stream import SENTINEL
from hub_server.app import create_hub_app
from hub_server.children import ChildProcess

TOKEN = "lifecycle-token"
AUTH = {TOKEN_HEADER: TOKEN}


@pytest.fixture()
def hub_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".codepedia"
    (home / "repos").mkdir(parents=True)
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: home)
    return home


class ScriptedChild:
    """A child process whose output and exit code the test drives."""

    def __init__(self) -> None:
        self.pid = 31337
        self.stdout = None
        self.returncode: int | None = None
        self._exited = threading.Event()
        self.terminated = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self._exited.wait(timeout)
        return self.returncode if self.returncode is not None else 0

    def terminate(self):
        self.terminated = True
        self.exit(1)

    def kill(self):
        self.terminate()

    def exit(self, code: int) -> None:
        self.returncode = code
        self._exited.set()


@pytest.fixture()
def scripted(monkeypatch):
    """Replace `children.launch` with a child the test feeds by hand."""
    made: dict = {}

    def fake_launch(*, kind, args, repository_path, on_event, on_line, cwd=None):
        process = ScriptedChild()
        child = ChildProcess(
            kind=kind,
            repositoryPath=repository_path,
            process=process,
            onEvent=on_event,
            onLine=on_line,
        )
        made["child"] = child
        made["process"] = process
        made["args"] = args
        return child

    import hub_server.app as hub_app

    monkeypatch.setattr(hub_app.children, "launch", fake_launch)
    # The staging cleanup would otherwise try to touch a real directory for a
    # pid that never existed.
    monkeypatch.setattr(hub_app.children, "discard_staging", lambda path, pid: True)
    return made


@pytest.fixture()
def client(hub_home, tmp_path):
    app = create_hub_app(auth_token=TOKEN, assets_dir=tmp_path / "no-assets")
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def emit(scripted, **payload) -> None:
    """Feed one event to the hub exactly as the reader thread would."""
    from hub_server.progress_parse import parse_line

    event = parse_line(f"{SENTINEL} {json.dumps(payload)}")
    assert event is not None, f"test emitted an event the parser rejects: {payload}"
    scripted["child"].onEvent(event)


def start(client, tmp_path, name: str = "repo"):
    repo = tmp_path / name
    repo.mkdir(exist_ok=True)
    response = client.post("/api/runs", json={"path": str(repo)}, headers=AUTH)
    assert response.status_code == 202
    return repo


def snapshot(client) -> dict:
    return client.get("/api/runs/current", headers=AUTH).json()["run"]


def wait_for(predicate, timeout: float = 5.0):
    """The hub finishes a run on a background thread watching the child exit."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    return None


# -- the bar keeps moving ---------------------------------------------------


def test_the_display_keeps_advancing_through_a_stage_that_takes_minutes(client, tmp_path, scripted):
    """Spec FR-015, SC-002, SC-011 - asked for by name in the feature brief.

    Summarization dominates a real run and, at the rate limit this project's
    Groq key imposes, completes one item at a time over many minutes. A display
    that only moved between stages would sit still for all of it.
    """
    start(client, tmp_path)
    emit(scripted, seq=1, type="stage", stage="SUMMARIZING", label="Generating summaries")

    versions = []
    for index in range(1, 26):
        emit(scripted, seq=index + 1, type="items", stage="SUMMARIZING", completed=index, total=412)
        current = snapshot(client)
        stage = next(item for item in current["stages"] if item["name"] == "SUMMARIZING")
        versions.append(current["version"])
        assert stage["completed"] == index
        assert stage["total"] == 412
        assert current["outcome"] is None, "a long stage must not be mistaken for a finished run"

    # Every single item moved the display: strictly increasing, no repeats.
    assert versions == sorted(versions)
    assert len(set(versions)) == len(versions)


def test_a_run_is_not_considered_stalled_however_long_it_takes(client, tmp_path, scripted):
    start(client, tmp_path)
    emit(scripted, seq=1, type="stage", stage="SUMMARIZING", label="Generating summaries")

    # No events at all for a while - the run is slow, not dead.
    time.sleep(0.3)

    current = snapshot(client)
    assert current["outcome"] is None
    assert current["currentStage"] == "SUMMARIZING"


# -- a failed run ends, clearly ---------------------------------------------


def test_a_failed_run_ends_in_a_clear_terminal_state(client, tmp_path, scripted):
    """Spec FR-021 to FR-024, SC-003, SC-004 - the brief's other named test.

    Reproduces the exact failure this machine produces: nine stages of correct
    work, then an embedding chain with no reachable provider.
    """
    start(client, tmp_path)

    for index, stage in enumerate(
        ["VALIDATING", "SCANNING", "PARSING", "BUILDING_GRAPH", "SUMMARIZING", "EMBEDDING"], start=1
    ):
        emit(scripted, seq=index, type="stage", stage=stage, label=stage.title())

    emit(
        scripted,
        seq=90,
        type="failed",
        stage="EMBEDDING",
        message="No provider in the 'embeddings' chain is currently available.",
        providers=["local:nomic-embed-text:latest", "openai:text-embedding-3-small"],
    )
    scripted["process"].exit(1)

    final = wait_for(lambda: (snapshot(client) or {}).get("outcome"))

    assert final == "failed", "the run never reached a terminal state"
    current = snapshot(client)
    # Spec FR-022: the stage, and every provider tried.
    assert current["failedStage"] == "EMBEDDING"
    assert "embeddings" in current["failureMessage"]
    assert current["providersAttempted"] == [
        "local:nomic-embed-text:latest",
        "openai:text-embedding-3-small",
    ]
    # Spec FR-023: the ticked stages above must not be read as saved work.
    assert current["discardedEverything"] is True
    assert current["currentStage"] is None
    assert all(stage["status"] != "running" for stage in current["stages"])


def test_a_child_killed_before_saying_anything_still_ends_the_run(client, tmp_path, scripted):
    """Spec FR-021, and contracts/run-progress-stream.md reader obligation 6.

    Exit code is authoritative. Without this, a segfaulting child would leave
    the bar spinning forever - the exact outcome the feature exists to prevent.
    """
    start(client, tmp_path)

    scripted["process"].exit(3)

    assert wait_for(lambda: (snapshot(client) or {}).get("outcome")) == "failed"
    assert snapshot(client)["failureMessage"]


def test_the_hub_accepts_a_new_analysis_after_a_failure(client, tmp_path, scripted):
    """Spec FR-026: a failed run must not wedge the hub permanently."""
    start(client, tmp_path, "first")
    scripted["process"].exit(1)
    wait_for(lambda: (snapshot(client) or {}).get("outcome"))

    client.post("/api/runs/current/dismiss", headers=AUTH)
    second = tmp_path / "second"
    second.mkdir()

    assert client.post("/api/runs", json={"path": str(second)}, headers=AUTH).status_code == 202


# -- cancelling -------------------------------------------------------------


def test_cancelling_ends_the_run_promptly_and_keeps_nothing(client, tmp_path, scripted):
    """Spec FR-012a."""
    start(client, tmp_path)
    emit(scripted, seq=1, type="stage", stage="SUMMARIZING", label="Generating summaries")

    response = client.post("/api/runs/current/cancel", headers=AUTH)

    assert response.status_code == 200
    run = response.json()["run"]
    assert run["outcome"] == "cancelled"
    assert run["discardedEverything"] is True
    assert scripted["process"].terminated, "cancel must actually stop the child"


def test_a_cancelled_run_is_not_relabelled_when_the_child_then_dies(client, tmp_path, scripted):
    """The child exits non-zero a moment after Stop - as it must, having been
    terminated. Telling the person their run *failed* would be wrong."""
    start(client, tmp_path)
    client.post("/api/runs/current/cancel", headers=AUTH)

    scripted["process"].exit(1)
    time.sleep(0.2)

    assert snapshot(client)["outcome"] == "cancelled"


def test_a_new_analysis_can_start_immediately_after_cancelling(client, tmp_path, scripted):
    start(client, tmp_path, "first")
    client.post("/api/runs/current/cancel", headers=AUTH)
    client.post("/api/runs/current/dismiss", headers=AUTH)

    second = tmp_path / "second"
    second.mkdir()

    assert client.post("/api/runs", json={"path": str(second)}, headers=AUTH).status_code == 202


# -- the run log ------------------------------------------------------------


def test_a_finished_run_is_recorded_with_its_diagnosis(client, tmp_path, scripted):
    """Spec FR-026a: the outcome outlives the run itself."""
    start(client, tmp_path)
    emit(
        scripted,
        seq=1,
        type="failed",
        stage="EMBEDDING",
        message="No provider in the 'embeddings' chain is currently available.",
        providers=["local:nomic-embed-text:latest"],
    )
    scripted["process"].exit(1)
    wait_for(lambda: (snapshot(client) or {}).get("outcome"))

    runs = client.get("/api/run-log", headers=AUTH).json()["runs"]

    assert len(runs) == 1
    assert runs[0]["outcome"] == "failed"
    assert runs[0]["failedStage"] == "EMBEDDING"
    assert runs[0]["providersAttempted"] == ["local:nomic-embed-text:latest"]


def test_a_run_whose_hub_died_reads_as_interrupted_on_the_next_start(client, tmp_path, scripted, hub_home):
    """Spec FR-026d.

    The hub is killed mid-run, so nothing ever closes that row. On the next
    start the sweep must resolve it - otherwise it reads as in-progress forever.
    """
    start(client, tmp_path)
    # No exit, no close: exactly what a killed hub leaves behind.

    from hub_server.run_log import RunLog

    swept = RunLog().sweep_interrupted()

    assert swept == 1
    assert RunLog().recent()[0].outcome == "interrupted"
