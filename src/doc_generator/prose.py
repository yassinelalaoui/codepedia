"""Which source files are documentation rather than code.

`parser_engine` maps a Markdown heading onto the existing class/function symbol
types, which is what lets documentation reuse the whole pipeline unchanged. The
cost of that mapping is that a heading is indistinguishable from a real symbol
by type alone, so the few places where the difference actually matters - the
words on a page, the prompt used to summarize it, and whether a symbol can be a
callable entry point - ask here.

The rule itself lives in `repository_metadata`, the lower of the two packages
that need it, and is re-exported here so `generator` and `entry_point_diagram`
keep importing it from their own package without a cycle. It used to be defined
twice, which meant adding `.mdx` to one copy would have summarized a file as
code and rendered it as prose, with nothing anywhere reporting an error.
"""

from __future__ import annotations

from repository_metadata.summary_context import PROSE_FILE_SUFFIXES, is_prose_file

__all__ = ["PROSE_FILE_SUFFIXES", "is_prose_file"]
