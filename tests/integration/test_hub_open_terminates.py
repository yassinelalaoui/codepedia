"""An `open` run ends when its server is ready, not when its server dies.

An `index` run ends when its process ends. An `open` run does not: the child it
starts *is* the wiki server, so waiting for that child to exit means waiting for
the reader to close the wiki. Treating the two the same left the run
permanently non-terminal, which produced three symptoms that all looked
unrelated and were the same bug:

1. Returning to the homepage bounced you straight back to the wiki, because a
   run carrying a `serverUrl` still looked live. There was no way to stay on
   the homepage at all.
2. No new analysis could be started while any wiki was open - the hub answered
   "an analysis is already running".
3. The run log kept a row with a NULL outcome, which the next startup sweep
   would have mislabelled as interrupted.
"""

from __future__ import annotations

import json
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from chat_api.security import TOKEN_HEADER
from cli import paths as cli_paths
from cli.progress_stream import SENTINEL
from hub_server.app import create_hub_app
from hub_server.children import ChildProcess

TOKEN = "open-terminates-token"
AUTH = {TOKEN_HEADER: TOKEN}
STATE_ID = "0123456789abcdef"


@pytest.fixture()
def hub_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".codepedia"
    (home / "repos").mkdir(parents=True)
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: home)
    return home


class LiveServer:
    """A child that keeps running, exactly as a served wiki does."""

    def __init__(self) -> None:
        self.pid = 6060
        self.stdout = None
        self.returncode: int | None = None
        self._exited = threading.Event()

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self._exited.wait(timeout)
        return self.returncode if self.returncode is not None else 0

    def terminate(self):
        self.returncode = 1
        self._exited.set()

    kill = terminate


@pytest.fixture()
def scripted(monkeypatch):
    made: dict = {}

    def fake_launch(*, kind, args, repository_path, on_event, on_line, cwd=None):
        child = ChildProcess(
            kind=kind,
            repositoryPath=repository_path,
            process=LiveServer(),
            onEvent=on_event,
            onLine=on_line,
        )
        made["child"] = child
        return child

    import hub_server.app as hub_app

    monkeypatch.setattr(hub_app.children, "launch", fake_launch)
    monkeypatch.setattr(hub_app.children, "discard_staging", lambda path, pid: True)
    return made


@pytest.fixture()
def client(hub_home, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    directory = hub_home / "repos" / STATE_ID
    directory.mkdir(parents=True)
    connection = sqlite3.connect(directory / "repository-metadata.sqlite")
    connection.execute("CREATE TABLE repositories (root_path TEXT NOT NULL UNIQUE, last_indexed_at TEXT)")
    connection.execute(
        "INSERT INTO repositories (root_path, last_indexed_at) VALUES (?, ?)",
        (str(root), "2026-09-01T10:00:00"),
    )
    connection.commit()
    connection.close()

    app = create_hub_app(auth_token=TOKEN, assets_dir=tmp_path / "no-assets")
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        test_client.repository_root = str(root)  # type: ignore[attr-defined]
        yield test_client


def ready(scripted, url: str = "http://127.0.0.1:51795/?token=abc") -> None:
    """Deliver a `server_ready` event exactly as the stdout reader would.

    The reader does two things with this event, and a double that only did the
    first would quietly stop the reuse path being exercised: it hands the event
    on, *and* it records the URL on the child so a later open of the same
    repository can be answered from the server already running.
    """
    from hub_server.progress_parse import parse_line

    event = parse_line(f"{SENTINEL} {json.dumps({'seq': 1, 'type': 'server_ready', 'url': url})}")
    assert event is not None
    child = scripted["child"]
    child.onEvent(event)
    child.url = url
    child._urlReady.set()


def open_with_catchup(client, scripted):
    """Open the repository slowly enough that the hub reports catch-up work."""
    response = client.post(f"/api/repositories/{STATE_ID}/open", headers=AUTH)
    assert response.status_code == 202, "expected the catch-up path for this test"
    ready(scripted)
    return response.json()["runId"]


def snapshot(client):
    return client.get("/api/runs/current", headers=AUTH).json()["run"]


def test_the_run_succeeds_as_soon_as_the_server_is_ready(client, scripted):
    open_with_catchup(client, scripted)

    run = snapshot(client)

    assert run["outcome"] == "succeeded", "an open run stayed live while its server ran"
    assert run["serverUrl"] == "http://127.0.0.1:51795/?token=abc"


def test_the_child_keeps_running_after_the_run_has_ended(client, scripted):
    """The wiki must stay served. Ending the run is bookkeeping, not a stop."""
    open_with_catchup(client, scripted)

    assert scripted["child"].is_running()
    assert scripted["child"].process.returncode is None


def test_a_new_analysis_can_start_while_a_wiki_is_open(client, scripted, tmp_path):
    """Symptom 2. Before the fix this answered 409 for as long as any wiki was
    open, so the homepage was unusable the moment you had used it once."""
    open_with_catchup(client, scripted)

    other = tmp_path / "another-project"
    other.mkdir()
    response = client.post("/api/runs", json={"path": str(other)}, headers=AUTH)

    assert response.status_code == 202, response.text


def test_the_run_log_records_the_open_rather_than_leaving_it_dangling(client, scripted):
    """Symptom 3. A NULL outcome is what the startup sweep reads as interrupted."""
    open_with_catchup(client, scripted)

    runs = client.get("/api/run-log", headers=AUTH).json()["runs"]

    assert len(runs) == 1
    assert runs[0]["kind"] == "open"
    assert runs[0]["outcome"] == "succeeded"
    assert runs[0]["endedAt"] is not None


def test_the_terminal_snapshot_still_carries_the_url_to_navigate_to(client, scripted):
    """The page needs it to take the reader to the wiki - ending the run must
    not cost it that."""
    open_with_catchup(client, scripted)

    run = snapshot(client)
    assert run["serverUrl"]
    assert run["kind"] == "open"
    # And it is not reported as a failure that discarded work.
    assert run["discardedEverything"] is False


def test_reopening_the_same_repository_reuses_the_running_server(client, scripted):
    open_with_catchup(client, scripted)

    response = client.post(f"/api/repositories/{STATE_ID}/open", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["url"] == "http://127.0.0.1:51795/?token=abc"
