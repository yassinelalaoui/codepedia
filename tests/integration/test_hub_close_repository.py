"""Closing one open wiki without ending the hub session.

Opening a repository leaves its server running on purpose: returning to it is
then instant, and its watcher keeps it current. Every child dies with the hub
(spec FR-007), but between those two points there was no way to stop one - so a
session that opened three repositories kept three servers, and
`remove_repository` answered "Close it before removing it" with no Close
anywhere to press.

The harness is `test_hub_open_terminates.py`'s, for the same reason it exists
there: a child that keeps running is what makes any of this observable.
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

TOKEN = "close-repository-token"
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
        self.pid = 6061
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


def _ready(scripted, url: str = "http://127.0.0.1:51795/?token=abc") -> None:
    from hub_server.progress_parse import parse_line

    event = parse_line(f"{SENTINEL} {json.dumps({'seq': 1, 'type': 'server_ready', 'url': url})}")
    assert event is not None
    child = scripted["child"]
    child.onEvent(event)
    child.url = url
    child._urlReady.set()


def _open(client, scripted) -> None:
    response = client.post(f"/api/repositories/{STATE_ID}/open", headers=AUTH)
    assert response.status_code == 202, "expected the catch-up path for this test"
    _ready(scripted)


def _entry(client) -> dict:
    repositories = client.get("/api/repositories", headers=AUTH).json()["repositories"]
    return next(entry for entry in repositories if entry["stateId"] == STATE_ID)


def test_closing_an_open_repository_stops_its_server(client, scripted):
    _open(client, scripted)
    assert scripted["child"].is_running(), "the fixture must leave a server running"

    response = client.post(f"/api/repositories/{STATE_ID}/close", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"closed": True}
    assert not scripted["child"].is_running()


def test_the_listing_says_which_repositories_are_open(client, scripted):
    """What the row menu offers Close on: without it the page cannot tell an
    open repository from a closed one."""
    assert _entry(client)["open"] is False

    _open(client, scripted)
    assert _entry(client)["open"] is True

    client.post(f"/api/repositories/{STATE_ID}/close", headers=AUTH)
    assert _entry(client)["open"] is False


def test_closing_a_repository_that_is_not_open_is_not_an_error(client):
    """Idempotent: two clicks, a stale page, or a server that already exited."""
    response = client.post(f"/api/repositories/{STATE_ID}/close", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"closed": False}


def test_a_closed_repository_can_then_be_removed(client, scripted, hub_home):
    """The dead end this route exists for: remove refused while a server ran,
    and nothing could stop that server short of quitting the hub."""
    _open(client, scripted)
    blocked = client.delete(f"/api/repositories/{STATE_ID}", headers=AUTH)
    assert blocked.status_code == 409

    client.post(f"/api/repositories/{STATE_ID}/close", headers=AUTH)
    removed = client.delete(f"/api/repositories/{STATE_ID}", headers=AUTH)

    assert removed.status_code in (200, 204), removed.text
    assert not (hub_home / "repos" / STATE_ID).exists()


def test_reopening_after_a_close_starts_a_fresh_server(client, scripted):
    """Closing must drop the child, not just stop it: a stopped child left in
    the map would be handed back as a live server on the next open."""
    _open(client, scripted)
    first = scripted["child"]
    client.post(f"/api/repositories/{STATE_ID}/close", headers=AUTH)

    response = client.post(f"/api/repositories/{STATE_ID}/open", headers=AUTH)

    assert response.status_code == 202, response.text
    assert scripted["child"] is not first, "the closed server was reused"


def test_closing_is_refused_while_that_repository_is_being_analysed(client, scripted, tmp_path):
    """A run still working on it is cancelled through the run, never closed out
    from under itself - the same conflict remove reports."""
    client.post("/api/runs", json={"path": client.repository_root}, headers=AUTH)

    response = client.post(f"/api/repositories/{STATE_ID}/close", headers=AUTH)

    assert response.status_code == 409
    assert "Stop the analysis" in response.json()["error"]["message"]


def test_closing_needs_the_token(client, scripted):
    _open(client, scripted)

    response = client.post(f"/api/repositories/{STATE_ID}/close")

    assert response.status_code == 401
    assert scripted["child"].is_running(), "an unauthorized call must not stop anything"


def test_closing_an_unknown_repository_is_not_found(client):
    response = client.post("/api/repositories/deadbeefdeadbeef/close", headers=AUTH)

    assert response.status_code == 404
