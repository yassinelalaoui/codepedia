from pathlib import Path

from repo_scanner.models import RepositoryScanRequest
from repo_scanner.scanner import scan_repository


def test_large_repository_scan_stays_streaming(tmp_path: Path):
    repo = tmp_path / "big"
    repo.mkdir()
    (repo / ".gitignore").write_text("", encoding="utf-8")
    src = repo / "src"
    src.mkdir()
    for index in range(1500):
        (src / f"file_{index}.py").write_text(f"print({index})\n", encoding="utf-8")
    result = scan_repository(RepositoryScanRequest(root_path=repo))
    assert len(result.entries) == 1500
    assert result.summary.included_files == 1500

