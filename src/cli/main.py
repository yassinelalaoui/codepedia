from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Optional

import typer
from local_llm import LocalLLMError
from repo_scanner.models import RepositoryScanRequest
from repo_scanner.output import serialize_scan_result
from repo_scanner.scanner import scan_repository
from repository_metadata import SummaryPipelineError

from cli import config as config_module
from cli.config_command import run_config
from cli.errors import (
    IndexNotFoundError,
    LocalModelUnavailableError,
    RepositoryNotFoundError,
    ServerBindError,
    report_and_exit,
)
from cli.index_command import run_index
from cli.serve_command import run_serve
from cli.server import start_local_server

# The pre-flight availability check (check_ai_dependencies, called inside
# run_index/run_serve) only rules out an unreachable service or a missing
# model *before* work starts. Once summarization is actually running, a slow
# or misbehaving local model can still raise LocalLLMError (e.g. a generation
# request that times out) or SummaryPipelineError - those need to be caught
# here too, or they reach the terminal as a raw traceback instead of
# report_and_exit's clean, actionable message (its own stated contract).
_AI_PIPELINE_ERRORS = (LocalLLMError, SummaryPipelineError)

app = typer.Typer(add_completion=False, help="Turn a local code repository into a browsable documentation wiki.")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def _version_callback(show_version: bool) -> None:
    if show_version:
        typer.echo(importlib.metadata.version("repo-scanner"))
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed repo-scanner version and exit.",
    ),
) -> None:
    return


@app.command("scan")
def scan(repo_path: Path) -> None:
    """Scan a repository and print a JSON inventory of its source files.

    Unchanged behavior from `repo_scanner.cli` (001) - re-registered under
    this shared entry point rather than reimplemented (research.md section 3).
    """
    result = scan_repository(RepositoryScanRequest(root_path=Path(repo_path)))
    print(serialize_scan_result(result))


@app.command("index")
def index(
    path: Path = typer.Argument(Path("."), help="Repository to index. Defaults to the current directory."),
    host: str = typer.Option(DEFAULT_HOST, "--host", help="Bind address for the local web server."),
    port: int = typer.Option(DEFAULT_PORT, "--port", help="Bind port for the local web server."),
) -> None:
    """Scan, parse, extract, summarize, embed, and generate a wiki for PATH,
    then serve it locally and print the URL."""
    cfg = config_module.load_config()
    try:
        result = run_index(path, config=cfg)
        start_local_server(result.vectorIndex, result.embeddingEngine, result.llmEngine, result.docsRoot, host, port)
    except (RepositoryNotFoundError, LocalModelUnavailableError, ServerBindError, *_AI_PIPELINE_ERRORS) as exc:
        report_and_exit(exc)


@app.command("serve")
def serve(
    path: Path = typer.Argument(Path("."), help="Already-indexed repository to serve. Defaults to the current directory."),
    host: str = typer.Option(DEFAULT_HOST, "--host", help="Bind address for the local web server."),
    port: int = typer.Option(DEFAULT_PORT, "--port", help="Bind port for the local web server."),
) -> None:
    """Serve an already-indexed repository with the watcher active, so
    file changes are reflected without a further command."""
    cfg = config_module.load_config()
    try:
        result = run_serve(path, config=cfg)
        try:
            start_local_server(result.vectorIndex, result.embeddingEngine, result.llmEngine, result.docsRoot, host, port)
        finally:
            if result.watcher is not None:
                result.watcher.stop()
    except (
        RepositoryNotFoundError,
        LocalModelUnavailableError,
        IndexNotFoundError,
        ServerBindError,
        *_AI_PIPELINE_ERRORS,
    ) as exc:
        report_and_exit(exc)


@app.command("config")
def config_command(
    llm_model: Optional[str] = typer.Option(None, "--llm-model", help="Local LLM model to use."),
    llm_endpoint: Optional[str] = typer.Option(None, "--llm-endpoint", help="Local LLM endpoint URL."),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model", help="Local embedding model to use."),
    embedding_endpoint: Optional[str] = typer.Option(None, "--embedding-endpoint", help="Local embedding endpoint URL."),
    show: bool = typer.Option(False, "--show", help="Show the current configuration without changing it."),
) -> None:
    """View or change which local LLM/embedding model `index`/`serve` use."""
    try:
        run_config(
            llm_model=llm_model,
            llm_endpoint=llm_endpoint,
            embedding_model=embedding_model,
            embedding_endpoint=embedding_endpoint,
            show=show,
        )
    except ValueError as exc:
        report_and_exit(exc)


if __name__ == "__main__":
    # Lets `python -m cli.main` invoke the CLI directly, and gives the
    # PyInstaller build (packaging/pyinstaller/repo-scanner.spec, 020) a real
    # entry script to run - the `repo-scanner` console-script wrapper
    # (pyproject.toml) already calls `app()` itself and doesn't need this.
    app()
