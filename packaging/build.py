"""Maintainer-run helper that builds the standalone `codepedia` binary
for the current OS and smoke-tests it (specs/020-cli-packaging,
research.md section 8, quickstart.md Scenario 1).

Usage:
    python -m pip install -e ".[build]"
    python packaging/build.py

PyInstaller does not cross-compile: run this once per target OS
(Windows/macOS/Linux) on a real machine of that OS. The produced binary is
written to dist/codepedia (dist/codepedia.exe on Windows) - see
packaging/README.md for what to do with it next.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = REPO_ROOT / "packaging" / "pyinstaller" / "codepedia.spec"
DIST_DIR = REPO_ROOT / "dist"
BINARY_NAME = "codepedia.exe" if sys.platform == "win32" else "codepedia"


def _run(command: list[str]) -> None:
    print(f"$ {' '.join(command)}")
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def build_binary() -> Path:
    _run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC_FILE)])
    binary_path = DIST_DIR / BINARY_NAME
    if not binary_path.exists():
        raise SystemExit(f"PyInstaller reported success but {binary_path} was not produced")
    return binary_path


def smoke_test(binary_path: Path) -> None:
    print(f"Smoke-testing {binary_path} ...")

    version_result = subprocess.run(
        [str(binary_path), "--version"], capture_output=True, text=True, check=False
    )
    if version_result.returncode != 0 or not version_result.stdout.strip():
        raise SystemExit(
            f"'{binary_path.name} --version' failed (exit {version_result.returncode}):\n"
            f"{version_result.stdout}{version_result.stderr}"
        )
    print(f"  --version -> {version_result.stdout.strip()}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        throwaway_repo = Path(tmp_dir) / "throwaway-repo"
        throwaway_repo.mkdir()
        (throwaway_repo / "example.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")

        scan_result = subprocess.run(
            [str(binary_path), "scan", str(throwaway_repo)], capture_output=True, text=True, check=False
        )
        if scan_result.returncode != 0:
            raise SystemExit(
                f"'{binary_path.name} scan' failed (exit {scan_result.returncode}):\n"
                f"{scan_result.stdout}{scan_result.stderr}"
            )
    print("  scan <throwaway repo> -> ok")


def main() -> None:
    if shutil.which("pyinstaller") is None:
        try:
            import PyInstaller  # noqa: F401
        except ImportError as exc:
            raise SystemExit(
                'PyInstaller is not installed. Run: python -m pip install -e ".[build]"'
            ) from exc

    binary_path = build_binary()
    smoke_test(binary_path)
    print(f"\nBuild OK: {binary_path}")
    print("See packaging/README.md for how to publish this as a GitHub Release asset.")


if __name__ == "__main__":
    main()
