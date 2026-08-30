"""Which source files are documentation rather than code.

`parser_engine` maps a Markdown heading onto the existing class/function symbol
types, which is what lets documentation reuse the whole pipeline unchanged. The
cost of that mapping is that a heading is indistinguishable from a real symbol
by type alone, so the few places where the difference actually matters - the
words on a page, the prompt used to summarize it, and whether a symbol can be a
callable entry point - ask here.

Kept in its own module with no internal imports so both `generator` and
`entry_point_diagram` can use it without a cycle.
"""

from __future__ import annotations

from pathlib import Path

PROSE_FILE_SUFFIXES = frozenset({".md", ".markdown"})


def is_prose_file(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in PROSE_FILE_SUFFIXES
