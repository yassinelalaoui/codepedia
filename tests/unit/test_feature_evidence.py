from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))

from _doc_generator_support import index_repo  # noqa: E402

from doc_generator.features.evidence import (  # noqa: E402
    MAX_README_PROMPT_CHARS,
    build_repository_evidence,
    read_readme_bullets,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _repo(tmp_path: Path):
    """A CLI entry point reaching a helper, plus a module nothing calls."""
    root = tmp_path / "evidence-repo"
    files = [
        _write(
            root / "app" / "commands.py",
            '"""Commands."""\n\n'
            "from .helpers import assist\n\n\n"
            "def run_report() -> int:\n"
            '    """Public, uncalled - an entry point."""\n'
            "    return assist()\n",
        ),
        _write(
            root / "app" / "helpers.py",
            '"""Helpers."""\n\n\ndef assist() -> int:\n    return 1\n',
        ),
        _write(
            root / "app" / "orphan.py",
            '"""Nothing imports or calls this."""\n\n\ndef _private() -> int:\n    return 2\n',
        ),
    ]
    store, graph = index_repo(tmp_path, root, files, "evidence-repo.sqlite")
    return root, store.load_repository(root), graph


def test_one_evidence_row_per_module(tmp_path):
    """Every module gets a row, including one nothing reaches.

    A missing row would not raise - it would quietly leave that module out of
    every candidate, and therefore out of the navigation. That is the one
    failure this feature exists to prevent, so it is asserted on the count
    rather than inferred from a spot check.
    """
    root, bundle, graph = _repo(tmp_path)

    evidence = build_repository_evidence(bundle, graph, repository_root=root)

    assert len(evidence.modules) == len(bundle.files)
    assert {item.moduleKey for item in evidence.modules} == {
        file_bundle.module.sourceFileId for file_bundle in bundle.files
    }
    orphan = next(item for item in evidence.modules if item.moduleName == "orphan")
    assert orphan.reachingEntryPointKeys == ()
    assert orphan.exportedSymbolNames == ()


def test_evidence_records_reaching_entry_points(tmp_path):
    root, bundle, graph = _repo(tmp_path)

    evidence = build_repository_evidence(bundle, graph, repository_root=root)

    helpers = next(item for item in evidence.modules if item.moduleName == "helpers")
    assert any("run_report" in key for key in helpers.reachingEntryPointKeys), (
        "the helper is called by the entry point, so the entry point reaches it"
    )


def test_evidence_records_public_exports_only(tmp_path):
    root, bundle, graph = _repo(tmp_path)

    evidence = build_repository_evidence(bundle, graph, repository_root=root)

    commands = next(item for item in evidence.modules if item.moduleName == "commands")
    orphan = next(item for item in evidence.modules if item.moduleName == "orphan")
    assert "run_report" in commands.exportedSymbolNames
    assert orphan.exportedSymbolNames == (), "`_private` is not an export"


def test_reaching_entry_points_terminates_on_a_call_cycle(tmp_path):
    """The walk carries its own visited set.

    `build_entry_point_call_sequence` deliberately does not - a sequence diagram
    must draw a repeated call twice - which is exactly why evidence must not
    reuse it. A cycle is the case that separates the two.
    """
    root = tmp_path / "cycle-repo"
    files = [
        _write(
            root / "loop.py",
            '"""Mutually recursive."""\n\n\n'
            "def enter(value: int) -> int:\n"
            "    return ping(value)\n\n\n"
            "def ping(value: int) -> int:\n"
            "    return pong(value)\n\n\n"
            "def pong(value: int) -> int:\n"
            "    return ping(value)\n",
        )
    ]
    store, graph = index_repo(tmp_path, root, files, "cycle-repo.sqlite")
    bundle = store.load_repository(root)

    evidence = build_repository_evidence(bundle, graph, repository_root=root)

    loop = next(item for item in evidence.modules if item.moduleName == "loop")
    assert len(loop.reachingEntryPointKeys) == len(set(loop.reachingEntryPointKeys)), (
        "a cycle must not report the same entry point twice"
    )


def test_evidence_is_identical_across_runs(tmp_path):
    root, bundle, graph = _repo(tmp_path)

    first = build_repository_evidence(bundle, graph, repository_root=root)
    second = build_repository_evidence(bundle, graph, repository_root=root)

    assert first.modules == second.modules
    assert first.entryPointModuleKeys == second.entryPointModuleKeys


def test_readme_md_is_read(tmp_path):
    """The difference from `chat.retrieval.read_readme_content`, pinned.

    That helper omits `.md` on purpose, because a `README.md` is indexed like any
    other file and retrieval returns the relevant parts of it. Here the opposite
    is wanted - the repository's own statement of what it does - and `.md` is the
    overwhelmingly common case.
    """
    (tmp_path / "README.md").write_text(
        "# My Tool\n\n- Indexes a repository\n- Answers questions about it\n",
        encoding="utf-8",
    )

    bullets = read_readme_bullets(tmp_path)

    assert "Indexes a repository" in bullets
    assert "Answers questions about it" in bullets


def test_missing_readme_yields_no_bullets(tmp_path):
    assert read_readme_bullets(tmp_path) == ()


def test_unreadable_readme_never_raises(tmp_path):
    """An unreadable README degrades the prompt, never the run."""
    directory = tmp_path / "README.md"
    directory.mkdir()  # a directory where a file is expected

    assert read_readme_bullets(tmp_path) == ()


def test_readme_bullets_are_truncated_at_a_line_boundary(tmp_path):
    """Half a capability description is worse than one fewer capability."""
    bullet = "- " + "x" * 200
    (tmp_path / "README.md").write_text("\n".join([bullet] * 40), encoding="utf-8")

    bullets = read_readme_bullets(tmp_path)

    assert bullets, "some bullets should survive"
    assert sum(len(line) + 1 for line in bullets) <= MAX_README_PROMPT_CHARS
    assert all(len(line) == 200 for line in bullets), "no bullet may be cut mid-line"


def test_evidence_reads_the_readme_of_the_analysed_repository(tmp_path):
    root, bundle, graph = _repo(tmp_path)
    (root / "README.md").write_text("# Repo\n\n- Reports things\n", encoding="utf-8")

    evidence = build_repository_evidence(bundle, graph, repository_root=root)

    assert "Reports things" in evidence.readmeBullets
