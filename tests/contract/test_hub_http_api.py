"""The hub's HTTP surface (contracts/hub-http-api.md).

Covers the guarantees that are easy to break silently: a rejected path starts
nothing, a second run is refused, the token is required on every state-changing
route, and a forged `Host` is turned away.
"""

from __future__ import annotations

import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from chat_api.security import TOKEN_HEADER
from cli import paths as cli_paths
from hub_server.app import create_hub_app

TOKEN = "test-token-value"
AUTH = {TOKEN_HEADER: TOKEN}


@pytest.fixture()
def hub_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".codepedia"
    (home / "repos").mkdir(parents=True)
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: home)
    return home


@pytest.fixture()
def client(hub_home, tmp_path):
    app = create_hub_app(auth_token=TOKEN, assets_dir=tmp_path / "no-assets")
    # `base_url` matters: TestClient's default `http://testserver` sends a Host
    # header the allowed-hosts middleware correctly rejects. Pointing it at
    # loopback is what a browser on this machine actually does - and the
    # rejection itself is asserted separately below.
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


@pytest.fixture()
def no_launch(monkeypatch):
    """Record what would have been launched, without launching it.

    Every assertion below is about the hub's own decisions - validation,
    exclusivity, auth - so a real child process would only add minutes and
    flakiness.
    """
    launched: list[dict] = []

    class FakeProcess:
        """A child that stays alive until the test lets it exit.

        `wait()` blocking is the important part: the hub turns a child's exit
        into the run's terminal state, so a fake that returns immediately would
        make every run finish before the next assertion and quietly defeat the
        exclusivity and conflict tests below.
        """

        def __init__(self) -> None:
            self.pid = 4242
            self.stdout = None
            self._exited = threading.Event()
            self.returncode: int | None = None

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

    def fake_launch(*, kind, args, repository_path, on_event, on_line, cwd=None):
        from hub_server.children import ChildProcess

        launched.append({"kind": kind, "args": args, "repositoryPath": repository_path})
        child = ChildProcess(
            kind=kind,
            repositoryPath=repository_path,
            process=FakeProcess(),
            onEvent=on_event,
            onLine=on_line,
        )
        return child

    import hub_server.app as hub_app

    monkeypatch.setattr(hub_app.children, "launch", fake_launch)
    return launched


def make_history_entry(hub_home, state_id: str, root_path: str) -> None:
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


# -- authentication ---------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/runs"),
        ("get", "/api/runs/current"),
        ("post", "/api/runs/current/cancel"),
        ("post", "/api/runs/current/dismiss"),
        ("get", "/api/repositories"),
        ("post", "/api/repositories/0123456789abcdef/open"),
        ("delete", "/api/repositories/0123456789abcdef"),
        ("get", "/api/run-log"),
    ],
)
def test_every_api_route_requires_the_token(client, method, path):
    """Spec FR-005 and SC-009."""
    call = getattr(client, method)
    response = call(path, json={}) if method == "post" else call(path)

    assert response.status_code == 401
    assert response.json()["error"]["kind"] == "unauthorized"


def test_a_wrong_token_is_refused(client):
    response = client.get("/api/repositories", headers={TOKEN_HEADER: "not-the-token"})

    assert response.status_code == 401


