"""Parsing a child's stdout (contracts/run-progress-stream.md).

Every test here is really about the same property: `parse_line` is total. The
thread calling it is the thread keeping the child's pipe drained, so an
exception would fill the pipe and hang the child (research.md §7). "Return
None" is the only acceptable failure mode.
"""

from __future__ import annotations

import json

import pytest

from cli.progress_stream import SENTINEL
from hub_server.progress_parse import ProgressEvent, is_event_line, parse_line


def line(**payload) -> str:
    return f"{SENTINEL} {json.dumps(payload)}"


def test_recognises_an_event_line():
    assert is_event_line(line(seq=1, type="stage", stage="SCANNING")) is True


@pytest.mark.parametrize(
    "text",
    [
        "Scanning repository",
        "  [12/340] function do_thing",
        "",
        "   ",
        "@@CODEPEDIA@@ {}",
        "prefixed @@CODEPEDIA_PROGRESS@@ {}",
    ],
)
def test_ordinary_output_is_not_an_event(text):
    assert is_event_line(text) is False
    assert parse_line(text) is None


def test_parses_a_stage_event():
    event = parse_line(line(seq=3, type="stage", stage="SUMMARIZING", label="Generating summaries"))

    assert isinstance(event, ProgressEvent)
    assert event.seq == 3
    assert event.type == "stage"
    assert event.stage == "SUMMARIZING"
    assert event.get("label") == "Generating summaries"


def test_parses_an_items_event():
    event = parse_line(line(seq=9, type="items", stage="EMBEDDING", completed=4, total=11))

    assert event is not None
    assert event.get("completed") == 4
    assert event.get("total") == 11


def test_parses_a_failed_event_keeping_its_extra_payload_fields():
    """Unknown fields survive parsing rather than being dropped.

    The parser knows a fixed set of event types, not a fixed set of fields, so
    a producer can add detail without this module changing.
    """
    event = parse_line(
        line(
            seq=40,
            type="failed",
            stage="EMBEDDING",
            message="The model for the 'embeddings' stage is not available.",
            detail="ollama is not running",
        )
    )

    assert event is not None
    assert event.stage == "EMBEDDING"
    assert event.get("detail") == "ollama is not running"


def test_parses_server_ready():
    event = parse_line(line(seq=51, type="server_ready", url="http://127.0.0.1:51734/?token=abc"))

    assert event is not None
    assert event.get("url") == "http://127.0.0.1:51734/?token=abc"


def test_parses_catchup():
    event = parse_line(line(seq=2, type="catchup", phase="parsing", completed=3, total=11, path="a.py"))

    assert event is not None
    assert event.type == "catchup"
    assert event.get("path") == "a.py"


@pytest.mark.parametrize(
    "text",
    [
        f"{SENTINEL} not json at all",
        f"{SENTINEL} {{",
        f"{SENTINEL} ",
        f"{SENTINEL}",
        f"{SENTINEL} []",
        f"{SENTINEL} 42",
        f'{SENTINEL} "a string"',
        f"{SENTINEL} null",
    ],
)
def test_malformed_event_lines_return_none_rather_than_raising(text):
    assert parse_line(text) is None


def test_missing_or_non_integer_seq_is_rejected():
    assert parse_line(f'{SENTINEL} {{"type": "stage"}}') is None
    assert parse_line(f'{SENTINEL} {{"seq": "3", "type": "stage"}}') is None
    # `True` is an int in Python, which would sneak through a naive check.
    assert parse_line(f'{SENTINEL} {{"seq": true, "type": "stage"}}') is None


def test_unknown_event_type_is_ignored_for_forward_compatibility():
    """A newer child must not break an older hub."""
    assert parse_line(line(seq=1, type="something_invented_later", detail="x")) is None


def test_unknown_stage_is_dropped_but_the_event_survives():
    """A `failed` event still carries a usable message and provider list even
    when it names a stage this version has never heard of."""
    event = parse_line(line(seq=7, type="failed", stage="TIME_TRAVELLING", message="boom", providers=[]))

    assert event is not None
    assert event.stage is None
    assert event.get("message") == "boom"


def test_replacement_characters_from_a_bad_decode_do_not_raise():
    """Child output is decoded with `errors="replace"`, so this is what a
    mangled byte actually looks like by the time it reaches the parser."""
    assert parse_line("�� garbage") is None
    assert parse_line(f"{SENTINEL} ��") is None
