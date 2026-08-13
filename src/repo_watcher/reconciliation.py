from __future__ import annotations

from pathlib import Path

from repo_scanner.models import RepositoryScanRequest
from repo_scanner.scanner import scan_repository
from repository_metadata import RepositoryMetadataStore, compute_content_hash

from .models import ChangeBatch, ChangeType, FileChange


def _to_relative(path_str: str, repository_root: Path) -> str:
    candidate = Path(path_str)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(repository_root).as_posix()
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


def compute_catchup_batch(
    repository_root: Path,
    metadata_store: RepositoryMetadataStore,
) -> ChangeBatch | None:
    scan_result = scan_repository(RepositoryScanRequest(root_path=repository_root))
    current_paths = {entry.relative_path for entry in scan_result.entries}

    try:
        bundle = metadata_store.load_repository(repository_root)
        known_hashes = {
            _to_relative(file_bundle.file.path, repository_root): file_bundle.file.contentHash
            for file_bundle in bundle.files
        }
    except KeyError:
        known_hashes = {}

    changes: list[FileChange] = []
    for path in sorted(current_paths):
        current_hash = compute_content_hash(repository_root / path)
        if path not in known_hashes:
            changes.append(FileChange(relative_path=path, change_type=ChangeType.CREATED))
        elif known_hashes[path] != current_hash:
            changes.append(FileChange(relative_path=path, change_type=ChangeType.MODIFIED))

    for path in sorted(set(known_hashes) - current_paths):
        changes.append(FileChange(relative_path=path, change_type=ChangeType.DELETED))

    if not changes:
        return None
    return ChangeBatch(changes=tuple(changes), origin="catchup")
