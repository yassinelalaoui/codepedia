"""The Codepedia homepage: a loopback hub that launches the real CLI.

This package owns `/` for `codepedia home` (contracts/home-command.md). It is
deliberately separate from `chat_api`, which serves one already-indexed
repository: the two share no routes and no state, and keeping `create_app`
untouched is what makes spec FR-002's "the CLI behaves exactly as before"
guarantee cheap to hold rather than something to keep re-proving.

The hub never runs the pipeline itself. It starts `python -m cli index` or
`python -m cli serve` as a child process and reads structured progress from that
child's stdout (research.md §1, §2). That is not an implementation detail: it is
what makes spec FR-012a's "stop the run" possible at all, since `run_index`
blocks inside provider calls in thread pools that Python cannot interrupt.
"""

from __future__ import annotations

from .app import create_hub_app

__all__ = ["create_hub_app"]
