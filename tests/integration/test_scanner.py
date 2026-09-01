from pathlib import Path
from shutil import copytree

from repo_scanner.models import RepositoryScanRequest
from repo_scanner.scanner import scan_repository


def _create_polyglot_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "polyglot-repo"
    copytree(fixture, root, dirs_exist_ok=True)
    (root / ".git").mkdir(parents=True, exist_ok=True)
    return root


def test_scan_excludes_ignored_and_binary_files(tmp_path: Path):
    repo = _create_polyglot_repo(tmp_path / "repo")
    (repo / "binary.dat").write_bytes(b"\x00\x01\x02")
    result = scan_repository(RepositoryScanRequest(root_path=repo))
    paths = {entry.relative_path: entry.language for entry in result.entries}
    assert paths == {
        "src/js/app.js": "JavaScript",
        "src/java/Main.java": "Java",
        "src/py/module.py": "Python",
    }


def test_scan_handles_missing_repo(tmp_path: Path):
    missing = tmp_path / "missing"
    try:
        scan_repository(missing)
        assert False, "expected failure"
    except FileNotFoundError:
        assert True


def test_scan_bounds_markdown_to_the_documentation_perimeter(tmp_path: Path):
    # Every heading in an indexed Markdown file becomes a symbol, and every
    # symbol is one LLM summary call plus one embedding - so without a perimeter
    # a repository's generated scaffolding decides what an indexing run costs.
    repo = _create_polyglot_repo(tmp_path / "repo")
    (repo / "README.md").write_text("# Project\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (repo / "specs" / "003-feature").mkdir(parents=True)
    (repo / "specs" / "003-feature" / "spec.md").write_text("# Spec\n", encoding="utf-8")

    result = scan_repository(RepositoryScanRequest(root_path=repo))

    markdown = {entry.relative_path for entry in result.entries if entry.language == "Markdown"}
    assert markdown == {"README.md", "docs/architecture.md"}


def test_a_declared_perimeter_replaces_the_default(tmp_path: Path):
    repo = _create_polyglot_repo(tmp_path / "repo")
    (repo / "README.md").write_text("# Project\n", encoding="utf-8")
    (repo / "specs").mkdir()
    (repo / "specs" / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (repo / ".codepedia.json").write_text('{"docs": {"include": ["specs/**"]}}', encoding="utf-8")

    result = scan_repository(RepositoryScanRequest(root_path=repo))

    markdown = {entry.relative_path for entry in result.entries if entry.language == "Markdown"}
    assert markdown == {"specs/spec.md"}


def test_markdown_outside_the_perimeter_counts_as_unsupported_not_ignored(tmp_path: Path):
    # It is a file this build understands and deliberately declined, which is
    # what `unsupported_files` already means; `ignored_files` is `.gitignore`'s.
    repo = _create_polyglot_repo(tmp_path / "repo")
    (repo / "NOTES.md").write_text("# Notes\n", encoding="utf-8")

    result = scan_repository(RepositoryScanRequest(root_path=repo))

    assert result.summary.unsupported_files >= 1
    assert result.summary.ignored_files == 0
