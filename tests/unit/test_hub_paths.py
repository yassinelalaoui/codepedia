"""Validating a repository path submitted from a browser.

Spec FR-009 and constitution 2.7. Everything downstream trusts the path this
returns, so both halves matter: what it refuses, and what it must *not* refuse
just because the path is spelled awkwardly.
"""

from __future__ import annotations

import sys

import pytest

from cli import paths as cli_paths
from hub_server.paths import InvalidRepositoryPathError, validate_submitted_path


@pytest.fixture()
def hub_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".codepedia"
    home.mkdir(parents=True)
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: home)
    return home


# -- rejections -------------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   ", "\t", None])
def test_empty_path_is_refused(raw, hub_home):
    with pytest.raises(InvalidRepositoryPathError) as caught:
        validate_submitted_path(raw)
    assert "Enter the path" in str(caught.value)


def test_missing_path_is_refused_by_name(tmp_path, hub_home):
    missing = tmp_path / "nowhere"

    with pytest.raises(InvalidRepositoryPathError) as caught:
        validate_submitted_path(str(missing))

    assert "nothing at" in str(caught.value)


def test_a_file_is_refused_with_a_message_that_says_so(tmp_path, hub_home):
    target = tmp_path / "a-file.txt"
    target.write_text("hello", encoding="utf-8")

    with pytest.raises(InvalidRepositoryPathError) as caught:
        validate_submitted_path(str(target))

    # Spec FR-010 and SC-004: a person must be able to tell what to do next.
    assert "file, not a folder" in str(caught.value)


def test_the_state_directory_itself_is_refused(hub_home):
    with pytest.raises(InvalidRepositoryPathError) as caught:
        validate_submitted_path(str(hub_home))

    assert "Codepedia's own storage" in str(caught.value)


def test_a_directory_inside_the_state_directory_is_refused(hub_home):
    """Analysing into your own output would make every generated page a source
    file for the next run (constitution 2.7)."""
    nested = hub_home / "repos" / "abcdef0123456789"
    nested.mkdir(parents=True)

    with pytest.raises(InvalidRepositoryPathError):
        validate_submitted_path(str(nested))


def test_dot_dot_cannot_be_used_to_reach_the_state_directory(hub_home):
    """Resolution happens before any comparison, so a differently-spelled path
    to a refused location is refused just the same."""
    (hub_home / "repos").mkdir(parents=True, exist_ok=True)

    # Resolves back to the state directory itself.
    with pytest.raises(InvalidRepositoryPathError):
        validate_submitted_path(str(hub_home / "repos" / ".."))


# -- awkward but valid ------------------------------------------------------


def test_a_path_with_spaces_is_accepted(tmp_path, hub_home):
    target = tmp_path / "my repository folder"
    target.mkdir()

    assert validate_submitted_path(str(target)) == target.resolve()


def test_a_path_with_non_ascii_is_accepted(tmp_path, hub_home):
    target = tmp_path / "dépôt-日本語"
    target.mkdir()

    assert validate_submitted_path(str(target)) == target.resolve()


def test_a_trailing_separator_is_accepted_and_normalised(tmp_path, hub_home):
    target = tmp_path / "repo"
    target.mkdir()

    assert validate_submitted_path(f"{target}{'/'}") == target.resolve()


def test_dot_dot_inside_an_otherwise_valid_path_is_resolved(tmp_path, hub_home):
    target = tmp_path / "repo"
    target.mkdir()
    (tmp_path / "sibling").mkdir()

    resolved = validate_submitted_path(str(tmp_path / "sibling" / ".." / "repo"))

    assert resolved == target.resolve()


def test_a_relative_path_is_resolved_against_the_working_directory(tmp_path, hub_home, monkeypatch):
    target = tmp_path / "repo"
    target.mkdir()
    monkeypatch.chdir(tmp_path)

    assert validate_submitted_path("repo") == target.resolve()


def test_a_home_relative_path_is_expanded(tmp_path, hub_home, monkeypatch):
    fake_home = tmp_path / "userhome"
    (fake_home / "code").mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("HOME", str(fake_home))

    assert validate_submitted_path("~/code") == (fake_home / "code").resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs elevation on Windows")
def test_a_symlink_is_resolved_to_its_target(tmp_path, hub_home):
    real = tmp_path / "real-repo"
    real.mkdir()
    link = tmp_path / "link-to-repo"
    link.symlink_to(real, target_is_directory=True)

    assert validate_submitted_path(str(link)) == real.resolve()


def test_the_returned_path_is_absolute_and_resolved(tmp_path, hub_home, monkeypatch):
    target = tmp_path / "repo"
    target.mkdir()
    monkeypatch.chdir(tmp_path)

    resolved = validate_submitted_path("./repo/")

    assert resolved.is_absolute()
    assert ".." not in resolved.parts
