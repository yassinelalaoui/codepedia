"""Resolving HEAD without shelling out to git.

`codepedia` ships as a PyInstaller binary that cannot assume `git` is on PATH,
so provenance is read straight off `.git`. These cover the layouts a real
checkout produces, and the rule that an unknown commit is always "" rather than
an exception - a wiki must still build for a directory that is not a checkout.
"""

from __future__ import annotations

from pathlib import Path

from repository_metadata.git_provenance import read_commit_sha, short_commit_sha

SHA = "a" * 40
OTHER = "b" * 40


def test_detached_head_holds_the_sha_directly(tmp_path: Path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text(SHA + "\n", encoding="utf-8")
    assert read_commit_sha(tmp_path) == SHA


def test_a_branch_ref_is_followed_to_its_loose_file(tmp_path: Path):
    heads = tmp_path / ".git" / "refs" / "heads"
    heads.mkdir(parents=True)
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (heads / "main").write_text(SHA + "\n", encoding="utf-8")
    assert read_commit_sha(tmp_path) == SHA


def test_a_branch_name_containing_a_slash_resolves(tmp_path: Path):
    heads = tmp_path / ".git" / "refs" / "heads" / "feature"
    heads.mkdir(parents=True)
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/feature/x\n", encoding="utf-8")
    (heads / "x").write_text(SHA + "\n", encoding="utf-8")
    assert read_commit_sha(tmp_path) == SHA


def test_a_packed_ref_is_found_when_the_loose_file_is_gone(tmp_path: Path):
    # What `git gc` leaves behind, which is the state of any long-lived clone.
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        f"{OTHER} refs/heads/other\n"
        f"{SHA} refs/heads/main\n"
        f"{OTHER} refs/tags/v1\n"
        f"^{OTHER}\n",
        encoding="utf-8",
    )
    assert read_commit_sha(tmp_path) == SHA


def test_a_worktree_points_at_its_real_git_directory(tmp_path: Path):
    real = tmp_path / "elsewhere"
    (real / "refs" / "heads").mkdir(parents=True)
    (real / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (real / "refs" / "heads" / "main").write_text(SHA + "\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text(f"gitdir: {real}\n", encoding="utf-8")
    assert read_commit_sha(repo) == SHA


def test_an_unborn_branch_has_no_commit_yet(tmp_path: Path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    assert read_commit_sha(tmp_path) == ""


def test_a_directory_that_is_not_a_checkout_is_not_an_error(tmp_path: Path):
    assert read_commit_sha(tmp_path) == ""
    assert read_commit_sha(tmp_path / "does-not-exist") == ""


def test_short_sha_is_empty_when_the_commit_is_unknown():
    assert short_commit_sha(SHA) == "aaaaaaa"
    assert short_commit_sha("") == ""
