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

from pathlib import Path

from repository_metadata.summary_context import PROSE_FILE_SUFFIXES, is_prose_file

__all__ = ["PROSE_FILE_SUFFIXES", "display_label", "is_prose_file"]


def display_label(name: str, file_path: str, repository_root: str | Path) -> str:
    """What a page, a sidebar entry or a search result calls this source file.

    Code keeps `module.name`, the file's stem, which is how a reader refers to
    it. Prose cannot: documentation filenames repeat by convention, and a
    repository laid out as `specs/001-x/spec.md`, `specs/002-y/spec.md` would
    fill the sidebar with entries all labelled "spec". The URLs differ -
    `links.page_slug` appends a hash of the stable id - but nothing on screen
    does, which is not a navigation.

    Display only, deliberately. `page_slug`, the page ids, `sourceFileId` and
    every stored anchor still derive from `module.name`, so relabelling costs no
    reindex and breaks no link: the returned string is only ever rendered.
    """
    if not is_prose_file(file_path):
        return name
    path = Path(file_path)
    try:
        relative = path.resolve().relative_to(Path(repository_root).resolve())
    except (OSError, ValueError):
        # Outside the repository root, or unresolvable on this filesystem - the
        # stem is still an honest answer, just a less specific one.
        return name
    return relative.with_suffix("").as_posix() or name
