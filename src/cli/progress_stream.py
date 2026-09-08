"""Structured progress events for a parent process, off by default.

`codepedia home` needs to see inside a running `index` or `serve` in order to
draw a progress bar. It must do that **without changing one byte of what those
commands print when a person runs them** (spec FR-002). So every emit here is
gated on an environment variable that only the hub sets on the children it
launches (contracts/run-progress-stream.md).

That gating is not politeness, it is the evidence: with the variable unset
`emit` returns before writing anything, which
`tests/integration/test_cli_output_unchanged.py` asserts directly. A future
change that makes emission unconditional fails that test rather than quietly
altering the CLI's output.

Events go to **stdout**, interleaved with the ordinary human-readable lines, one
per line, sentinel-prefixed. stderr is deliberately not used: it carries real
errors and has to stay legible as such. The hub forwards every non-sentinel line
to its own stdout verbatim, which is what keeps spec FR-016 true.
"""

from __future__ import annotations

import itertools
import json
import os
import sys
import threading
from typing import Any

# Chosen to be unmistakable against real output. A repository can contain a
# symbol named `[12/340]`, so the item-progress lines the terminal prints are
# not safely parseable - this is (contracts/run-progress-stream.md's rationale
# for a sentinel rather than parsing what is already there).
SENTINEL = "@@CODEPEDIA_PROGRESS@@"

ENV_VAR = "CODEPEDIA_PROGRESS_STREAM"

_seq = itertools.count(1)
# `sys.stdout.write` is not atomic across threads, and both progress callbacks
# fire from worker pools. The lock keeps one event on one line; without it two
# concurrent writes can interleave into an unparseable hybrid.
_write_lock = threading.Lock()


def enabled() -> bool:
    """Whether a parent process asked for structured events.

    Read per call rather than cached at import: tests set and unset the variable
    with `monkeypatch.setenv`, and an import-time constant would make that
    require a module reload. The cost is one dict lookup per event, which is
    nothing beside the provider call each event describes.
    """
    return os.environ.get(ENV_VAR) == "1"


def emit(event_type: str, **fields: Any) -> None:
    """Write one event, or nothing at all when the variable is unset.

    `ensure_ascii=True` is load-bearing rather than stylistic: a repository path
    or a symbol name can contain anything, and JSON escaping guarantees the
    result is one line of ASCII no matter what went in. The reader's "exactly
    one line per event" contract depends on it.
    """
    if not enabled():
        return
    payload = {"seq": next(_seq), "type": event_type, **fields}
    line = SENTINEL + " " + json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    with _write_lock:
        # Python block-buffers stdout when it is a pipe, which is exactly the
        # case here. Without the flush, events reach the hub in 8KB clumps and
        # the bar advances in jumps minutes apart - spec SC-002 asks for 2s.
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
