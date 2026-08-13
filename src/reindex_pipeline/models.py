from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from doc_generator import DocumentationSet
from repo_watcher import FileChange

EdgeId = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class ReindexBatch:
    repositoryRoot: Path
    changes: tuple[FileChange, ...]


@dataclass(frozen=True, slots=True)
class ChangeConfirmation:
    relativePath: str
    currentHash: str
    changed: bool


@dataclass(frozen=True, slots=True)
class PathClassification:
    relativePath: str
    excluded: bool
    isBinary: bool
    language: str | None


@dataclass(frozen=True, slots=True)
class ReindexOutcome:
    reprocessedPaths: tuple[str, ...] = ()
    skippedPaths: tuple[str, ...] = ()
    removedPaths: tuple[str, ...] = ()
    regeneratedSymbolIds: tuple[str, ...] = ()
    documentation: DocumentationSet | None = None
    summaryFailure: str | None = None
    failedPaths: tuple[str, ...] = ()
