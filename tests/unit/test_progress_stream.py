"""The env-gated progress emitter (contracts/run-progress-stream.md).

The first tests here are the important ones: with the variable unset, nothing is
written at all. That is what makes spec FR-002's "the CLI behaves exactly as
before" a mechanical property rather than an argument.
"""

from __future__ import annotations

import json

import pytest

from cli import progress_stream


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(progress_stream.ENV_VAR, raising=False)


def test_emits_nothing_when_variable_unset(capsys):
    progress_stream.emit("stage", stage="SUMMARIZING", label="Generating summaries")

    assert capsys.readouterr().out == ""


def test_emits_nothing_when_variable_set_to_something_else(monkeypatch, capsys):
    # Only "1" enables it. An inherited "0" or "false" from a parent shell must
    # not turn a person's own `codepedia index` into a machine-readable stream.
    monkeypatch.setenv(progress_stream.ENV_VAR, "0")

    progress_stream.emit("stage", stage="SCANNING", label="Scanning repository")

    assert capsys.readouterr().out == ""


def test_emits_one_sentinel_line_when_enabled(monkeypatch, capsys):
    monkeypatch.setenv(progress_stream.ENV_VAR, "1")

    progress_stream.emit("items", stage="SUMMARIZING", completed=37, total=412)

    out = capsys.readouterr().out
    assert out.endswith("\n")
    lines = out.splitlines()
    assert len(lines) == 1

    prefix, payload = lines[0].split(" ", 1)
    assert prefix == progress_stream.SENTINEL
    event = json.loads(payload)
    assert event["type"] == "items"
    assert event["stage"] == "SUMMARIZING"
    assert event["completed"] == 37
    assert event["total"] == 412


def test_seq_increases_monotonically(monkeypatch, capsys):
    monkeypatch.setenv(progress_stream.ENV_VAR, "1")

    for _ in range(5):
        progress_stream.emit("items", stage="EMBEDDING", completed=1, total=9)

    seqs = [json.loads(line.split(" ", 1)[1])["seq"] for line in capsys.readouterr().out.splitlines()]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 5


@pytest.mark.parametrize(
    "hostile",
    [
        "line one\nline two",
        "carriage\rreturn",
        "cafe uber ...",
        'quotes "and" \\backslashes\\',
        "tab\tseparated",
    ],
)
def test_hostile_payload_still_yields_exactly_one_ascii_line(monkeypatch, capsys, hostile):
    """A repository path or symbol name can contain anything.

    JSON escaping with `ensure_ascii` is what guarantees the reader's
    one-line-per-event contract holds regardless of what the pipeline hands us -
    a raw newline in a file path would otherwise split one event into two
    unparseable halves.
    """
    monkeypatch.setenv(progress_stream.ENV_VAR, "1")

    progress_stream.emit("catchup", completed=1, total=2, path=hostile)

    out = capsys.readouterr().out
    assert len(out.splitlines()) == 1
    assert out.isascii()
    event = json.loads(out.splitlines()[0].split(" ", 1)[1])
    assert event["path"] == hostile


def test_non_ascii_payload_is_escaped_into_one_ascii_line(monkeypatch, capsys):
    """Non-ASCII is kept out of the source file but exercised at runtime."""
    monkeypatch.setenv(progress_stream.ENV_VAR, "1")
    non_ascii = "café über 日本語"

    progress_stream.emit("catchup", completed=1, total=2, path=non_ascii)

    out = capsys.readouterr().out
    assert len(out.splitlines()) == 1
    assert out.isascii()
    assert json.loads(out.splitlines()[0].split(" ", 1)[1])["path"] == non_ascii


def test_enabled_reflects_the_environment_at_call_time(monkeypatch):
    assert progress_stream.enabled() is False
    monkeypatch.setenv(progress_stream.ENV_VAR, "1")
    assert progress_stream.enabled() is True
