from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

COMMON_LANGUAGE_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    # Prose, not code, but a repository's documentation is part of what a wiki
    # is meant to explain. `parser_engine` gives it a heading-based inventory
    # rather than a symbol one; everything downstream (pages, anchors, chunks,
    # summaries) treats it like any other source file.
    ".md": "Markdown",
    ".markdown": "Markdown",
}

# The language name every prose file detects as. `docs_scope` keys the
# documentation perimeter on this rather than on a suffix set of its own:
# `repository_metadata.summary_context.PROSE_FILE_SUFFIXES` is already the one
# definition of "which suffixes are prose" (a second copy is exactly the defect
# that consolidation removed), and this package sits below the one that owns it.
PROSE_LANGUAGE = "Markdown"


@dataclass(frozen=True, slots=True)
class LanguageDetector:
    def detect(self, path: Path) -> str | None:
        suffix = path.suffix.lower()
        if suffix in COMMON_LANGUAGE_MAP:
            return COMMON_LANGUAGE_MAP[suffix]
        detected = _detect_with_tree_sitter(path)
        if detected:
            return detected
        return None


def _detect_with_tree_sitter(path: Path) -> str | None:
    try:
        from tree_sitter import Language, Parser  # type: ignore
    except Exception:
        return None
    try:
        with path.open("rb") as handle:
            content = handle.read(8192)
    except OSError:
        return None
    if not content:
        return None
    # Fallback is intentionally conservative: only try obvious interpreters when
    # Tree-sitter bindings are available. The scanner remains fully local.
    lowered = content.lower()
    if lowered.startswith(b"#!/") and b"python" in lowered.splitlines()[0]:
        return "Python"
    if lowered.startswith(b"#!/") and b"node" in lowered.splitlines()[0]:
        return "JavaScript"
    return None

