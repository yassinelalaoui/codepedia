"""Validate a repository path that arrived from a browser.

Starting an analysis is a write action against an arbitrary filesystem path,
submitted by whatever can reach the hub. Spec FR-009 requires this to run before
any work begins, and constitution 2.7 - the analysed repository stays read-only
- is only as good as what happens here, because everything downstream trusts the
path it is handed.

Every rejection carries its own message. "That path is not valid" tells the
person nothing; "that path is a file, not a folder" tells them what to do next,
which is what spec FR-010 and SC-004 are asking for.
"""

from __future__ import annotations

import os
from pathlib import Path

from cli import paths as cli_paths


class InvalidRepositoryPathError(ValueError):
    """A submitted path that must not be analysed. Message is user-facing."""

    kind = "invalid_path"


def validate_submitted_path(raw: str) -> Path:
    """Resolve and check a submitted path, or raise `InvalidRepositoryPathError`.

    The checks are ordered so the first failure is the most useful explanation.
    Resolution happens early and deliberately: `..` segments, a trailing
    separator, `~`, and symlinks are all normalised away *before* anything is
    compared, so no later check can be walked around by spelling a path
    differently.
    """
    if raw is None or not str(raw).strip():
        raise InvalidRepositoryPathError("Enter the path of a repository to analyse.")

    candidate = str(raw).strip()

    try:
        # `strict=False`: a path that does not exist must reach the "does not
        # exist" message below, not surface as an OSError from resolution.
        resolved = Path(candidate).expanduser().resolve(strict=False)
    except (OSError, ValueError, RuntimeError) as error:
        raise InvalidRepositoryPathError(
            f"That path could not be read as a location on this machine: {candidate}"
        ) from error

    if not resolved.exists():
        raise InvalidRepositoryPathError(f"There is nothing at {resolved} on this machine.")

    if not resolved.is_dir():
        raise InvalidRepositoryPathError(
            f"{resolved} is a file, not a folder. Point this at the repository's folder."
        )

    if not os.access(resolved, os.R_OK):
        raise InvalidRepositoryPathError(f"{resolved} cannot be read - check its permissions.")

    _reject_codepedia_home(resolved)

    return resolved


def _reject_codepedia_home(resolved: Path) -> None:
    """Refuse the tool's own state directory, and anything inside it.

    Analysing `~/.codepedia` would nest a run's output inside its own input:
    every generated page and database would become a source file for the next
    run. `doc_generator._ensure_output_root_is_separate` already guards the
    output side of that; this is the input side, and it is the one a browser can
    reach (spec FR-009, constitution 2.7).
    """
    home = cli_paths.codepedia_home()
    try:
        home_resolved = home.expanduser().resolve(strict=False)
    except (OSError, ValueError, RuntimeError):
        return

    if resolved == home_resolved or home_resolved in resolved.parents:
        raise InvalidRepositoryPathError(
            f"{resolved} is inside Codepedia's own storage. Choose a repository to analyse instead."
        )
