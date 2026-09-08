"""The analyse history, derived by scanning `~/.codepedia/repos/`.

The filtering is the point. That directory accumulates `<state_id>.staging-<pid>`
residue from runs that never finished - seven against four real entries on the
machine this was built for - and every one of them would otherwise appear as a
phantom repository (spec FR-030, SC-005).
"""

from __future__ import annotations

import sqlite3

import pytest

from cli import paths as cli_paths
from hub_server import history


@pytest.fixture()
def repos(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".codepedia"
    (home / "repos").mkdir(parents=True)
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: home)
    return home / "repos"


def make_entry(repos_dir, state_id: str, root_path: str, last_indexed_at: str) -> None:
    """Write the minimum a state directory needs to be listable."""
    directory = repos_dir / state_id
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "repository-metadata.sqlite")
    connection.execute(
        "CREATE TABLE repositories (root_path TEXT NOT NULL UNIQUE, last_indexed_at TEXT)"
    )
    connection.execute(
        "INSERT INTO repositories (root_path, last_indexed_at) VALUES (?, ?)",
        (root_path, last_indexed_at),
    )
    connection.commit()
    connection.close()


def test_lists_an_analysed_repository(repos, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    make_entry(repos, "0123456789abcdef", str(root), "2026-09-01T10:00:00")

    entries = history.list_entries()

    assert len(entries) == 1
    assert entries[0].stateId == "0123456789abcdef"
    assert entries[0].repositoryPath == str(root)
    assert entries[0].lastIndexedAt == "2026-09-01T10:00:00"
    assert entries[0].available is True


def test_staging_residue_never_appears_as_a_repository(repos, tmp_path):
    """Spec FR-030 and SC-005, against the exact shape seen in the wild."""
    root = tmp_path / "project"
    root.mkdir()
    make_entry(repos, "3d82e509c5da9263", str(root), "2026-09-01T10:00:00")

    # Residue, complete with a readable database - matching what a killed run
    # actually leaves behind, so the filter cannot pass by accident.
    for pid in (16056, 18600, 24652):
        make_entry(repos, f"3d82e509c5da9263.staging-{pid}", str(root), "2026-09-01T09:00:00")

    entries = history.list_entries()

    assert len(entries) == 1
    assert entries[0].stateId == "3d82e509c5da9263"


@pytest.mark.parametrize(
    "name",
    [
        "3d82e509c5da9263.staging-1",
        "0123456789abcdeF",  # uppercase: not what state_id produces
        "0123456789abcde",  # 15 chars
        "0123456789abcdef0",  # 17 chars
        "not-a-state-id",
        "docs",
        ".tmp",
    ],
)
def test_only_exact_state_id_directories_are_listed(repos, tmp_path, name):
    root = tmp_path / "project"
    root.mkdir()
    make_entry(repos, name, str(root), "2026-09-01T10:00:00")

    assert history.list_entries() == []


def test_an_unreadable_entry_does_not_cost_the_others(repos, tmp_path):
    """Spec FR-031: one damaged database must not hide every other repository."""
    root = tmp_path / "project"
    root.mkdir()
    make_entry(repos, "aaaaaaaaaaaaaaaa", str(root), "2026-09-01T10:00:00")

    broken = repos / "bbbbbbbbbbbbbbbb"
    broken.mkdir()
    (broken / "repository-metadata.sqlite").write_bytes(b"not a database at all")

    # A directory with the right name and no database at all.
    (repos / "cccccccccccccccc").mkdir()

    entries = history.list_entries()

    assert [entry.stateId for entry in entries] == ["aaaaaaaaaaaaaaaa"]


def test_entries_are_ordered_newest_first(repos, tmp_path):
    for index, stamp in enumerate(["2026-09-01T10:00:00", "2026-09-03T10:00:00", "2026-09-02T10:00:00"]):
        root = tmp_path / f"project{index}"
        root.mkdir()
        make_entry(repos, f"{index:016x}", str(root), stamp)

    entries = history.list_entries()

    assert [entry.lastIndexedAt for entry in entries] == [
        "2026-09-03T10:00:00",
        "2026-09-02T10:00:00",
        "2026-09-01T10:00:00",
    ]


def test_a_repository_whose_folder_is_gone_stays_listed_but_marked(repos, tmp_path):
    """Spec FR-031b: its documentation is still readable, so hiding it would
    strand generated output with no way to reach or remove it."""
    make_entry(repos, "dddddddddddddddd", str(tmp_path / "deleted-project"), "2026-09-01T10:00:00")

    entries = history.list_entries()

    assert len(entries) == 1
    assert entries[0].available is False


def test_two_paths_with_identical_content_are_two_separate_entries(repos, tmp_path):
    """Spec FR-031a: path is identity, and a move is deliberately not detected.

    Pinned so nobody later adds content-based matching unopposed - a wrong match
    would silently attach one project's documentation to another.
    """
    original = tmp_path / "project"
    moved = tmp_path / "project-renamed"
    for folder in (original, moved):
        folder.mkdir()
        (folder / "main.py").write_text("print('same content')", encoding="utf-8")

    make_entry(repos, "1111111111111111", str(original), "2026-09-01T10:00:00")
    make_entry(repos, "2222222222222222", str(moved), "2026-09-02T10:00:00")

    entries = history.list_entries()

    assert len(entries) == 2
    assert {entry.repositoryPath for entry in entries} == {str(original), str(moved)}


def test_no_repos_directory_yields_an_empty_listing(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: tmp_path / "nothing-here")

    assert history.list_entries() == []


# -- removal ---------------------------------------------------------------


def test_remove_deletes_only_the_state_directory(repos, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('hello')", encoding="utf-8")
    make_entry(repos, "eeeeeeeeeeeeeeee", str(root), "2026-09-01T10:00:00")

    assert history.remove("eeeeeeeeeeeeeeee") is True

    assert not (repos / "eeeeeeeeeeeeeeee").exists()
    # Constitution 2.7: the analysed repository is never touched.
    assert (root / "main.py").read_text(encoding="utf-8") == "print('hello')"
    assert history.list_entries() == []


@pytest.mark.parametrize("state_id", ["../escape", "not-hex", "", "aaaa/bbbb"])
def test_remove_refuses_anything_that_is_not_a_state_id(repos, state_id):
    """The pattern check is what keeps a crafted id from escaping the directory."""
    assert history.remove(state_id) is False


def test_remove_of_an_unknown_state_id_is_a_no_op(repos):
    assert history.remove("ffffffffffffffff") is False
