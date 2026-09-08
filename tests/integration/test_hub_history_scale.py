"""Spec SC-006: the listing appears within 2 seconds at 20 repositories.

This is the bar research.md §6 relies on when it argues the derived scan needs
no cache in front of it. The argument was that N small SQLite opens is nothing
at this scale - and an argument about performance that nothing measures is just
an opinion, so this measures it.

If it ever fails, the conclusion to revisit is the *cache decision*, not this
criterion.
"""

from __future__ import annotations

import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from chat_api.security import TOKEN_HEADER
from cli import paths as cli_paths
from hub_server import history
from hub_server.app import create_hub_app

TOKEN = "scale-token"
AUTH = {TOKEN_HEADER: TOKEN}

REPOSITORY_COUNT = 20
BUDGET_SECONDS = 2.0


@pytest.fixture()
def populated_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".codepedia"
    repos = home / "repos"
    repos.mkdir(parents=True)
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: home)

    for index in range(REPOSITORY_COUNT):
        root = tmp_path / f"project-{index:02d}"
        root.mkdir()
        directory = repos / f"{index:016x}"
        directory.mkdir()
        connection = sqlite3.connect(directory / "repository-metadata.sqlite")
        connection.execute(
            "CREATE TABLE repositories (root_path TEXT NOT NULL UNIQUE, last_indexed_at TEXT)"
        )
        connection.execute(
            "INSERT INTO repositories (root_path, last_indexed_at) VALUES (?, ?)",
            (str(root), f"2026-09-{(index % 28) + 1:02d}T10:00:00"),
        )
        connection.commit()
        connection.close()

    # Residue too: the scan has to skip these, and skipping is not free.
    for index in range(10):
        (repos / f"{index:016x}.staging-{1000 + index}").mkdir()

    return home


def test_the_scan_lists_twenty_repositories_within_the_budget(populated_home):
    started = time.perf_counter()
    entries = history.list_entries()
    elapsed = time.perf_counter() - started

    assert len(entries) == REPOSITORY_COUNT
    assert elapsed < BUDGET_SECONDS, (
        f"the derived history scan took {elapsed:.2f}s for {REPOSITORY_COUNT} repositories, "
        f"over the {BUDGET_SECONDS}s budget in spec SC-006 - revisit research.md §6's "
        "decision not to cache it"
    )


def test_the_endpoint_answers_within_the_budget(populated_home, tmp_path):
    app = create_hub_app(auth_token=TOKEN, assets_dir=tmp_path / "no-assets")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        started = time.perf_counter()
        response = client.get("/api/repositories", headers=AUTH)
        elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert len(response.json()["repositories"]) == REPOSITORY_COUNT
    assert elapsed < BUDGET_SECONDS


def test_residue_is_excluded_even_at_scale(populated_home):
    """Spec FR-030 and SC-005, with the residue outnumbering nothing by accident."""
    entries = history.list_entries()

    assert all(".staging-" not in entry.stateId for entry in entries)
    assert len(entries) == REPOSITORY_COUNT
