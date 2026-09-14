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

from collections import defaultdict
from pathlib import Path
from typing import Iterable

from repository_metadata.models import ModuleSymbol
from repository_metadata.summary_context import PROSE_FILE_SUFFIXES, is_prose_file

__all__ = ["PROSE_FILE_SUFFIXES", "disambiguated_labels", "display_label", "is_prose_file"]


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


def disambiguated_labels(modules: Iterable[ModuleSymbol], repository_root: str | Path) -> dict[str, str]:
    """A visible label per module, keyed by `sourceFileId`, no two alike (038 spec FR-030).

    Starts from `display_label`. Where several modules share one - the eight
    `__init__` rows of the sample repository - each takes the shortest tail of
    its repository-relative path, whole segments and no extension, that no
    other module sharing the label has: `api/__init__`, `core/__init__`. Two
    files that differ only in extension cannot be told apart that way, so they
    keep it.

    Display only, like `display_label`, and for the Overview's module list only
    (038 research Decision 12).
    """
    modules = list(modules)
    labels = {module.sourceFileId: display_label(module.name, module.filePath, repository_root) for module in modules}
    groups: dict[str, list[ModuleSymbol]] = defaultdict(list)
    for module in modules:
        groups[labels[module.sourceFileId]].append(module)

    for group in groups.values():
        if len(group) < 2:
            continue
        paths = {module.sourceFileId: _relative_parts(module, repository_root) for module in group}
        for module in group:
            labels[module.sourceFileId] = _shortest_unique_tail(module.sourceFileId, paths)

    # A tail can still collide with a label outside its group - `docs/guide`
    # for `docs/guide.py` against the prose file `docs/guide.md` - and then
    # only the full path, extension included, separates them.
    counts: dict[str, int] = defaultdict(int)
    for label in labels.values():
        counts[label] += 1
    for module in modules:
        if counts[labels[module.sourceFileId]] > 1:
            labels[module.sourceFileId] = "/".join(_relative_parts(module, repository_root, keep_suffix=True))
    return labels


def _relative_parts(module: ModuleSymbol, repository_root: str | Path, *, keep_suffix: bool = False) -> tuple[str, ...]:
    path = Path(module.filePath)
    try:
        relative = path.resolve().relative_to(Path(repository_root).resolve())
    except (OSError, ValueError):
        relative = Path(path.name)
    return (relative if keep_suffix else relative.with_suffix("")).parts or (module.name,)


def _shortest_unique_tail(key: str, paths: dict[str, tuple[str, ...]]) -> str:
    own = paths[key]
    others = [parts for other, parts in paths.items() if other != key]
    for length in range(1, len(own) + 1):
        tail = own[-length:]
        if all(parts[-length:] != tail for parts in others):
            return "/".join(tail)
    return "/".join(own)
