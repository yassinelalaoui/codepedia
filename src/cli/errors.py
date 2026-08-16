from __future__ import annotations

from typing import NoReturn

import typer


class RepositoryNotFoundError(Exception):
    """The given repository path does not exist or is not a directory."""


class LocalModelUnavailableError(Exception):
    """The local LLM or embedding model is unreachable or not installed."""


class IndexNotFoundError(Exception):
    """`serve` was run against a repository `index` has never indexed."""


class ServerBindError(Exception):
    """The local web server could not bind to the requested host/port."""


def report_and_exit(err: Exception) -> NoReturn:
    """Print `err`'s message to stderr and exit non-zero.

    The single place every CLI command routes a failure through, so no
    command ever lets a raw traceback reach the terminal (spec.md's "Error
    messaging" requirement).
    """
    typer.echo(str(err), err=True)
    raise typer.Exit(code=1)
