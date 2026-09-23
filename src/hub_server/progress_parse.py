"""Turn one line of a child's stdout into an event, or into nothing.

The parsing half of contracts/run-progress-stream.md. Deliberately total: every
input returns either an event or `None`, and nothing here raises. A child
process writes freely to stdout - a summary can contain anything, a library can
print a warning mid-line - and the reader thread that calls this is also the
thread keeping the child's pipe drained. An exception here would stop that
draining, fill the pipe, and hang the child (research.md §7). "Show less" is an
acceptable failure; "hang the server" is not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from cli.index_command import Stage
from cli.progress_stream import SENTINEL

# The stage names the homepage knows how to draw, taken from the pipeline's own
# enum rather than restated - data-model.md §1 requires the two never drift.
KNOWN_STAGES = frozenset(stage.name for stage in Stage)

KNOWN_TYPES = frozenset(
    {"stage", "stage_end", "items", "failed", "server_ready", "catchup"}
)


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """One parsed event. `payload` keeps the raw fields for the run state to
    read; the named attributes are only the ones every consumer needs."""

    seq: int
    type: str
    stage: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)


def is_event_line(line: str) -> bool:
    """Whether a line belongs to the channel rather than to the terminal.

    Anything answering `False` here is forwarded verbatim to the hub's own
    stdout, which is what keeps spec FR-016 true.
    """
    return line.startswith(SENTINEL)


def parse_line(line: str) -> Optional[ProgressEvent]:
    """Parse one line, or return `None` if it is not a well-formed event.

    Returns `None` - never raises - for: a line that is not an event at all, a
    sentinel line whose remainder is not JSON, JSON that is not an object, a
    missing or non-integer `seq`, and an unrecognised `type`. The last of those
    is forward-compatibility: a newer child emitting an event this hub has never
    heard of must not break this hub (contracts/run-progress-stream.md, reader
    obligation 4).
    """
    if not is_event_line(line):
        return None

    remainder = line[len(SENTINEL):].strip()
    if not remainder:
        return None

    try:
        raw = json.loads(remainder)
    except (ValueError, TypeError):
        return None

    if not isinstance(raw, dict):
        return None

    seq = raw.get("seq")
    event_type = raw.get("type")
    if not isinstance(seq, int) or isinstance(seq, bool):
        return None
    if not isinstance(event_type, str) or event_type not in KNOWN_TYPES:
        return None

    stage = raw.get("stage")
    if stage is not None and (not isinstance(stage, str) or stage not in KNOWN_STAGES):
        # An unknown stage name is dropped rather than rejecting the whole
        # event: `failed` still carries a usable message and provider list even
        # when it names a stage this version has never seen.
        stage = None

    return ProgressEvent(seq=seq, type=event_type, stage=stage, payload=raw)
