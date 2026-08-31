"""What `codepedia index` and `codepedia serve` hand the user at startup.

`start_local_server` is the single place both commands go through, so it is
where the token is minted, printed, and matched to the bind address. A token
that never reaches the terminal locks the user out of their own chat panel;
allowed hosts that omit the bind address lock out every request.
"""

from __future__ import annotations

from pathlib import Path

import cli.server
from chat_api.security import DEFAULT_ALLOWED_HOSTS, TOKEN_QUERY_PARAM


def _capture(monkeypatch, host: str):
    """Run `start_local_server` without binding, returning (printed, kwargs)."""
    printed: list[str] = []
    captured: dict = {}

    def fake_create_app(*args, **kwargs):
        captured.update(kwargs)

        class _App:
            state = type("S", (), {})()

        return _App()

    monkeypatch.setattr(cli.server, "create_app", fake_create_app)
    monkeypatch.setattr(cli.server.typer, "echo", lambda line: printed.append(line))
    monkeypatch.setattr(cli.server.uvicorn, "run", lambda app, *, host, port: None)

    cli.server.start_local_server(None, None, None, Path("docs"), host, 8000)
    return printed, captured


def test_the_printed_url_carries_a_token_the_app_was_built_with(monkeypatch):
    printed, kwargs = _capture(monkeypatch, "127.0.0.1")

    token = kwargs["auth_token"]
    assert token
    expected_url = f"http://127.0.0.1:8000/?{TOKEN_QUERY_PARAM}={token}"
    assert printed[0] == f"Documentation wiki available at {expected_url}"
    assert not any(line.startswith("WARNING") for line in printed)


def test_a_loopback_bind_allows_only_loopback_hosts(monkeypatch):
    _, kwargs = _capture(monkeypatch, "127.0.0.1")

    assert tuple(kwargs["allowed_hosts"]) == DEFAULT_ALLOWED_HOSTS


def test_a_lan_bind_is_warned_about_and_still_allowed_as_a_host(monkeypatch):
    printed, kwargs = _capture(monkeypatch, "192.168.1.20")

    assert any(line.startswith("WARNING: bound to 192.168.1.20") for line in printed)
    # The warning must not also break the server it warns about.
    assert "192.168.1.20" in tuple(kwargs["allowed_hosts"])


def test_each_run_mints_its_own_token(monkeypatch):
    _, first = _capture(monkeypatch, "127.0.0.1")
    _, second = _capture(monkeypatch, "127.0.0.1")

    assert first["auth_token"] != second["auth_token"]
