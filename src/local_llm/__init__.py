from __future__ import annotations

from .engine import LocalLLMEngine, create_local_llm_engine
from .errors import (
    GenerationFailedError,
    InvalidResponseError,
    LocalLLMError,
    ModelMissingError,
    ServiceUnavailableError,
)
from .models import AvailabilityStatus, DEFAULT_ENDPOINT_URL, DEFAULT_GENERATE_TIMEOUT, GenerationResult, PromptEnvelope
from .protocol import LLMEngine

__all__ = [
    "AvailabilityStatus",
    "GenerationFailedError",
    "GenerationResult",
    "InvalidResponseError",
    "LLMEngine",
    "LocalLLMEngine",
    "LocalLLMError",
    "ModelMissingError",
    "PromptEnvelope",
    "ServiceUnavailableError",
    "create_llm_engine",
    "create_local_llm_engine",
]


def create_llm_engine(
    model_name: str,
    endpoint_url: str | None = None,
    *,
    timeout: float = 5.0,
    generate_timeout: float | None = None,
) -> LLMEngine:
    """Build the local engine.

    This used to take a `provider` argument and dispatch to one of two
    engines. There is only one now: inference happens on this machine or it
    does not happen (constitution 2.1 v4.0.0). The function is kept because
    callers already route through it, and because it remains the one place
    that turns "no endpoint given" into the local default - `cli` must not
    reach into this package's constants itself, since it sits above it in
    `docs/architecture.md`'s layering.
    """
    return create_local_llm_engine(
        model_name,
        endpoint_url if endpoint_url is not None else DEFAULT_ENDPOINT_URL,
        timeout=timeout,
        generate_timeout=generate_timeout if generate_timeout is not None else DEFAULT_GENERATE_TIMEOUT,
    )
