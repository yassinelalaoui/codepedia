from __future__ import annotations

from pathlib import Path

from repo_scanner.binary import is_binary_path
from repo_scanner.docs_scope import DocsScope
from repo_scanner.ignore import IgnoreMatcher
from repo_scanner.language import PROSE_LANGUAGE, LanguageDetector
from repository_metadata import RepositoryMetadataStore, compute_content_hash

from .models import ChangeConfirmation, PathClassification

_LANGUAGE_DETECTOR = LanguageDetector()


def classify_path(
    repository_root: Path,
    relative_path: str,
    ignore_matcher: IgnoreMatcher,
    docs_scope: DocsScope | None = None,
) -> PathClassification:
    if ignore_matcher.ignores(relative_path, is_dir=False):
        return PathClassification(relativePath=relative_path, excluded=True, isBinary=False, language=None)
    absolute_path = repository_root / relative_path
    if is_binary_path(absolute_path):
        return PathClassification(relativePath=relative_path, excluded=False, isBinary=True, language=None)
    language = _LANGUAGE_DETECTOR.detect(absolute_path)
    # The same documentation perimeter `scan_repository` applies, applied to the
    # watcher's path: without it a save under `specs/` would be reindexed here
    # even though a full `index` no longer knows the file exists, and the two
    # views of the repository would drift apart file by file.
    scope = docs_scope if docs_scope is not None else DocsScope()
    if language == PROSE_LANGUAGE and not scope.covers(relative_path):
        language = None
    return PathClassification(relativePath=relative_path, excluded=False, isBinary=False, language=language)


def confirm_change(
    repository_root: Path,
    relative_path: str,
    metadata_store: RepositoryMetadataStore,
) -> ChangeConfirmation:
    absolute_path = repository_root / relative_path
    current_hash = compute_content_hash(absolute_path)
    # RepositoryMetadataStore keys stored files by the same path string SourceFile.path
    # was constructed with at store_inventory() time, which is always absolute
    # (parser_engine.SourceFile needs a real filesystem path to read from disk) —
    # see pipeline.py's _reparse_and_store. Must match here or every "modified" file
    # would look brand new (no stored hash found) on every run.
    changed = metadata_store.has_file_changed(
        repository_root=repository_root,
        path=absolute_path,
        current_hash=current_hash,
    )
    return ChangeConfirmation(relativePath=relative_path, currentHash=current_hash, changed=changed)
