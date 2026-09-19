"""The API tokens this machine reuses across runs.

`chat_api.security.generate_token` mints one per process, which is the safer
default for a server that could be started by anything. The CLI wants something
else: a token minted once and kept, so the reader opens the printed URL a single
time per browser profile and afterwards reaches the homepage or a wiki by typing
its address in any window. `frontend/src/lib/apiToken.ts` keeps its half of that
bargain by storing the value in `localStorage`, which every window of an origin
shares - a per-run token there would go stale on the next start.

What the trade buys and what it costs:

* **Buys:** the bare `http://127.0.0.1:<port>/` works everywhere, always. A
  second window, a bookmark, and a restarted server all keep chat working,
  because the value the browser remembers is still the value the server expects.
* **Costs:** the token now outlives the process, so it is a secret at rest
  rather than one that dies with the run. It is written to a file only this
  user can read (`0600`), under the home directory the rest of this package
  already keeps its state in, and it never travels anywhere the per-run token
  did not already go.

The hub and the wiki get *separate* values, as they did when both were minted
per run. They do not authorise the same things - the hub can start a long
analysis of any path on the machine and delete stored analyses, while the wiki
spends an LLM budget - and the wiki is the origin that renders Markdown built
from a documented repository. Keeping them apart means a token that leaks from
the page showing someone else's README does not also unlock the hub.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from chat_api.security import generate_token

from . import paths

#: The hub authorises more than the wiki, so the two never share a value.
TokenRole = Literal["hub", "wiki"]

__all__ = ["TokenRole", "load_or_create_token", "reuse_hint", "tokens_path"]


def tokens_path() -> Path:
    # Through the module, not a bound name: `cli.paths` documents that tests
    # redirect this by monkeypatching the attribute, which only reaches callers
    # that look it up at call time.
    return paths.codepedia_home() / "tokens.json"


def load_or_create_token(role: TokenRole) -> str:
    """This machine's token for `role`, minting and storing one on first use.

    A token that cannot be stored - a read-only home directory, a file this user
    may not write - is still returned, so the server starts and works for that
    run exactly as it did when every run minted its own. Only the convenience is
    lost, never the ability to serve.
    """
    path = tokens_path()
    stored = _read(path)
    existing = stored.get(role)
    if isinstance(existing, str) and existing:
        return existing

    token = generate_token()
    stored[role] = token
    _write(path, stored)
    return token


def reuse_hint(host: str, port: int) -> str:
    """The line that tells the reader the URL only has to be opened once."""
    return (
        f"Opened once, http://{host}:{port}/ then works in any window - "
        "your browser keeps the token and it stays valid on the next run."
    )


def _read(path: Path) -> dict:
    """What is stored, or nothing at all.

    A corrupt or unreadable file is treated as absent rather than fatal: the
    caller mints a fresh token and overwrites it, which is what a reader who
    deleted the file would expect anyway.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, tokens: dict) -> None:
    """Write `0600`, so the file is readable by this user only.

    `os.open` with the mode, rather than a write followed by `chmod`: the
    permissions are in place before the token is in the file, so it is never
    briefly world-readable. On Windows the mode only sets the read-only bit, and
    the protection is the ACL on the user profile that already covers the rest
    of `~/.codepedia`.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(tokens, handle, indent=2)
    except OSError:
        # Documented in `load_or_create_token`: serving still works, only the
        # reuse across runs is lost.
        pass
