from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Literal

from repository_metadata import RepositoryMetadataStore


class ChangeType(Enum):
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class FileChange:
    relative_path: str
    change_type: ChangeType


@dataclass(frozen=True, slots=True)
class ChangeBatch:
    changes: tuple[FileChange, ...]
    origin: Literal["live", "catchup"] = "live"

    def __post_init__(self) -> None:
        if not self.changes:
            raise ValueError("ChangeBatch must contain at least one FileChange")
        paths = [change.relative_path for change in self.changes]
        if len(paths) != len(set(paths)):
            raise ValueError("ChangeBatch must not contain duplicate relative_path entries")


@dataclass(frozen=True, slots=True)
class WatcherConfiguration:
    repository_root: Path
    metadata_store: RepositoryMetadataStore
    on_batch: Callable[[ChangeBatch], None]
    stabilization_delay: float = 1.5
