"""The state of the one analysis that may be running (data-model.md §1).

Exactly one non-terminal run exists at a time (spec FR-012), which is what lets
this be a single object behind a lock rather than a registry. It is mutated by
the child's stdout reader thread and read by HTTP handlers, so every read hands
back a snapshot rather than the live object.

`version` is the coordination mechanism: it increases on every mutation, and the
progress stream re-sends a full snapshot whenever it changes. Full snapshots
rather than deltas mean a late attach, a reload and a second tab are all the
same code path, and a client's view can never drift from the server's
(spec FR-018, research.md §4).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from cli.index_command import Stage

from .progress_parse import ProgressEvent

# The ten stages, in pipeline order, from the pipeline's own enum. Restating
# them here would create two lists to keep in step; data-model.md §1 requires
# there be one.
STAGE_SEQUENCE: tuple[tuple[str, str], ...] = tuple((stage.name, stage.value) for stage in Stage)

PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"

SUCCEEDED = "succeeded"
CANCELLED = "cancelled"
INTERRUPTED = "interrupted"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class StageState:
    name: str
    label: str
    status: str = PENDING
    completed: Optional[int] = None
    total: Optional[int] = None
    elapsedSeconds: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "status": self.status,
            "completed": self.completed,
            "total": self.total,
            "elapsedSeconds": self.elapsedSeconds,
        }


@dataclass
class RunState:
    """One attempt to analyse or open one repository."""

    runId: str
    kind: str
    repositoryPath: str
    stages: list[StageState] = field(default_factory=lambda: [StageState(name, label) for name, label in STAGE_SEQUENCE])
    currentStage: Optional[str] = None
    notices: list[str] = field(default_factory=list)
    catchup: Optional[dict[str, Any]] = None
    outcome: Optional[str] = None
    failedStage: Optional[str] = None
    failureMessage: Optional[str] = None
    serverUrl: Optional[str] = None
    startedAt: str = field(default_factory=_now)
    endedAt: Optional[str] = None
    version: int = 0
    childPid: Optional[int] = None

    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # -- mutation -----------------------------------------------------------

    def _touch(self) -> None:
        self.version += 1

    def _stage(self, name: Optional[str]) -> Optional[StageState]:
        if name is None:
            return None
        for stage in self.stages:
            if stage.name == name:
                return stage
        return None

    def apply(self, event: ProgressEvent) -> None:
        """Fold one parsed event into this state."""
        with self._lock:
            handler = getattr(self, f"_apply_{event.type}", None)
            if handler is None:
                return
            handler(event)
            self._touch()

    def _apply_stage(self, event: ProgressEvent) -> None:
        stage = self._stage(event.stage)
        if stage is None:
            return
        # Everything before the newly-started stage is finished by definition:
        # the pipeline is strictly ordered, so a stage starting is proof its
        # predecessors are done even if their `stage_end` was lost.
        for candidate in self.stages:
            if candidate.name == stage.name:
                break
            if candidate.status in (PENDING, RUNNING):
                candidate.status = DONE
        stage.status = RUNNING
        self.currentStage = stage.name

    def _apply_stage_end(self, event: ProgressEvent) -> None:
        stage = self._stage(event.stage)
        if stage is None:
            return
        stage.status = DONE
        stage.elapsedSeconds = event.get("elapsedSeconds")

    def _apply_items(self, event: ProgressEvent) -> None:
        stage = self._stage(event.stage)
        if stage is None:
            return
        stage.completed = event.get("completed")
        stage.total = event.get("total")
        if stage.status == PENDING:
            stage.status = RUNNING

    def _apply_catchup(self, event: ProgressEvent) -> None:
        self.catchup = {
            "phase": event.get("phase"),
            "completed": event.get("completed"),
            "total": event.get("total"),
            "path": event.get("path"),
        }

    def _apply_failed(self, event: ProgressEvent) -> None:
        # Diagnosis only. The run does not become terminal here - the child's
        # exit code decides that (contracts/run-progress-stream.md, reader
        # obligation 6), so a child killed before emitting this still ends.
        self.failedStage = event.stage or event.get("chain")
        self.failureMessage = event.get("message")
        stage = self._stage(event.stage)
        if stage is not None:
            stage.status = FAILED

    def _apply_server_ready(self, event: ProgressEvent) -> None:
        self.serverUrl = event.get("url")

    # -- termination --------------------------------------------------------

    def finish(self, outcome: str, *, message: Optional[str] = None) -> None:
        """Reach a terminal state, once and for all (spec FR-021).

        Guarded against a second call: a child that emits `failed` and then
        exits non-zero must not overwrite `cancelled` with `failed`, or the
        person who pressed Stop would be told their run broke.
        """
        with self._lock:
            if self.outcome is not None:
                return
            self.outcome = outcome
            self.endedAt = _now()
            if message and not self.failureMessage:
                self.failureMessage = message
            for stage in self.stages:
                if stage.status == RUNNING:
                    stage.status = FAILED if outcome != SUCCEEDED else DONE
                elif stage.status == PENDING and outcome == SUCCEEDED:
                    stage.status = DONE
            self.currentStage = None
            self._touch()

    @property
    def isTerminal(self) -> bool:
        return self.outcome is not None

    # -- reading ------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "runId": self.runId,
                "kind": self.kind,
                "repositoryPath": self.repositoryPath,
                "stages": [stage.to_dict() for stage in self.stages],
                "currentStage": self.currentStage,
                "notices": list(self.notices),
                "catchup": dict(self.catchup) if self.catchup else None,
                "outcome": self.outcome,
                "failedStage": self.failedStage,
                "failureMessage": self.failureMessage,
                "serverUrl": self.serverUrl,
                "startedAt": self.startedAt,
                "endedAt": self.endedAt,
                "version": self.version,
                # Spec FR-023: say it, do not leave it to be inferred from a
                # column of ticked stages.
                "discardedEverything": self.outcome in (FAILED, "failed", CANCELLED),
            }
