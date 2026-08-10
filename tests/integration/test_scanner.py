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