def test_starting_a_run_without_a_token_starts_nothing(client, no_launch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    response = client.post("/api/runs", json={"path": str(repo)})

    assert response.status_code == 401
    assert no_launch == [], "an unauthenticated request launched a process"


def test_a_forged_host_header_is_rejected(client):
    """Spec FR-006: a page on another origin must not reach this server by
    pointing a domain at 127.0.0.1."""
    response = client.get("/api/repositories", headers={**AUTH, "Host": "evil.example.com"})

    assert response.status_code == 400


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_loopback_hosts_are_accepted(client, host):
    response = client.get("/api/repositories", headers={**AUTH, "Host": host})

    assert response.status_code == 200


# -- starting a run ---------------------------------------------------------


def test_a_valid_path_starts_a_run_and_echoes_the_resolved_path(client, no_launch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    response = client.post("/api/runs", json={"path": f"{repo}/"}, headers=AUTH)

    assert response.status_code == 202
    body = response.json()
    assert body["repositoryPath"] == str(repo.resolve())
    assert body["runId"]
    assert no_launch[0]["args"][0] == "index"


@pytest.mark.parametrize(
    "path_factory,expected",
    [
        (lambda tmp: "", "Enter the path"),
        (lambda tmp: str(tmp / "missing"), "nothing at"),
        (lambda tmp: "FILE", "file, not a folder"),
    ],
)
def test_an_invalid_path_is_refused_and_nothing_is_started(
    client, no_launch, tmp_path, path_factory, expected
):
    """Spec FR-010: a distinct message per problem, and no side effect."""
    if path_factory(tmp_path) == "FILE":
        target = tmp_path / "a-file.txt"
        target.write_text("x", encoding="utf-8")
        submitted = str(target)
    else:
        submitted = path_factory(tmp_path)

    response = client.post("/api/runs", json={"path": submitted}, headers=AUTH)

    assert response.status_code == 400
    assert response.json()["error"]["kind"] == "invalid_path"
    assert expected in response.json()["error"]["message"]
    assert no_launch == []


def test_the_state_directory_cannot_be_analysed(client, no_launch, hub_home):
    """Constitution 2.7, on the input side."""
    response = client.post("/api/runs", json={"path": str(hub_home)}, headers=AUTH)

    assert response.status_code == 400
    assert no_launch == []


def test_a_second_run_is_refused_and_names_the_running_one(client, no_launch, tmp_path):
    """Spec FR-012: one at a time, refused rather than queued."""
    first = tmp_path / "first"
    first.mkdir()
    second = tmp_path / "second"
    second.mkdir()

    assert client.post("/api/runs", json={"path": str(first)}, headers=AUTH).status_code == 202
    response = client.post("/api/runs", json={"path": str(second)}, headers=AUTH)

    assert response.status_code == 409
    assert response.json()["error"]["kind"] == "run_in_progress"
    assert str(first.resolve()) in response.json()["error"]["message"]
    assert len(no_launch) == 1, "the refused request must not have started anything"


def test_current_run_is_null_before_anything_has_run(client):
    assert client.get("/api/runs/current", headers=AUTH).json() == {"run": None}


def test_current_run_reports_the_live_run(client, no_launch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    client.post("/api/runs", json={"path": str(repo)}, headers=AUTH)

    body = client.get("/api/runs/current", headers=AUTH).json()

    assert body["run"]["repositoryPath"] == str(repo.resolve())
    assert body["run"]["outcome"] is None
    assert len(body["run"]["stages"]) == 10


def test_cancel_without_a_run_is_a_conflict(client):
    assert client.post("/api/runs/current/cancel", headers=AUTH).status_code == 409


def test_dismiss_refuses_while_a_run_is_live(client, no_launch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    client.post("/api/runs", json={"path": str(repo)}, headers=AUTH)

    response = client.post("/api/runs/current/dismiss", headers=AUTH)

    assert response.status_code == 409


# -- the history ------------------------------------------------------------


def test_repositories_lists_analysed_entries_only(client, hub_home, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    make_history_entry(hub_home, "0123456789abcdef", str(root))
    make_history_entry(hub_home, "0123456789abcdef.staging-999", str(root))

    body = client.get("/api/repositories", headers=AUTH).json()

    assert [entry["stateId"] for entry in body["repositories"]] == ["0123456789abcdef"]


def test_opening_an_unknown_repository_is_a_404(client):
    response = client.post("/api/repositories/ffffffffffffffff/open", headers=AUTH)

    assert response.status_code == 404


def test_removing_an_unknown_repository_is_a_404(client):
    assert client.delete("/api/repositories/ffffffffffffffff", headers=AUTH).status_code == 404


def test_remove_deletes_the_state_directory_and_nothing_else(client, hub_home, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('hello')", encoding="utf-8")
    make_history_entry(hub_home, "0123456789abcdef", str(root))

    response = client.delete("/api/repositories/0123456789abcdef", headers=AUTH)

    assert response.status_code == 204
    assert not (hub_home / "repos" / "0123456789abcdef").exists()
    # Constitution 2.7 and spec FR-041.
    assert (root / "main.py").read_text(encoding="utf-8") == "print('hello')"
    assert client.get("/api/repositories", headers=AUTH).json()["repositories"] == []


def test_remove_is_refused_while_that_repository_is_being_analysed(
    client, no_launch, hub_home, tmp_path
):
    """Spec FR-042: surface the conflict, never delete half of it."""
    root = tmp_path / "project"
    root.mkdir()
    make_history_entry(hub_home, "0123456789abcdef", str(root))
    client.post("/api/runs", json={"path": str(root)}, headers=AUTH)

    response = client.delete("/api/repositories/0123456789abcdef", headers=AUTH)

    assert response.status_code == 409
    assert response.json()["error"]["kind"] == "conflict"
    assert (hub_home / "repos" / "0123456789abcdef").exists()


# -- the run log ------------------------------------------------------------


def test_run_log_is_empty_rather_than_failing_when_absent(client):
    """Spec FR-026e: never a 500."""
    response = client.get("/api/run-log", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"runs": []}


def test_a_started_run_appears_in_the_run_log(client, no_launch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    client.post("/api/runs", json={"path": str(repo)}, headers=AUTH)

    runs = client.get("/api/run-log", headers=AUTH).json()["runs"]

    assert len(runs) == 1
    assert runs[0]["repositoryPath"] == str(repo.resolve())
    assert runs[0]["kind"] == "index"


def test_a_corrupt_run_log_still_answers_200(client, hub_home):
    (hub_home / "runs.sqlite").write_bytes(b"not a database")

    response = client.get("/api/run-log", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"runs": []}
