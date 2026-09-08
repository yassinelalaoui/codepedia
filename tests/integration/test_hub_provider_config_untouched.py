"""The hub reports on providers; it never changes them (spec FR-025).

Feature 037 surfaces provider failures prominently - it has to, because on a
machine with an unreachable embedding chain that is what every run does. The
temptation this guards against is the obvious "helpful" one: noticing the chain
is broken and rewriting it. That would mutate the user's configuration and
re-trigger the disclosure gate, and it belongs to feature 038, not this one.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from chat_api.security import TOKEN_HEADER
from cli import paths as cli_paths
from cli.config import CLIConfiguration, disclosure_signature
from hub_server.app import create_hub_app

TOKEN = "config-token"
AUTH = {TOKEN_HEADER: TOKEN}


@pytest.fixture()
def hub_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".codepedia"
    (home / "repos").mkdir(parents=True)
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: home)

    # A chain that cannot possibly work - exactly the situation the hub is
    # expected to report on.
    config = CLIConfiguration(
        embeddingChain=("local:nomic-embed-text:latest", "openai:text-embedding-3-small"),
        summaryChain=("groq:openai/gpt-oss-20b",),
        chatChain=("groq:openai/gpt-oss-20b",),
    )
    acknowledged = CLIConfiguration(
        **{**config.to_dict(), "disclosureAcknowledgedSignature": disclosure_signature(config)}
    )
    (home / "config.json").write_text(json.dumps(acknowledged.to_dict()), encoding="utf-8")
    return home


def fingerprint(home) -> str:
    return hashlib.sha256((home / "config.json").read_bytes()).hexdigest()


@pytest.fixture()
def client(hub_home, tmp_path, monkeypatch):
    import hub_server.app as hub_app

    class Dead:
        def __init__(self) -> None:
            self.pid = 999
            self.stdout = None
            self.returncode = 1

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def terminate(self):
            return None

        def kill(self):
            return None

    def fake_launch(*, kind, args, repository_path, on_event, on_line, cwd=None):
        from hub_server.children import ChildProcess

        return ChildProcess(
            kind=kind,
            repositoryPath=repository_path,
            process=Dead(),
            onEvent=on_event,
            onLine=on_line,
        )

    monkeypatch.setattr(hub_app.children, "launch", fake_launch)
    monkeypatch.setattr(hub_app.children, "discard_staging", lambda path, pid: True)

    app = create_hub_app(auth_token=TOKEN, assets_dir=tmp_path / "no-assets")
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def test_a_failing_run_leaves_the_provider_configuration_byte_identical(client, hub_home, tmp_path):
    before = fingerprint(hub_home)
    repository = tmp_path / "project"
    repository.mkdir()

    client.post("/api/runs", json={"path": str(repository)}, headers=AUTH)
    import time

    time.sleep(0.4)

    assert fingerprint(hub_home) == before, "the hub rewrote the user's provider configuration"


def test_reading_the_run_log_does_not_touch_the_configuration(client, hub_home):
    before = fingerprint(hub_home)

    client.get("/api/run-log", headers=AUTH)
    client.get("/api/repositories", headers=AUTH)

    assert fingerprint(hub_home) == before


def test_the_hub_exposes_no_route_that_writes_configuration(client):
    """Provider editing is feature 038. There should be nothing here to call."""
    app_routes = {
        getattr(route, "path", "") for route in client.app.routes if hasattr(route, "path")
    }

    assert not any("provider" in path or "config" in path for path in app_routes)
