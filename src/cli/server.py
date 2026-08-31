from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import uvicorn
from chat_api.app import create_app
from chat_api.security import allowed_hosts_for, generate_token, startup_lines

from .errors import ServerBindError


def start_local_server(
    vector_index: Any,
    embedding_engine: Any,
    llm_engine: Any,
    docs_root: Path,
    host: str,
    port: int,
    metadata_db_path: Path | None = None,
    dependency_graph: Any = None,
) -> None:
    """Serve the generated wiki + chat API and block until interrupted.

    Shared by `index` and `serve` (research.md §8) so both commands print the
    same URL message and handle a bind failure the same way.
    """
    # One token per run, printed once: the wiki is a static bundle generated
    # before this point, so the URL is the only channel that can carry it to
    # the browser.
    token = generate_token()
    app = create_app(
        vector_index, embedding_engine, llm_engine, docs_root, metadata_db_path,
        dependency_graph=dependency_graph,
        auth_token=token,
        allowed_hosts=allowed_hosts_for(host),
    )
    for line in startup_lines(host, port, token):
        typer.echo(line)
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
