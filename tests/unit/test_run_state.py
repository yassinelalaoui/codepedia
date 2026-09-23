"""Folding progress events into the run's state (data-model.md §1)."""

from __future__ import annotations

import json

from cli.progress_stream import SENTINEL
from hub_server.progress_parse import parse_line
from hub_server.runs import CANCELLED, SUCCEEDED, RunState


def event(**payload):
    return parse_line(f"{SENTINEL} {json.dumps(payload)}")


def new_run() -> RunState:
    return RunState(runId="r1", kind="index", repositoryPath="C:/repo")


def stage(run: RunState, name: str):
    return next(item for item in run.stages if item.name == name)


def test_all_ten_stages_are_present_from_the_start():
    run = new_run()

    assert len(run.stages) == 10
    assert [item.name for item in run.stages][:3] == ["VALIDATING", "CHECKING_MODELS", "SCANNING"]
    assert all(item.status == "pending" for item in run.stages)


def test_starting_a_stage_marks_it_running():
    run = new_run()

    run.apply(event(seq=1, type="stage", stage="SCANNING", label="Scanning repository"))

    assert stage(run, "SCANNING").status == "running"
    assert run.currentStage == "SCANNING"


def test_a_later_stage_starting_finishes_the_earlier_ones():
    """The pipeline is strictly ordered, so a stage starting is proof its
    predecessors finished - even if their `stage_end` was lost."""
    run = new_run()

    run.apply(event(seq=1, type="stage", stage="SUMMARIZING", label="Generating summaries"))

    assert stage(run, "VALIDATING").status == "done"
    assert stage(run, "SCANNING").status == "done"
    assert stage(run, "SUMMARIZING").status == "running"
    assert stage(run, "EMBEDDING").status == "pending"


def test_stage_end_records_the_duration():
    run = new_run()
    run.apply(event(seq=1, type="stage", stage="PARSING", label="Parsing"))
    run.apply(event(seq=2, type="stage_end", stage="PARSING", elapsedSeconds=4.125))

    assert stage(run, "PARSING").status == "done"
    assert stage(run, "PARSING").elapsedSeconds == 4.125


def test_item_counts_land_on_the_named_stage():
    run = new_run()
    run.apply(event(seq=1, type="stage", stage="SUMMARIZING", label="Generating summaries"))
    run.apply(event(seq=2, type="items", stage="SUMMARIZING", completed=37, total=412))

    assert stage(run, "SUMMARIZING").completed == 37
    assert stage(run, "SUMMARIZING").total == 412
    assert stage(run, "EMBEDDING").completed is None


def test_version_increases_on_every_mutation():
    """What the progress stream polls - a snapshot is only re-sent when this
    moves (research.md §4)."""
    run = new_run()
    versions = [run.version]

    for seq, payload in enumerate(
        [
            dict(type="stage", stage="SCANNING", label="Scanning repository"),
            dict(type="items", stage="SUMMARIZING", completed=1, total=9),
            dict(type="items", stage="SUMMARIZING", completed=2, total=9),
        ],
        start=1,
    ):
        run.apply(event(seq=seq, **payload))
        versions.append(run.version)

    assert versions == sorted(versions)
    assert len(set(versions)) == len(versions)


def test_failed_event_records_the_diagnosis_without_terminating_the_run():
    """The child's exit code decides termination, not this event
    (contracts/run-progress-stream.md, reader obligation 6)."""
    run = new_run()
    run.apply(event(seq=1, type="stage", stage="EMBEDDING", label="Updating embeddings"))
    run.apply(
        event(
            seq=2,
            type="failed",
            stage="EMBEDDING",
            message="The model for the 'embeddings' stage is not available.",
        )
    )

    assert run.failedStage == "EMBEDDING"
    assert run.failureMessage == "The model for the 'embeddings' stage is not available."
    assert run.outcome is None, "a diagnosis is not a terminal state"


def test_finish_sets_the_outcome_exactly_once():
    """Spec FR-021, and the reason cancelling is trustworthy: a child that dies
    a moment after Stop must not relabel the run as failed."""
    run = new_run()

    run.finish(CANCELLED, message="You stopped this analysis.")
    run.finish("failed", message="something else")

    assert run.outcome == CANCELLED
    assert "stopped" in run.failureMessage


def test_a_terminal_run_reports_that_nothing_was_kept():
    """Spec FR-023 - the sentence a column of ticked stages would otherwise
    contradict."""
    failed = new_run()
    failed.finish("failed")
    cancelled = new_run()
    cancelled.finish(CANCELLED)
    succeeded = new_run()
    succeeded.finish(SUCCEEDED)

    assert failed.snapshot()["discardedEverything"] is True
    assert cancelled.snapshot()["discardedEverything"] is True
    assert succeeded.snapshot()["discardedEverything"] is False


def test_finishing_leaves_no_stage_still_running():
    run = new_run()
    run.apply(event(seq=1, type="stage", stage="EMBEDDING", label="Updating embeddings"))

    run.finish("failed")

    assert stage(run, "EMBEDDING").status == "failed"
    assert run.currentStage is None
    assert all(item.status != "running" for item in run.stages)


def test_snapshot_is_a_copy_not_the_live_object():
    run = new_run()
    snapshot = run.snapshot()
    run.apply(event(seq=1, type="stage", stage="SCANNING", label="Scanning repository"))

    assert snapshot["currentStage"] is None
    assert run.snapshot()["currentStage"] == "SCANNING"


def test_unknown_event_types_are_ignored():
    run = new_run()
    before = run.version

    run.apply(event(seq=1, type="server_ready", url="http://127.0.0.1:9/?token=x"))

    assert run.serverUrl == "http://127.0.0.1:9/?token=x"
    assert run.version > before
