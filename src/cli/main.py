from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import List, Optional

import typer
from local_llm import LocalLLMError
from provider_routing import FailoverExhaustedError
from repo_scanner.models import RepositoryScanRequest
from repo_scanner.output import serialize_scan_result
from repo_scanner.scanner import scan_repository
from repository_metadata import SummaryPipelineError

from cli import config as config_module
from cli.config_command import run_config
from cli.disclosure import ensure_disclosure_acknowledged
from cli.errors import (
    IndexNotFoundError,
    LocalModelUnavailableError,
    RepositoryNotFoundError,
    ServerBindError,
    report_and_exit,
)
from cli.index_command import run_index
from cli.provider_command import run_provider_chain_set, run_provider_mode_full_local
from cli.serve_command import run_serve
from cli.server import start_local_server

# The pre-flight availability check (check_ai_dependencies, called inside
# run_index/run_serve) only rules out an unreachable service or a missing
# model *before* work starts. Once summarization/embedding/chat is actually
# running, a slow or misbehaving provider can still raise LocalLLMError, a
# FailoverExhaustedError (every provider in a chain unavailable), or
# SummaryPipelineError - those need to be caught here too, or they reach the
# terminal as a raw traceback instead of report_and_exit's clean, actionable
# message (its own stated contract).
_AI_PIPELINE_ERRORS = (LocalLLMError, SummaryPipelineError, FailoverExhaustedError)

# Subcommands that touch a chain-consuming stage - the disclosure gate
# (contracts/cli-provider-commands.md) runs before all of these; `scan` and
# `config --show` are read-only/static-analysis-only and are not gated
# (spec FR-014).
_DISCLOSURE_GATED_COMMANDS = {"index", "serve", "provider"}

app = typer.Typer(add_completion=False, help="Turn a local code repository into a browsable documentation wiki.")
provider_app = typer.Typer(add_completion=False, help="Manage per-stage AI provider chains and the full-local switch.")
app.add_typer(provider_app, name="provider")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


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
    invoked = ctx.invoked_subcommand
    if invoked in _DISCLOSURE_GATED_COMMANDS:
        ensure_disclosure_acknowledged(config_module.load_config())


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


@app.command("config")
def config_command(
    llm_model: Optional[str] = typer.Option(None, "--llm-model", help="Local LLM model to use for any 'local:' chain entry."),
    llm_endpoint: Optional[str] = typer.Option(None, "--llm-endpoint", help="Local LLM endpoint URL."),
    llm_generate_timeout: Optional[float] = typer.Option(
        None,
        "--llm-generate-timeout",
        help="Seconds to wait for the local LLM to finish generating a summary before failing (default: 120).",
    ),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model", help="Local embedding model to use for any 'local:' chain entry."),
    embedding_endpoint: Optional[str] = typer.Option(None, "--embedding-endpoint", help="Local embedding endpoint URL."),
    embedding_generate_timeout: Optional[float] = typer.Option(
        None,
        "--embedding-generate-timeout",
        help="Seconds to wait for the local embedding runtime to finish embedding before failing (default: 60).",
    ),
    show: bool = typer.Option(False, "--show", help="Show the current configuration without changing it."),
) -> None:
    """View or change local connection settings and see the current provider
    chains. Use `codepedia provider chain set`/`provider mode full-local`
    to change which providers a stage actually uses."""
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


@provider_app.command("mode")
def provider_mode(mode: str = typer.Argument(..., help="Only 'full-local' is currently supported.")) -> None:
    """`codepedia provider mode full-local` - atomically switch all three
    stages to local-only providers (spec FR-004)."""
    if mode != "full-local":
        report_and_exit(ValueError(f"Unknown provider mode {mode!r}; expected 'full-local'."))
    try:
        run_provider_mode_full_local()
    except ValueError as exc:
        report_and_exit(exc)


@provider_app.command("chain")
def provider_chain(
    action: str = typer.Argument(..., help="Only 'set' is currently supported."),
    stage: str = typer.Argument(..., help="'embeddings', 'summary', or 'chat'."),
    providers: List[str] = typer.Argument(..., help="One or more '<provider>:<model>' entries, in try-order."),
) -> None:
    """`codepedia provider chain set <stage> <provider:model>...` - replace
    one stage's provider chain (spec FR-006/FR-007)."""
    if action != "set":
        report_and_exit(ValueError(f"Unknown provider chain action {action!r}; expected 'set'."))
    try:
        run_provider_chain_set(stage, providers)
    except ValueError as exc:
        report_and_exit(exc)


if __name__ == "__main__":
    # Lets `python -m cli.main` invoke the CLI directly, and gives the
    # PyInstaller build (packaging/pyinstaller/codepedia.spec, 020) a real
    # entry script to run - the `codepedia` console-script wrapper
    # (pyproject.toml) already calls `app()` itself and doesn't need this.
    app()
