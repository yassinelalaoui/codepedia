from __future__ import annotations

from typing import Literal

FailureReason = Literal["network_error", "rate_limited", "auth_failed", "unknown"]

# spec FR-005 triggers failover on exactly three reasons: network error,
# rate/quota limit, or authentication failure. Any other `.kind` (e.g. a
# missing local model, an invalid/unparseable response, a bad request) is a
# real error a chain switch cannot fix, so it is classified "unknown" and
# FailoverExecutor re-raises it instead of trying the next provider.
_KIND_TO_REASON: dict[str, FailureReason] = {
    "service_unavailable": "network_error",
    "rate_limited": "rate_limited",
    "missing_api_key": "auth_failed",
}


def classify_failure(exc: Exception) -> FailureReason:
    """Map an engine exception (a `local_llm`/`embedding_engine` error
    instance) to a failover reason, reading its `.kind` attribute - the same
    string every engine error family already exposes uniformly (research.md
    §6)."""
    kind = getattr(exc, "kind", None)
    if isinstance(kind, str) and kind in _KIND_TO_REASON:
        return _KIND_TO_REASON[kind]
    return "unknown"
