"""What a full, successful run puts on the progress channel.

`test_cli_output_unchanged.py` proves the channel is silent unless asked. This
proves that when it is asked, what comes out is enough to draw the homepage's
bar: every stage in pipeline order, item counts that rise inside the two stages
that dominate the wall clock, and a terminal event on failure.

The fixtures come from `test_cli.py` rather than being duplicated here - they
are the established way this suite runs the real pipeline against in-memory
engine doubles, which matters because no provider chain completes on the
machine this feature was built for (research.md §11).
"""

from __future__ import annotations

import json

import pytest

from cli import progress_stream
from cli.errors import LocalModelUnavailableError
from cli.index_command import Stage, run_index

# Imported for their fixture side effect: pytest resolves fixtures by module
# attribute, so importing them here registers them for this module.
from integration.test_cli import (  # noqa: F401 - fixtures
    _copy_fixture_repo,
    _local_config,
    cli_home,
    fake_engines,
)

STAGE_ORDER = [stage.name for stage in Stage]


@pytest.fixture()
def events(monkeypatch, capsys):
    """Collect the parsed events a block of pipeline work emits."""
    monkeypatch.setenv(progress_stream.ENV_VAR, "1")

    def drain() -> list[dict]:
        out = capsys.readouterr().out
        return [
            json.loads(line.split(" ", 1)[1])
            for line in out.splitlines()
            if line.startswith(progress_stream.SENTINEL)
        ]

    return drain


def test_full_run_emits_every_stage_in_pipeline_order(tmp_path, cli_home, fake_engines, events):
    root = _copy_fixture_repo(tmp_path)

    result = run_index(root, config=_local_config())
    result.vectorIndex.close()

    emitted = events()
    stages = [event["stage"] for event in emitted if event["type"] == "stage"]

    # A subsequence check, not equality: STARTING_SERVER belongs to the command
    # that serves the result, not to run_index, and a stage list that gained an
    # entry should not fail this test - drifting *out of order* should.
    positions = [STAGE_ORDER.index(name) for name in stages]
    assert positions == sorted(positions), f"stages emitted out of pipeline order: {stages}"
    assert "VALIDATING" in stages, "the stage announced outside _stage was missed"
    assert "CHECKING_MODELS" in stages, "the second stage announced outside _stage was missed"
    assert "SUMMARIZING" in stages
    assert "EMBEDDING" in stages


def test_every_started_stage_reports_its_duration(tmp_path, cli_home, fake_engines, events):
    root = _copy_fixture_repo(tmp_path)

    result = run_index(root, config=_local_config())
    result.vectorIndex.close()

    emitted = events()
    ended = {event["stage"] for event in emitted if event["type"] == "stage_end"}
    assert ended, "no stage reported a duration"
    for event in emitted:
        if event["type"] == "stage_end":
            assert isinstance(event["elapsedSeconds"], (int, float))
            assert event["elapsedSeconds"] >= 0


def test_item_progress_rises_within_a_stage(tmp_path, cli_home, fake_engines, events):
    """Spec FR-015: the bar has to move *inside* a stage, not only between them.

    Summarization dominates a real run, so a display that only advanced on a
    stage change would sit still for most of it.
    """
    root = _copy_fixture_repo(tmp_path)

    result = run_index(root, config=_local_config())
    result.vectorIndex.close()

    items = [event for event in events() if event["type"] == "items"]
    assert items, "no within-stage progress was reported at all"

    for stage_name in {event["stage"] for event in items}:
        completed = [event["completed"] for event in items if event["stage"] == stage_name]
        assert completed == sorted(completed), f"{stage_name} progress went backwards"
        for event in items:
            if event["stage"] == stage_name:
                assert 1 <= event["completed"] <= event["total"]


def test_seq_is_unique_and_ordered_across_a_whole_run(tmp_path, cli_home, fake_engines, events):
    root = _copy_fixture_repo(tmp_path)

    result = run_index(root, config=_local_config())
    result.vectorIndex.close()

    seqs = [event["seq"] for event in events()]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


def test_unavailable_provider_emits_a_failed_event_naming_the_chain(tmp_path, cli_home, monkeypatch, events):
    """Spec FR-022: name the stage, and name what was tried.

    This is the path every run takes on a machine whose embedding chain cannot
    be reached, so the diagnosis it carries is not an edge case.
    """
    root = _copy_fixture_repo(tmp_path)
    config = _local_config()

    import cli.index_command as index_command

    def unavailable(**_: object) -> None:
        raise LocalModelUnavailableError(
            "No provider in the 'embeddings' chain is currently available. Start the local "
            "service, install the required model, or check your remote provider credentials, "
            "then try again."
        )

    monkeypatch.setattr(index_command, "check_ai_dependencies", unavailable)

    with pytest.raises(LocalModelUnavailableError):
        run_index(root, config=config)

    failures = [event for event in events() if event["type"] == "failed"]
    assert len(failures) == 1
    failure = failures[0]
    assert failure["stage"] == "CHECKING_MODELS"
    assert failure["chain"] == "embeddings"
    assert "embeddings" in failure["message"]
    # The providers actually configured for that chain, so the homepage can say
    # which ones were tried rather than only that something was unavailable.
    assert failure["providers"] == list(config.embeddingChain)
