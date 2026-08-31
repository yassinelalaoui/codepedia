"""Who may reach the chat API, and from what Host header.

The wiki and the API share one origin, and that origin renders Markdown built
from the documented repository. `doc_generator.html_sanitizer` is what keeps a
booby-trapped README from executing there - this module is the second half of
the same posture: even if something does execute, the API it would reach needs a
token nobody else has, and a `Host` nobody else can claim.

Two distinct defences, because they stop two distinct attackers:

* **The token** stops another process on this machine - or a page on another
  origin that guesses the port - from creating sessions, reading conversation
  history, or spending the LLM budget. It is generated per run, never persisted:
  a token that outlives the process would be one more secret to leak.
* **The allowed hosts** stop DNS rebinding, where an attacker's domain is made
  to resolve to 127.0.0.1 so a page they control becomes same-origin with this
  server. Starlette compares the `Host` header with the port stripped, so
  listing the address is enough - no port variants to enumerate.

The token guards the API routes only, not the wiki `StaticFiles` mount: an
ordinary page load cannot carry a custom header, and the pages are already
readable on disk by anything that could ask for them here. What is *not* on disk
- the LLM, the index, the conversation history - is exactly what the token
covers.
"""

from __future__ import annotations

import ipaddress
import secrets
from typing import Sequence

from starlette.requests import Request

# Read by the wiki bundle from `?token=` in the URL printed at startup, then
# sent on every API call (frontend/src/lib/apiToken.ts).
TOKEN_HEADER = "X-Codepedia-Token"
TOKEN_QUERY_PARAM = "token"

# The hosts a loopback-bound server legitimately answers to. A non-loopback bind
# adds its own address in `allowed_hosts_for`.
DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = ("127.0.0.1", "localhost", "::1")


class UnauthorizedError(Exception):
    """Raised when a request carries no valid API token (mapped to 401)."""

    kind = "unauthorized"


def generate_token() -> str:
    """A fresh token for one server run. 32 bytes, URL-safe: it travels in a URL."""
    return secrets.token_urlsafe(32)


def require_api_token(request: Request) -> None:
    """FastAPI dependency: reject a request whose token is missing or wrong.

    `compare_digest` rather than `==` so a wrong token takes the same time to
    reject whatever prefix it shares with the real one.
    """
    expected = getattr(request.app.state, "authToken", None)
    presented = request.headers.get(TOKEN_HEADER)
    if not expected or not presented or not secrets.compare_digest(presented, expected):
        raise UnauthorizedError(
            f"This request needs the {TOKEN_HEADER} header. Reopen the URL printed when the "
            "server started - it carries the token."
        )


def is_loopback_host(host: str) -> bool:
    """True when binding to `host` keeps the server on this machine only."""
    cleaned = host.strip().strip("[]")
    if cleaned in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(cleaned).is_loopback
    except ValueError:
        # A hostname we cannot resolve here; treat it as reachable from
        # elsewhere, which is the conservative half of the guess.
        return False


def allowed_hosts_for(host: str) -> tuple[str, ...]:
    """The `Host` values the server accepts when bound to `host`."""
    cleaned = host.strip().strip("[]")
    if not cleaned or cleaned in DEFAULT_ALLOWED_HOSTS:
        return DEFAULT_ALLOWED_HOSTS
    # 0.0.0.0/:: mean "every interface", which no browser ever sends as a Host.
    if cleaned in ("0.0.0.0", "::"):
        return DEFAULT_ALLOWED_HOSTS
    return (*DEFAULT_ALLOWED_HOSTS, cleaned)


def startup_lines(host: str, port: int, token: str) -> tuple[str, ...]:
    """What both entry points print once the server is up.

    The token rides in the URL because the wiki is a static bundle generated
    before the server starts: there is no other moment at which this run's token
    could reach the browser. The bundle moves it into `sessionStorage` and out of
    the address bar on first load.
    """
    lines = [
        f"Documentation wiki available at http://{host}:{port}/?{TOKEN_QUERY_PARAM}={token}",
        "Keep that URL private: the token authorizes the chat API for this run.",
    ]
    if not is_loopback_host(host):
        lines.append(
            f"WARNING: bound to {host}, so this server is reachable from other machines on "
            "the network. Anyone who obtains the token above can use the chat API."
        )
    return tuple(lines)


def print_startup_lines(host: str, port: int, token: str, write) -> None:  # noqa: ANN001 - echo/print
    for line in startup_lines(host, port, token):
        write(line)


__all__: Sequence[str] = (
    "DEFAULT_ALLOWED_HOSTS",
    "TOKEN_HEADER",
    "TOKEN_QUERY_PARAM",
    "UnauthorizedError",
    "allowed_hosts_for",
    "generate_token",
    "is_loopback_host",
    "print_startup_lines",
    "require_api_token",
    "startup_lines",
)
