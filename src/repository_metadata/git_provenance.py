"""The commit a wiki was generated from, read straight off the filesystem.

A generated page states when it was built; without the commit it was built
*from*, "Updated on ..." says nothing a reader can check. This resolves the
repository's current HEAD so the wiki can show `Updated on <date> · Commit
<sha>`, and so a later run can tell whether the documentation predates the code.

Deliberately no `git` subprocess. `codepedia` ships as a PyInstaller binary that
cannot assume `git` is on PATH, spawning a process per index run is a cost the
read does not need, and the constitution's repository-read-only rule is easier
to honour by never handing the repository to another program. Everything below
is plain file reading, and every failure degrades to "" rather than raising: an
unknown commit must never stop a wiki from being generated.

The layouts handled are the ones a real checkout produces:

* `.git/HEAD` holding a raw sha - a detached HEAD, which is what CI checkouts
  usually leave behind;
* `.git/HEAD` holding `ref: refs/heads/<branch>`, resolved against
  `.git/refs/...` and then, when the ref has been packed away by `git gc`,
  against `.git/packed-refs`;
* `.git` as a *file* containing `gitdir: <path>` - a worktree or a submodule,
  where the real git directory lives elsewhere.
"""

from __future__ import annotations

import re
from pathlib import Path

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
_GITDIR_PREFIX = "gitdir:"
_REF_PREFIX = "ref:"

# What a page displays. Long enough to be unambiguous in any real repository,
# short enough to read - the same length `git log --oneline` uses.
SHORT_SHA_LENGTH = 7


def read_commit_sha(repository_root: str | Path) -> str:
    """The full sha of `repository_root`'s current HEAD, or "" if unknown.

    "" covers every uninteresting case identically: not a git repository, an
    unborn branch with no commit yet, a dangling ref, or a directory this
    process cannot read.
    """
    git_dir = _resolve_git_dir(Path(repository_root).expanduser())
    if git_dir is None:
        return ""
    head = _read_text(git_dir / "HEAD")
    if not head:
        return ""
    if _SHA_PATTERN.match(head):
        return head
    if not head.startswith(_REF_PREFIX):
        return ""
    ref = head[len(_REF_PREFIX) :].strip()
    if not ref:
        return ""
    return _resolve_ref(git_dir, ref)


def short_commit_sha(commit_sha: str, *, length: int = SHORT_SHA_LENGTH) -> str:
    return commit_sha[:length] if commit_sha else ""


def _resolve_git_dir(repository_root: Path) -> Path | None:
    candidate = repository_root / ".git"
    if candidate.is_dir():
        return candidate
    if candidate.is_file():
        # A worktree or submodule: the file points at the real git directory,
        # relative to the repository root when not absolute.
        pointer = _read_text(candidate)
        if not pointer.startswith(_GITDIR_PREFIX):
            return None
        target = Path(pointer[len(_GITDIR_PREFIX) :].strip())
        if not target.is_absolute():
            target = (repository_root / target).resolve()
        return target if target.is_dir() else None
    return None


def _resolve_ref(git_dir: Path, ref: str) -> str:
    loose = _read_text(git_dir / Path(ref))
    if _SHA_PATTERN.match(loose):
        return loose
    return _read_packed_ref(git_dir, ref)


def _read_packed_ref(git_dir: Path, ref: str) -> str:
    """Find `ref` in `.git/packed-refs`, which `git gc` writes loose refs into."""
    for line in _read_text(git_dir / "packed-refs").splitlines():
        stripped = line.strip()
        # `#` is a header comment, `^` the peeled target of an annotated tag -
        # never the commit the ref itself points at.
        if not stripped or stripped.startswith("#") or stripped.startswith("^"):
            continue
        sha, _, name = stripped.partition(" ")
        if name.strip() == ref and _SHA_PATTERN.match(sha):
            return sha
    return ""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
