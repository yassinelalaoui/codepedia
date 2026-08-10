from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
import os

from .binary import is_binary_path
from .ignore import IgnoreMatcher, load_ignore_matcher
from .language import LanguageDetector
from .models import RepositoryScanRequest, ScanResult, ScanSummary, SourceFileEntry


@dataclass(frozen=True, slots=True)
class ScanContext:
    root: Path
    ignore: IgnoreMatcher
    language_detector: LanguageDetector


def scan_repository(request: RepositoryScanRequest | Path | str) -> ScanResult:
    root = _resolve_request(request)
    _validate_repository(root)
    context = ScanContext(
        root=root,
        ignore=load_ignore_matcher(root),
        language_detector=LanguageDetector(),
    )
    entries: list[SourceFileEntry] = []
    summary = ScanSummary()
    for relative_path, absolute_path in _walk_repository(context):
        summary = ScanSummary(
            total_candidates=summary.total_candidates + 1,
            included_files=summary.included_files,
            ignored_files=summary.ignored_files,
            binary_files=summary.binary_files,
            unsupported_files=summary.unsupported_files,
        )
        if context.ignore.ignores(relative_path, is_dir=False):
            summary = ScanSummary(
                total_candidates=summary.total_candidates,
                included_files=summary.included_files,
                ignored_files=summary.ignored_files + 1,
                binary_files=summary.binary_files,
                unsupported_files=summary.unsupported_files,
            )
            continue
        if is_binary_path(absolute_path):
            summary = ScanSummary(
                total_candidates=summary.total_candidates,
                included_files=summary.included_files,
                ignored_files=summary.ignored_files,
                binary_files=summary.binary_files + 1,
                unsupported_files=summary.unsupported_files,
            )
            continue
        language = context.language_detector.detect(absolute_path)
        if not language:
            summary = ScanSummary(
                total_candidates=summary.total_candidates,
                included_files=summary.included_files,
                ignored_files=summary.ignored_files,
                binary_files=summary.binary_files,
                unsupported_files=summary.unsupported_files + 1,
            )
            continue
        entries.append(SourceFileEntry(relative_path=relative_path, language=language))
        summary = ScanSummary(
            total_candidates=summary.total_candidates,
            included_files=summary.included_files + 1,
            ignored_files=summary.ignored_files,
            binary_files=summary.binary_files,
            unsupported_files=summary.unsupported_files,
        )
    entries.sort(key=lambda item: item.relative_path)
    return ScanResult.create(root, entries, summary)


def _resolve_request(request: RepositoryScanRequest | Path | str) -> Path:
    if isinstance(request, RepositoryScanRequest):
        return Path(request.root_path).expanduser().resolve()
    return Path(request).expanduser().resolve()


def _validate_repository(root: Path) -> None:
    if not root.exists():
        raise FileNotFoundError(f"Repository path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root}")
    if not os_accessible(root):
        raise PermissionError(f"Repository path is not readable: {root}")


def os_accessible(path: Path) -> bool:
    return os.access(path, os.R_OK | os.X_OK)


def _walk_repository(context: ScanContext) -> Iterator[tuple[str, Path]]:
    stack: list[Path] = [context.root]
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name, reverse=True)
        except OSError:
            continue
        for child in children:
            relative = child.relative_to(context.root).as_posix()
            is_dir = child.is_dir()
            if context.ignore.ignores(relative, is_dir=is_dir):
                continue
            if is_dir:
                stack.append(child)
            elif child.is_file():
                yield relative, child
