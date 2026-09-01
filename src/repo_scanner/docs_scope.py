from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pathspec import GitIgnoreSpec

CONFIG_FILENAME = ".codepedia.json"

# An explicit perimeter, not an opt-out. `parser_engine` promotes every Markdown
# heading to a symbol, and every symbol costs one LLM summary call plus one
# embedding - so indexing whatever `*.md` a repository happens to contain makes
# the run's cost a property of the repository's scaffolding rather than of its
# code. Measured on this repository before the bound existed: 3 314 Markdown
# files producing 39 740 symbols, against roughly 1 245 for all of `src/`.
#
# The defaults are what a reader of a wiki would actually look for: the README
# that says what the project is, and the project's own documentation directory.
# Everything is anchored to the root, including the directories - an unanchored
# `docs/` matches at any depth, which on this repository pulled in 657 files
# from a vendored `claude-skills/docs/` tree that documents somebody else's
# project. A monorepo whose documentation really does live at
# `packages/web/docs/` says so in `.codepedia.json`; that is what a declared
# perimeter is for, and guessing on its behalf is what this bound removes.
DEFAULT_DOCS_INCLUDE: tuple[str, ...] = (
    "/README*.md",
    "/README*.markdown",
    "/docs/",
    "/doc/",
    "/documentation/",
)
DEFAULT_DOCS_EXCLUDE: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocsScope:
    """Which documentation files are part of a repository's wiki.

    Patterns are gitignore patterns, evaluated with the same ``pathspec``
    implementation `IgnoreMatcher` uses - so anchoring (``/README.md``),
    directory patterns (``docs/``) and negations (``!docs/generated/**``)
    behave the way a reader of a ``.gitignore`` already expects. ``exclude``
    is applied after ``include`` and wins.

    Only consulted for prose files. Code is never scoped by this: a repository
    is indexed for its code, and narrowing *that* is what ``.gitignore``
    already does.
    """

    include: tuple[str, ...] = DEFAULT_DOCS_INCLUDE
    exclude: tuple[str, ...] = DEFAULT_DOCS_EXCLUDE

    def covers(self, relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/").strip("/")
        if not normalized:
            return False
        if not _spec(self.include).match_file(normalized):
            return False
        return not _spec(self.exclude).match_file(normalized)


def load_docs_scope(root: Path | str) -> DocsScope:
    """Read `.codepedia.json` at the repository root, or fall back to defaults.

    The scope lives with the repository rather than in the user's global
    configuration because it *is* a property of the repository: the same
    machine indexes several, and a third-party checkout carries its own answer
    to "which of these files are documentation".
    """
    config_path = Path(root) / CONFIG_FILENAME
    if not config_path.is_file():
        return DocsScope()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        # Loud, not silent: a malformed config that fell back to the defaults
        # would look exactly like a config that was never read, and the symptom
        # - documentation missing from the wiki - would show up hours later.
        raise ValueError(f"{config_path} is not readable JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{config_path} must contain a JSON object")
    docs = payload.get("docs", {})
    if not isinstance(docs, dict):
        raise ValueError(f"{config_path}: 'docs' must be a JSON object")
    return DocsScope(
        include=_patterns(config_path, docs, "include", DEFAULT_DOCS_INCLUDE),
        exclude=_patterns(config_path, docs, "exclude", DEFAULT_DOCS_EXCLUDE),
    )


def _patterns(config_path: Path, docs: dict, key: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if key not in docs:
        return fallback
    value = docs[key]
    if not isinstance(value, list) or not all(isinstance(entry, str) for entry in value):
        raise ValueError(f"{config_path}: 'docs.{key}' must be a list of pattern strings")
    return tuple(value)


def _spec(patterns: tuple[str, ...]) -> GitIgnoreSpec:
    return GitIgnoreSpec.from_lines(patterns)
