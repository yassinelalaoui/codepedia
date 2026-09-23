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
from cli.home_command import run_home
from cli.index_command import run_index
from cli.serve_command import run_serve
from cli.server import start_local_server

# The pre-flight availability check (check_ai_dependencies, called inside
# run_index/run_serve) only rules out an unreachable runtime or a missing
# model *before* work starts. Once summarization/embedding/chat is actually
# running, a slow or misbehaving model can still raise LocalLLMError or
# SummaryPipelineError - those need to be caught here too, or they reach the
# terminal as a raw traceback instead of report_and_exit's clean, actionable
# message (its own stated contract).
_AI_PIPELINE_ERRORS = (LocalLLMError, SummaryPipelineError)

app = typer.Typer(add_completion=False, help="Turn a local code repository into a browsable documentation wiki.")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
# Deliberately not `serve`'s port: a hub and a directly-run `serve` should not
# collide by default (contracts/home-command.md).
DEFAULT_HOME_PORT = 8100


def _version_callback(show_version: bool) -> None:
    if show_version:
        typer.echo(importlib.metadata.version("codepedia"))
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed codepedia version and exit.",
    ),
) -> None:
    # No disclosure gate: nothing this tool does sends repository content
    # anywhere. Every model call goes to a runtime on this machine
    # (constitution 2.1 v4.0.0), so there is no third party to disclose.
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
        start_local_server(
            result.vectorIndex, result.embeddingEngine, result.chatLlmEngine, result.docsRoot, host, port, result.metadataDbPath,
            dependency_graph=result.dependencyGraph,
        )
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
            start_local_server(
                result.vectorIndex, result.embeddingEngine, result.chatLlmEngine, result.docsRoot, host, port, result.metadataDbPath,
            dependency_graph=result.dependencyGraph,
            )
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


@app.command("home")
def home(
    host: str = typer.Option(DEFAULT_HOST, "--host", help="Bind address for the homepage server."),
    port: int = typer.Option(DEFAULT_HOME_PORT, "--port", help="Bind port for the homepage server."),
) -> None:
    """Start the Codepedia homepage: analyse a repository, or reopen one."""
    try:
        run_home(host, port)
    except ServerBindError as exc:
        report_and_exit(exc)


@app.command("config")
def config_command(
    llm_model: Optional[str] = typer.Option(None, "--llm-model", help="Ollama model used for summaries and chat."),
    llm_endpoint: Optional[str] = typer.Option(None, "--llm-endpoint", help="Local LLM endpoint URL."),
    llm_generate_timeout: Optional[float] = typer.Option(
        None,
        "--llm-generate-timeout",
        help="Seconds to wait for the local LLM to finish generating a summary before failing (default: 120).",
    ),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model", help="Ollama model used for embeddings."),
    embedding_endpoint: Optional[str] = typer.Option(None, "--embedding-endpoint", help="Local embedding endpoint URL."),
    embedding_generate_timeout: Optional[float] = typer.Option(
        None,
        "--embedding-generate-timeout",
        help="Seconds to wait for the local embedding runtime to finish embedding before failing (default: 60).",
    ),
    show: bool = typer.Option(False, "--show", help="Show the current configuration without changing it."),
) -> None:
    """View or change which local models this tool uses, and check whether
    the Ollama runtime has them installed."""
    try:
        run_config(
            llm_model=llm_model,
            llm_endpoint=llm_endpoint,
            llm_generate_timeout=llm_generate_timeout,
            embedding_model=embedding_model,
            embedding_endpoint=embedding_endpoint,
            embedding_generate_timeout=embedding_generate_timeout,
            show=show,
        )
    except ValueError as exc:
        report_and_exit(exc)


if __name__ == "__main__":
    # Lets `python -m cli.main` invoke the CLI directly, and gives the
    # PyInstaller build (packaging/pyinstaller/codepedia.spec, 020) a real
    # entry script to run - the `codepedia` console-script wrapper
    # (pyproject.toml) already calls `app()` itself and doesn't need this.
    app()
