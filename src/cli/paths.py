from __future__ import annotations

import hashlib
from pathlib import Path

from repository_metadata.sqlite_store import stable_repository_id


def repo_scanner_home() -> Path:
    """Root of every path this package writes to.

    A function (not a module-level constant) so tests can redirect it by
    monkeypatching this attribute, without needing every already-imported
    caller to be reloaded.
    """
    return Path.home() / ".repo-scanner"


def config_path() -> Path:
    return repo_scanner_home() / "config.json"


def state_id(root: Path) -> str:
    """A short, filesystem-safe id for a repository path.

    ``stable_repository_id`` (005) returns ``"repo::/abs/posix/path"``, which
    is stable but not a valid directory name on every platform (``:`` is
    disallowed outside a Windows drive letter). Hashing it keeps the id
    stable per repository path while staying filesystem-safe everywhere.
    """
    raw = stable_repository_id(root)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def repo_state_dir(root: Path) -> Path:
    return repo_scanner_home() / "repos" / state_id(root)


def metadata_db_path(state_dir: Path) -> Path:
    return state_dir / "repository-metadata.sqlite"


def graph_db_path(state_dir: Path) -> Path:
    return state_dir / "dependency-graph.sqlite"


def vector_index_db_path(state_dir: Path) -> Path:
    return state_dir / "vector-index.sqlite"


def vector_metadata_db_path(state_dir: Path) -> Path:
    return state_dir / "vector-metadata.sqlite"


def doc_manifest_db_path(state_dir: Path) -> Path:
    return state_dir / "doc-manifest.sqlite"


def docs_output_dir(state_dir: Path) -> Path:
    return state_dir / "docs"
