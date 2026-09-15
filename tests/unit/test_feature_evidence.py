from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))

import pytest  # noqa: E402
from _doc_generator_support import index_repo  # noqa: E402

from doc_generator.features.evidence import (  # noqa: E402
    MAX_README_LEAD_CHARS,
    MAX_README_PROMPT_CHARS,
    build_repository_evidence,
    find_readme,
    is_test_path,
    read_readme_bullets,
    read_readme_lead,
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


def test_find_readme_follows_candidate_order(tmp_path):
    """`.md` wins over `.rst`, and a directory holding neither has no README.

    Both the planner's bullets and the Overview's lead read through this, so
    the two can never describe the repository from different files.
    """
    assert find_readme(tmp_path) is None
    _write(tmp_path / "README.rst", "Title\n=====\n")
    assert find_readme(tmp_path) == tmp_path / "README.rst"
    _write(tmp_path / "README.md", "# Title\n")
    assert find_readme(tmp_path) == tmp_path / "README.md"


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


# --- Spec 039: the roles grouping needs (research Decision 3) ----------------


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_api.py",
        "src/test/java/com/acme/WalletTest.java",
        "pkg/service_test.go",
        "web/__tests__/app.js",
        "web/src/app.spec.ts",
        "web/src/app.test.tsx",
        "conftest.py",
    ],
)
def test_test_files_are_recognised_by_directory_or_name(path):
    assert is_test_path(path)


@pytest.mark.parametrize(
    "path",
    ["src/latest.py", "src/contest.py", "backend/Wallet.java", "web/src/app.ts", "README.md"],
)
def test_ordinary_files_are_not_test_files(path):
    assert not is_test_path(path)


def test_readme_lead_is_the_first_prose_paragraph(tmp_path):
    (tmp_path / "README.md").write_text(
        "# Project\n\n[![badge](x.svg)](y)\n\n- a list item\n\n"
        "Project **turns** code into a wiki. It runs locally.\n\n## Install\n\nLater text.\n",
        encoding="utf-8",
    )

    lead = read_readme_lead(tmp_path)

    assert lead == "Project turns code into a wiki. It runs locally."
    assert len(lead) <= MAX_README_LEAD_CHARS


def test_readme_lead_is_empty_without_a_readme(tmp_path):
    assert read_readme_lead(tmp_path) == ""


def _roles_repo(tmp_path: Path):
    """A test, a command, a `main`, an uncalled helper and two same-named modules."""
    root = tmp_path / "roles-repo"
    sources = {
        "tests/test_x.py": "def test_truth():\n    assert True\n",
        "cli.py": "@app.command()\ndef run():\n    return 0\n",
        "launcher.py": "def main():\n    return 0\n",
        "helpers.py": "def assist():\n    return 1\n",
        "pkg_a/__init__.py": '"""Package a."""\n',
        "pkg_b/__init__.py": '"""Package b."""\n',
    }
    files = [_write(root / name, text) for name, text in sources.items()]
    _write(
        root / "README.md",
        "# Roles\n\n[![build](b.svg)](c)\n\nRoles shows every kind of module. It is a fixture.\n",
    )
    store, graph = index_repo(tmp_path, root, files, "roles-repo.sqlite")
    bundle = store.load_repository(root)
    key_by_path = {
        Path(file_bundle.module.filePath).resolve().relative_to(root.resolve()).as_posix(): file_bundle.module.sourceFileId
        for file_bundle in bundle.files
    }
    return build_repository_evidence(bundle, graph, repository_root=root), key_by_path


def test_evidence_carries_the_readme_lead(tmp_path):
    evidence, _ = _roles_repo(tmp_path)

    assert evidence.readmeLead == "Roles shows every kind of module. It is a fixture."


def test_test_modules_are_listed_apart(tmp_path):
    evidence, key = _roles_repo(tmp_path)

    assert evidence.testModuleKeys == frozenset({key["tests/test_x.py"]})


def test_entry_modules_hold_a_command_a_route_or_main(tmp_path):
    """`helpers.assist` is an entry point, but only an uncalled one (FR-006a)."""
    evidence, key = _roles_repo(tmp_path)

    assert set(evidence.entryModuleKeys) == {key["cli.py"], key["launcher.py"]}
    assert list(evidence.entryModuleKeys) == sorted(evidence.entryModuleKeys)


def test_seeds_are_non_test_modules_with_entry_points(tmp_path):
    """The test's uncalled `test_truth` is an entry point, and still no seed (FR-008)."""
    evidence, key = _roles_repo(tmp_path)

    assert set(evidence.seedModuleKeys) == {key["cli.py"], key["launcher.py"], key["helpers.py"]}
    assert key["tests/test_x.py"] in evidence.entryPointModuleKeys, "033's field still counts tests"


def test_module_labels_tell_same_named_modules_apart(tmp_path):
    evidence, key = _roles_repo(tmp_path)

    labels = evidence.moduleLabels
    assert set(labels) == set(key.values())
    assert labels[key["pkg_a/__init__.py"]] != labels[key["pkg_b/__init__.py"]]
    assert labels[key["pkg_a/__init__.py"]] == "pkg_a/__init__"
