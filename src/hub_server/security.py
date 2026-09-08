"""Who may reach the hub.

The hub reuses `chat_api.security` wholesale - the same per-run token, the same
`compare_digest`, the same allowed-hosts defence against DNS rebinding. That
module already reasons through why both exist, and restating it here would just
give the two a chance to disagree (research.md §9).

One thing is added, for one route. `EventSource` - the browser API the progress
stream uses - cannot set request headers, so it cannot present
`X-Codepedia-Token`. The token therefore has to be accepted from the query
string on that route, exactly as `chat_api` already accepts it in the URL it
prints for the wiki. The fallback is scoped to that single route: everywhere
else takes the header, so a credential cannot end up in a browser history entry
or a `Referer` for a request that never needed it there.
"""

from __future__ import annotations

import secrets

from starlette.requests import Request

from chat_api.security import TOKEN_HEADER, TOKEN_QUERY_PARAM, UnauthorizedError

__all__ = [
    "TOKEN_HEADER",
    "TOKEN_QUERY_PARAM",
    "UnauthorizedError",
    "require_hub_token",
    "require_hub_token_or_query",
]


def _expected(request: Request) -> str | None:
    return getattr(request.app.state, "authToken", None)


def _check(expected: str | None, presented: str | None, *, where: str) -> None:
    if not expected or not presented or not secrets.compare_digest(presented, expected):
        raise UnauthorizedError(
            f"This request needs the {where}. Reopen the URL printed when the homepage "
            "started - it carries the token."
        )


def require_hub_token(request: Request) -> None:
    """Header only. Guards everything that starts, opens or deletes something.

    Spec FR-005: a request without the credential cannot start an analysis, open
    a repository, or remove a stored analysis.
    """
    _check(_expected(request), request.headers.get(TOKEN_HEADER), where=f"{TOKEN_HEADER} header")


def require_hub_token_or_query(request: Request) -> None:
    """Header or `?token=`. For the progress stream only.

    Not a weakening of `require_hub_token` - the same token, compared the same
    way. It is a concession to `EventSource` having no way to send a header, and
    it is why the stream is a read-only route: it reports on a run, it cannot
    start or stop one.
    """
    presented = request.headers.get(TOKEN_HEADER) or request.query_params.get(TOKEN_QUERY_PARAM)
    _check(_expected(request), presented, where=f"{TOKEN_HEADER} header or ?{TOKEN_QUERY_PARAM}=")
