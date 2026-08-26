from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import typer
except Exception:  # pragma: no cover
    typer = None

from .models import RepositoryScanRequest
from .output import serialize_scan_result
from .scanner import scan_repository


class _FallbackApp:
    def __call__(self) -> None:
        parser = argparse.ArgumentParser(
            prog="codepedia",
            description="Scan a local repository and emit source inventory JSON.",
        )
        subparsers = parser.add_subparsers(dest="command", required=True)
        scan_parser = subparsers.add_parser("scan", help="Scan a repository path")
        scan_parser.add_argument("repo_path")
        args = parser.parse_args()
        if args.command == "scan":
            _scan_command(args.repo_path)

    def command(self, name: str):  # pragma: no cover - decorator compatibility
        def decorator(func):
            return func

        return decorator


if typer is not None:
    app = typer.Typer(add_completion=False, help="Scan a local repository and emit source inventory JSON.")
else:
    app = _FallbackApp()


def _scan_command(repo_path: str) -> None:
    result = scan_repository(RepositoryScanRequest(root_path=Path(repo_path)))
    print(serialize_scan_result(result))


if typer is not None:

    @app.command("scan")
    def scan(repo_path: Path) -> None:
        _scan_command(str(repo_path))
