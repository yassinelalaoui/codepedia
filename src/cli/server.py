from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import uvicorn
from chat_api.app import create_app

from .errors import ServerBindError


def start_local_server(
    vector_index: Any,
    embedding_engine: Any,
    llm_engine: Any,
    docs_root: Path,
    host: str,
    port: int,
) -> None:
    """Serve the generated wiki + chat API and block until interrupted.

    Shared by `index` and `serve` (research.md §8) so both commands print the
    same URL message and handle a bind failure the same way.
    """
    app = create_app(vector_index, embedding_engine, llm_engine, docs_root)
    typer.echo(f"Documentation wiki available at http://{host}:{port}/")
    try:
        uvicorn.run(app, host=host, port=port)
    except SystemExit as exc:
        # uvicorn.run() does not raise OSError on a bind failure (e.g. the
        # port already in use) — Config.bind_socket()/Server.startup() catch
        # it internally and call sys.exit(STARTUP_FAILURE), which surfaces
        # here as SystemExit rather than propagating the original OSError.
        raise ServerBindError(
            f"Could not start the server on {host}:{port} - the address may already be in use."
        ) from exc
