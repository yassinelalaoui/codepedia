from __future__ import annotations

from typing import Literal

FailureReason = Literal[
    "network_error", "rate_limited", "auth_failed", "model_missing", "empty_response", "unknown"
]

# spec FR-005 triggers failover on a network error, a rate/quota limit, or an
# authentication failure. Any other `.kind` (an invalid/unparseable response, a
# bad request, a generation failure) is a real error a chain switch cannot fix,
# so it is classified "unknown" and FailoverExecutor re-raises it instead of
# trying the next provider.
#
# "model_missing" is the exception, and it is here because the default chains
# now lead with `local:` (cli.config DEFAULT_*_CHAIN). An Ollama runtime that is
# up but has not pulled `qwen2.5-coder`/`nomic-embed-text` is the ordinary state
# of a fresh install, and unlike the kinds above it *is* fixable by a chain
# switch: the next entry is a different provider serving a different model
# entirely. Treating it as fatal would make the local-first default fail hard on
# exactly the machines the remote fallback exists to serve. It is kept distinct
# from "network_error" rather than folded into it so `engine_failover_log` still
# records why the switch happened - "pull the model" and "start the runtime" are
# different fixes for the operator reading that table.
#
# Note this also changes single-entry local chains (`provider mode full-local`):
# a missing model there now surfaces as FailoverExhaustedError naming
# "model_missing" rather than the engine's own ModelMissingError.
_KIND_TO_REASON: dict[str, FailureReason] = {
    "service_unavailable": "network_error",
    "rate_limited": "rate_limited",
    "missing_api_key": "auth_failed",
    "model_missing": "model_missing",
    # A provider that answered, but with nothing in it. Small local models do
    # this occasionally, and the next provider in the chain is a different
    # model that will very likely answer - so this switches rather than ending
    # the run. Raised by repository_metadata.summary_pipeline.EmptySummaryError.
    "empty_response": "empty_response",
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


def retry_after_seconds(exc: Exception) -> float | None:
    """How long the provider itself asked us to wait, or None if it did not say.

    Read off `.retryAfterSeconds`, the same uniform-attribute style
    `classify_failure` uses for `.kind` - so an engine family that has not
    grown the field yet simply reports None and the caller keeps guessing.
    Populated from the 429's `Retry-After` header by the remote transports
    (`local_llm.groq_transport`, `embedding_engine.openai_transport`).
    """
    value = getattr(exc, "retryAfterSeconds", None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return max(0.0, float(value))
