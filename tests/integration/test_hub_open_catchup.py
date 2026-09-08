"""Opening a repository, and showing the catch-up it triggers.

Spec FR-019, FR-020, FR-035, FR-038a.

The ordering these rely on is real and load-bearing: `watcher.start()` runs
`compute_catchup_batch` synchronously (`repo_watcher/watcher.py:51-53`) before
`start_local_server` prints the URL. So a hub-launched `serve` reports
everything it is bringing up to date and only then hands over the address.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

from chat_api.security import TOKEN_HEADER
from cli import paths as cli_paths
from cli.progress_stream import SENTINEL
from hub_server.app import create_hub_app
from hub_server.children import ChildProcess, classify_failure

TOKEN = "open-token"
AUTH = {TOKEN_HEADER: TOKEN}


@pytest.fixture()
def hub_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".codepedia"
    (home / "repos").mkdir(parents=True)
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: home)
    return home


def make_entry(hub_home, state_id: str, root_path: str) -> None:
    directory = hub_home / "repos" / state_id
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "repository-metadata.sqlite")
    connection.execute("CREATE TABLE repositories (root_path TEXT NOT NULL UNIQUE, last_indexed_at TEXT)")
    connection.execute(
        "INSERT INTO repositories (root_path, last_indexed_at) VALUES (?, ?)",
        (root_path, "2026-09-01T10:00:00"),
    )
    connection.commit()
    connection.close()


class ScriptedServer:
    def __init__(self) -> None:
        self.pid = 5150
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

    def kill(self):
        self.terminate()

    def exit(self, code: int) -> None:
        self.returncode = code
        self._exited.set()


@pytest.fixture()
def scripted(monkeypatch):
    made: dict = {}

    def fake_launch(*, kind, args, repository_path, on_event, on_line, cwd=None):
        process = ScriptedServer()
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
    monkeypatch.setattr(hub_app.children, "discard_staging", lambda path, pid: True)
    return made


@pytest.fixture()
def client(hub_home, tmp_path):
    app = create_hub_app(auth_token=TOKEN, assets_dir=tmp_path / "no-assets")
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def feed(scripted, **payload) -> None:
    from hub_server.progress_parse import parse_line

    event = parse_line(f"{SENTINEL} {json.dumps(payload)}")
    assert event is not None
    scripted["child"].onEvent(event)
    if payload.get("type") == "server_ready":
        scripted["child"].url = payload["url"]
        scripted["child"]._urlReady.set()


def test_open_launches_serve_on_loopback_with_a_free_port(client, hub_home, tmp_path, scripted):
    root = tmp_path / "project"
    root.mkdir()
    make_entry(hub_home, "0123456789abcdef", str(root))

    threading.Timer(
        0.2, lambda: feed(scripted, seq=1, type="server_ready", url="http://127.0.0.1:51734/?token=abc")
    ).start()
    response = client.post("/api/repositories/0123456789abcdef/open", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["url"] == "http://127.0.0.1:51734/?token=abc"
    args = scripted["args"]
    assert args[0] == "serve"
    # Constitution 2.2: the child is bound to loopback explicitly, never
    # inheriting whatever the hub happened to be bound to.
    assert "--host" in args and args[args.index("--host") + 1] == "127.0.0.1"
    assert "--port" in args


def test_a_repository_with_nothing_to_catch_up_shows_no_progress_display(
    client, hub_home, tmp_path, scripted
):
    """Spec FR-020: no empty bar for someone who just wants to read."""
    root = tmp_path / "project"
    root.mkdir()
    make_entry(hub_home, "0123456789abcdef", str(root))

    threading.Timer(
        0.1, lambda: feed(scripted, seq=1, type="server_ready", url="http://127.0.0.1:1/?token=x")
    ).start()
    started = time.perf_counter()
    response = client.post("/api/repositories/0123456789abcdef/open", headers=AUTH)
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert "url" in response.json()
    assert "runId" not in response.json(), "a catch-up display was offered when there was nothing to show"
    assert elapsed < 5.0


def test_catchup_work_is_reported_as_a_run_the_page_can_follow(client, hub_home, tmp_path, scripted):
    """Spec FR-019: the previously-invisible catch-up becomes visible."""
    root = tmp_path / "project"
    root.mkdir()
    make_entry(hub_home, "0123456789abcdef", str(root))

    # No `server_ready` inside the quick window - there is work to do first.
    threading.Timer(0.1, lambda: feed(scripted, seq=1, type="catchup", phase="parsing", completed=1, total=11, path="a.py")).start()

    response = client.post("/api/repositories/0123456789abcdef/open", headers=AUTH)

    assert response.status_code == 202
    assert response.json()["catchup"] is True
    run = client.get("/api/runs/current", headers=AUTH).json()["run"]
    assert run["kind"] == "open"
    assert run["catchup"]["completed"] == 1
    assert run["catchup"]["total"] == 11
    assert run["catchup"]["path"] == "a.py"


def test_the_page_gets_the_url_once_catchup_finishes(client, hub_home, tmp_path, scripted):
    root = tmp_path / "project"
    root.mkdir()
    make_entry(hub_home, "0123456789abcdef", str(root))

    threading.Timer(0.1, lambda: feed(scripted, seq=1, type="catchup", phase="parsing", completed=1, total=3, path="a.py")).start()
    client.post("/api/repositories/0123456789abcdef/open", headers=AUTH)

    feed(scripted, seq=2, type="server_ready", url="http://127.0.0.1:51734/?token=abc")

    run = client.get("/api/runs/current", headers=AUTH).json()["run"]
    assert run["serverUrl"] == "http://127.0.0.1:51734/?token=abc"


def test_opening_a_repository_whose_folder_is_gone_is_still_offered(client, hub_home, tmp_path, scripted):
    """Spec FR-039: the documentation is intact and readable; only bringing it
    up to date is impossible."""
    make_entry(hub_home, "0123456789abcdef", str(tmp_path / "deleted"))

    entries = client.get("/api/repositories", headers=AUTH).json()["repositories"]

    assert entries[0]["available"] is False


# -- failure classification (data-model.md §4) ------------------------------


def _child_with_output(lines: list[str]) -> ChildProcess:
    child = ChildProcess(
        kind="open",
        repositoryPath="C:/repo",
        process=ScriptedServer(),
        onEvent=lambda event: None,
        onLine=lambda line: None,
    )
    child.lines = lines
    return child


def test_a_missing_index_is_classified_as_an_unusable_analysis():
    """Spec FR-038."""
    child = _child_with_output(["No index found for C:/repo. Run `codepedia index C:/repo` first."])

    result = classify_failure(child)

    assert result["kind"] == "index_missing"
    assert "Analyse it to rebuild" in result["message"]


def test_a_provider_outage_is_classified_separately_and_names_the_chain():
    """Spec FR-038a, and research.md §11's finding.

    `run_serve` checks all three chains before doing anything, so on a machine
    with an unreachable embedding chain every Open fails even though the wiki is
    complete on disk. Calling that "your analysis is unusable" would be a false
    diagnosis that sends someone to re-run an index that was never the problem.
    """
    child = _child_with_output(
        ["No provider in the 'embeddings' chain is currently available. Start the local service..."]
    )

    result = classify_failure(child)

    assert result["kind"] == "provider_unavailable"
    assert result["chain"] == "embeddings"
    assert "provider problem, not a problem with the analysis" in result["message"]
    assert "documentation is intact" in result["message"]


def test_a_bind_failure_is_classified_as_being_out_of_ports():
    """Spec FR-037: failure to start a further server is reported, not silent."""
    child = _child_with_output(
        ["Could not start the server on 127.0.0.1:51734 - the address may already be in use."]
    )

    result = classify_failure(child)

    assert result["kind"] == "bind_failed"


def test_an_unrecognised_failure_still_produces_a_message():
    child = _child_with_output(["Traceback (most recent call last):", "  something unexpected"])

    result = classify_failure(child)

    assert result["kind"] == "failed"
    assert result["message"]
    assert result["detail"], "the tail of the child's output is what makes it diagnosable"
