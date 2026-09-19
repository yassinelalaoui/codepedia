"""The API token this machine keeps between runs (`cli.tokens`).

The point of storing it at all is that a reader opens the printed URL once and
then reaches the server from any window, so the value must survive a restart,
and the hub must never be unlocked by the wiki's copy.
"""

from __future__ import annotations

import json
import os
import stat

import pytest

import cli.paths as cli_paths
from cli import tokens as tokens_module


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Redirect `~/.codepedia`, the way `cli.paths` documents."""
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: tmp_path / ".codepedia")
    return tmp_path / ".codepedia"


def test_the_same_token_comes_back_on_the_next_run():
    """What makes the bare URL work in a window opened after a restart."""
    first = tokens_module.load_or_create_token("hub")
    second = tokens_module.load_or_create_token("hub")

    assert first == second
    assert first


def test_the_hub_and_the_wiki_never_share_a_token():
    """They authorise different things: the hub can start and delete analyses,
    and the wiki is the origin that renders a documented repository."""
    assert tokens_module.load_or_create_token("hub") != tokens_module.load_or_create_token("wiki")


@pytest.mark.skipif(os.name == "nt", reason="Windows ignores the POSIX mode; the user-profile ACL protects it there")
def test_a_stored_token_is_readable_by_this_user_only(home):
    tokens_module.load_or_create_token("hub")
    mode = stat.S_IMODE(os.stat(home / "tokens.json").st_mode)

    assert not mode & stat.S_IRGRP and not mode & stat.S_IROTH, oct(mode)


def test_a_corrupt_file_is_replaced_rather_than_fatal(home):
    home.mkdir(parents=True)
    (home / "tokens.json").write_text("{not json", encoding="utf-8")

    token = tokens_module.load_or_create_token("wiki")

    assert token
    assert json.loads((home / "tokens.json").read_text(encoding="utf-8"))["wiki"] == token


def test_a_home_that_cannot_be_written_still_yields_a_working_token(monkeypatch):
    """A read-only home costs the reuse, never the ability to serve."""
    def refuse(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(tokens_module.os, "open", refuse)

    assert tokens_module.load_or_create_token("hub")


def test_the_hint_names_the_address_that_works_afterwards():
    hint = tokens_module.reuse_hint("127.0.0.1", 8100)

    assert "http://127.0.0.1:8100/" in hint
    assert "any window" in hint
