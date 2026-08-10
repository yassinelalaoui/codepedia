from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RepositoryScanRequest:
    root_path: Path
    output_format: str = "json"


@dataclass(frozen=True, slots=True)
class SourceFileEntry:
    relative_path: str
    language: str


@dataclass(frozen=True, slots=True)
class ScanSummary:
    total_candidates: int = 0
    included_files: int = 0
    ignored_files: int = 0
    binary_files: int = 0
    unsupported_files: int = 0


@dataclass(frozen=True, slots=True)
class ScanResult:
    root_path: str
    generated_at: str
    entries: list[SourceFileEntry] = field(default_factory=list)
    summary: ScanSummary = field(default_factory=ScanSummary)

    @classmethod
    def create(cls, root_path: Path, entries: list[SourceFileEntry], summary: ScanSummary) -> "ScanResult":
        return cls(
            root_path=str(root_path),
            generated_at=datetime.now(timezone.utc).isoformat(),
            entries=entries,
            summary=summary,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entries"] = [asdict(entry) for entry in self.entries]
        payload["summary"] = asdict(self.summary)
        return payload

