"""Reading the one HTTP header this project's backoff cares about.

`provider_routing.BackoffPolicy` guesses how long a rate limit will last -
exponential, capped, jittered - while both remote providers answer a 429 with
`Retry-After`, saying how long it will actually last. Nothing in `src/` read
that header until now.

The parser lives in a package nothing else imports, for the same reason
`sqlite_support.apply_write_pragmas` does: `local_llm` and `embedding_engine`
both need it, neither may import the other, and neither may import
`provider_routing` (which imports *them*, via `provider_routing.factory`). A
copy per package would be two parsers to keep in agreement, with nothing
reporting a disagreement.
"""

from __future__ import annotations

from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any


__all__ = ["parse_retry_after"]


def parse_retry_after(headers: Any) -> float | None:
    """Seconds to wait per `Retry-After`, or None if the response did not say.

    RFC 9110 allows both forms and providers use both: a delay in seconds
    (Groq) and an HTTP-date (some OpenAI responses). A date already in the past
    clamps to 0.0 rather than going negative - "wait no longer" is what it
    means, and a negative floor would silently cancel the exponential term the
    caller adds on top.

    Anything unreadable returns None rather than raising: a malformed header is
    a reason to fall back on the guess, never a reason to fail the call that
    was already failing.
    """
    if headers is None:
        return None
    try:
        raw = headers.get("Retry-After")
    except Exception:  # noqa: BLE001 - a header mapping that will not answer is a None
        return None
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None

    try:
        return max(0.0, float(value))
    except ValueError:
        pass

    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    # A date without a zone is UTC by the spec's own reading of HTTP-date.
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
