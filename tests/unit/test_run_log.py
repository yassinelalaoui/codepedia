"""The durable run log (data-model.md §2, spec FR-026a-e).

The behaviour worth pinning is not the round-trip - it is the two failure paths:
a hub that died mid-run must not leave a run reading as in-progress forever, and
a log this version cannot read must not stop the homepage loading.
"""

from __future__ import annotations

import sqlite3

import pytest

from cli import paths as cli_paths
from hub_server.run_log import RETAINED_RUNS, RunLog, run_log_path


@pytest.fixture()
def log(tmp_path, monkeypatch) -> RunLog:
    home = tmp_path / "home" / ".codepedia"
    home.mkdir(parents=True)
    monkeypatch.setattr(cli_paths, "codepedia_home", lambda: home)
    return RunLog()


def test_a_started_run_is_recorded_with_no_outcome(log):
    log.append(run_id="r1", repository_path="C:/repo", kind="index")

    records = log.recent()
    assert len(records) == 1
    assert records[0].runId == "r1"
    assert records[0].outcome is None
    assert records[0].endedAt is None


def test_closing_a_run_records_its_diagnosis(log):
    log.append(run_id="r1", repository_path="C:/repo", kind="index")
    log.close(
        run_id="r1",
        outcome="failed",
        failed_stage="EMBEDDING",
        failure_message="The model for the 'embeddings' stage is not available.",
    )

    record = log.recent()[0]
    assert record.outcome == "failed"
    assert record.failedStage == "EMBEDDING"
    assert "embeddings" in record.failureMessage
    assert record.endedAt is not None


def test_recent_returns_newest_first(log):
    for index in range(3):
        log.append(
            run_id=f"r{index}",
            repository_path=f"C:/repo{index}",
            kind="index",
            started_at=f"2026-09-0{index + 1}T10:00:00+00:00",
        )

    assert [record.runId for record in log.recent()] == ["r2", "r1", "r0"]


def test_pruning_keeps_the_newest_and_bounds_the_file(log):
    for index in range(RETAINED_RUNS + 15):
        log.append(
            run_id=f"r{index:03d}",
            repository_path="C:/repo",
            kind="index",
            started_at=f"2026-01-01T00:{index // 60:02d}:{index % 60:02d}+00:00",
        )

    records = log.recent(limit=1000)
    assert len(records) == RETAINED_RUNS
    # Spec FR-026c: pruning is automatic and keeps the *newest*.
    assert records[0].runId == f"r{RETAINED_RUNS + 14:03d}"


def test_startup_sweep_closes_a_run_whose_hub_died(log):
    """Spec FR-026d.

    A NULL outcome can only belong to a run whose process is gone - spec FR-012
    guarantees there was one at most, and the process doing the sweeping is a
    new one. Without this, that run reads as in-progress forever.
    """
    log.append(run_id="orphan", repository_path="C:/repo", kind="index")

    swept = log.sweep_interrupted()

    assert swept == 1
    record = log.recent()[0]
    assert record.outcome == "interrupted"
    assert record.endedAt is not None


def test_startup_sweep_leaves_finished_runs_alone(log):
    log.append(run_id="done", repository_path="C:/repo", kind="index")
    log.close(run_id="done", outcome="succeeded")

    assert log.sweep_interrupted() == 0
    assert log.recent()[0].outcome == "succeeded"


def test_a_missing_log_reads_as_empty(log):
    assert log.recent() == []


def test_a_corrupt_log_reads_as_empty_rather_than_raising(log):
    """Spec FR-026e: the homepage must load even when this file cannot."""
    log.append(run_id="r1", repository_path="C:/repo", kind="index")
    run_log_path().write_bytes(b"this is definitely not a sqlite database")

    assert log.recent() == []
    # And the sweep must survive it too, since it runs at startup.
    assert log.sweep_interrupted() == 0


def test_a_log_from_an_unrecognised_schema_reads_as_empty(log):
    path = run_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE runs (something_else TEXT)")
    connection.commit()
    connection.close()

    assert log.recent() == []
