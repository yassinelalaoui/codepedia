"""The analysed repository is never written to (constitution 2.7, spec FR-011).

This is the guarantee with the widest blast radius in the whole project, and
analysis is the operation that writes the most - so it is checked here against a
full real run, not only against Remove (`test_hub_http_api.py` covers that).

The check is a byte-level comparison of every file before and after, plus the
directory listing, so a new file, a deleted file and an edited file all fail it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from cli.index_command import run_index

from integration.test_cli import (  # noqa: F401 - imported for their fixture side effect
    _copy_fixture_repo,
    _local_config,
    cli_home,
    fake_engines,
)


def fingerprint(root: Path) -> dict[str, str]:
    """Every file under `root`, by relative path, with its content hash."""
    prints: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            prints[str(path.relative_to(root)).replace("\\", "/")] = digest
    return prints


def test_a_full_analysis_leaves_the_repository_byte_identical(tmp_path, cli_home, fake_engines):
    """Spec SC-010."""
    root = _copy_fixture_repo(tmp_path)
    before = fingerprint(root)
    assert before, "the fixture repository should not be empty"

    result = run_index(root, config=_local_config())
    result.vectorIndex.close()

    after = fingerprint(root)

    assert after == before, "the analysis modified the repository it was analysing"


def test_an_analysis_writes_only_under_the_state_directory(tmp_path, cli_home, fake_engines):
    """Spec FR-011: the output side of the same guarantee.

    Documentation, the index and the metadata all belong under `~/.codepedia`.
    Anything appearing beside the repository would mean the tool had started
    writing into the workspace it promises not to touch.
    """
    root = _copy_fixture_repo(tmp_path)
    siblings_before = {path.name for path in tmp_path.iterdir()}

    result = run_index(root, config=_local_config())
    result.vectorIndex.close()

    assert {path.name for path in tmp_path.iterdir()} == siblings_before
    # And the output really did land where it should.
    assert (cli_home / "repos").is_dir()
    assert any((cli_home / "repos").iterdir())


def test_a_failed_analysis_also_leaves_the_repository_untouched(tmp_path, cli_home, monkeypatch):
    """The failure path writes into a staging directory too, and discards it.

    Worth its own test because the cleanup runs through a different branch than
    the success path, and a botched cleanup is exactly the kind of thing that
    would reach for the wrong directory.
    """
    import cli.index_command as index_command
    from cli.errors import LocalModelUnavailableError

    root = _copy_fixture_repo(tmp_path)
    before = fingerprint(root)

    def unavailable(**_: object) -> None:
        raise LocalModelUnavailableError("No provider in the 'embeddings' chain is currently available.")

    monkeypatch.setattr(index_command, "check_ai_dependencies", unavailable)

    try:
        run_index(root, config=_local_config())
    except LocalModelUnavailableError:
        pass

    assert fingerprint(root) == before
