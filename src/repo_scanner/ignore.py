from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_EXCLUDED_DIRS = {".git", "node_modules", "dist", "build", "out", "target"}


@dataclass(frozen=True, slots=True)
class IgnoreMatcher:
    patterns: list[str]
    root: Path

    def ignores(self, relative_path: str, is_dir: bool = False) -> bool:
        normalized = relative_path.replace("\\", "/")
        parts = normalized.split("/")
        if any(part in DEFAULT_EXCLUDED_DIRS for part in parts):
            return True
        for pattern in self.patterns:
            if _matches_gitignore_pattern(normalized, pattern, is_dir=is_dir):
                return True
        return False


def load_ignore_matcher(root: Path) -> IgnoreMatcher:
    patterns: list[str] = []
    gitignore = root / ".gitignore"
    if gitignore.is_file():
        patterns.extend(_read_patterns(gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()))
    return IgnoreMatcher(patterns=patterns, root=root)


def _read_patterns(lines: Iterable[str]) -> list[str]:
    patterns: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _matches_gitignore_pattern(path: str, pattern: str, is_dir: bool = False) -> bool:
    negate = pattern.startswith("!")
    if negate:
        pattern = pattern[1:]
    pattern = pattern.lstrip("/")
    if pattern.endswith("/"):
        pattern = pattern[:-1]
        if not is_dir:
            return False
    matched = False
    if "/" not in pattern:
        matched = any(segment == pattern for segment in path.split("/"))
    elif path == pattern or path.endswith("/" + pattern) or path.startswith(pattern + "/"):
        matched = True
    elif pattern.startswith("*") and path.endswith(pattern.lstrip("*")):
        matched = True
    return False if negate else matched

