from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pathspec import GitIgnoreSpec

DEFAULT_EXCLUDED_DIRS = {".git", "node_modules", "dist", "build", "out", "target"}
GITIGNORE_FILENAME = ".gitignore"


@dataclass(frozen=True, slots=True)
class IgnoreMatcher:
    """Git-compatible ignore matcher.

    Patterns are evaluated with ``pathspec``'s gitignore implementation, so
    negations (``!keep.log``), anchored patterns and directory-only patterns
    behave the way ``git`` does. ``.gitignore`` files are honoured in every
    directory, not just the repository root: the file closest to the path
    being tested wins, and ``DEFAULT_EXCLUDED_DIRS`` only applies when no
    ``.gitignore`` has an opinion about the path.
    """

    root: Path
    extra_patterns: tuple[str, ...] = ()
    _spec_cache: dict[str, GitIgnoreSpec | None] = field(default_factory=dict, repr=False, compare=False)

    def ignores(self, relative_path: str, is_dir: bool = False) -> bool:
        normalized = relative_path.replace("\\", "/").strip("/")
        if not normalized:
            return False
        subject = f"{normalized}/" if is_dir else normalized
        decision: bool | None = None
        for directory in _ancestor_directories(normalized):
            spec = self._spec_for(directory)
            if spec is None:
                continue
            relative_subject = subject[len(directory) + 1 :] if directory else subject
            result = spec.check_file(relative_subject)
            if result.include is not None:
                decision = bool(result.include)
        if decision is not None:
            return decision
        return _matches_default_excludes(normalized)

    def _spec_for(self, directory: str) -> GitIgnoreSpec | None:
        cached = self._spec_cache.get(directory, _MISSING)
        if cached is not _MISSING:
            return cached  # type: ignore[return-value]
        spec = self._load_spec(directory)
        self._spec_cache[directory] = spec
        return spec

    def _load_spec(self, directory: str) -> GitIgnoreSpec | None:
        lines: list[str] = []
        if not directory:
            lines.extend(self.extra_patterns)
        gitignore = (self.root / directory / GITIGNORE_FILENAME) if directory else (self.root / GITIGNORE_FILENAME)
        if gitignore.is_file():
            try:
                lines.extend(gitignore.read_text(encoding="utf-8", errors="ignore").splitlines())
            except OSError:
                pass
        if not lines:
            return None
        return GitIgnoreSpec.from_lines(lines)


_MISSING = object()


def load_ignore_matcher(root: Path, extra_patterns: tuple[str, ...] = ()) -> IgnoreMatcher:
    return IgnoreMatcher(root=Path(root), extra_patterns=tuple(extra_patterns))


def _ancestor_directories(normalized_path: str) -> list[str]:
    """Directories that may hold a ``.gitignore`` for ``normalized_path``.

    Shallowest first, so a deeper file's decision overrides a shallower one.
    """
    parts = normalized_path.split("/")[:-1]
    directories = [""]
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        directories.append(current)
    return directories


def _matches_default_excludes(normalized_path: str) -> bool:
    return any(part in DEFAULT_EXCLUDED_DIRS for part in normalized_path.split("/"))
