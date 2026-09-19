"""`codepedia home` - the launcher homepage (contracts/home-command.md).

Takes no repository argument, which is the whole point: this is the entry point
you reach for when you do not yet have one in mind (spec FR-001).
"""

from __future__ import annotations

import typer
import uvicorn
from chat_api.security import TOKEN_QUERY_PARAM, is_loopback_host
from hub_server import create_hub_app
from hub_server.run_log import RunLog

from .errors import ServerBindError
from .tokens import load_or_create_token, reuse_hint


def startup_lines(host: str, port: int, token: str) -> tuple[str, ...]:
    """What `home` prints once it is up.

    Deliberately parallel to `chat_api.security.startup_lines`, but it says more
    about what the token authorises - because it authorises more. The wiki's
    token spends an LLM budget; this one can start a long-running analysis of
    any path on the machine and delete stored analyses.
    """
    lines = [
        f"Codepedia homepage available at http://{host}:{port}/?{TOKEN_QUERY_PARAM}={token}",
        "Keep that URL private: the token authorizes starting and removing analyses on this machine.",
    ]
    if not is_loopback_host(host):
        lines.append(
            f"WARNING: bound to {host}, so this server is reachable from other machines on "
            "the network. Anyone who obtains the token above can start and remove analyses "
            "on this machine."
        )
    return tuple(lines)


def run_home(host: str, port: int) -> None:
    """Start the hub and block until interrupted."""
    # Before serving anything: a run whose hub died is still recorded as
    # unfinished, and would otherwise read as in-progress forever and block
    # every future analysis (spec FR-026d).
    RunLog().sweep_interrupted()

    # Kept between runs, so the printed URL is opened once per browser and the
    # bare address works in every window afterwards (cli/tokens.py).
    token = load_or_create_token("hub")
    app = create_hub_app(auth_token=token, host=host)

    for line in startup_lines(host, port, token):
        typer.echo(line)
    typer.echo(reuse_hint(host, port))

    try:
        uvicorn.run(app, host=host, port=port)
    except SystemExit as exc:
        # uvicorn calls sys.exit(STARTUP_FAILURE) on a bind failure rather than
        # letting the OSError propagate - the same quirk `cli/server.py:47-53`
        # documents and handles.
        raise ServerBindError(
            f"Could not start the homepage on {host}:{port} - the address may already be in use."
        ) from exc
    finally:
        # Spec FR-007: the hub does not leave its children running.
        app.state.hub.shutdown()
