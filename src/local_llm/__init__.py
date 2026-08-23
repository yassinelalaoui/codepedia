from __future__ import annotations

from .engine import LocalLLMEngine, create_local_llm_engine
from .errors import (
    GenerationFailedError,
    InvalidResponseError,
    LocalLLMError,
    MissingApiKeyError,
    ModelMissingError,
    RemoteGenerationFailedError,
    RemoteLLMError,
    RemoteServiceUnavailableError,
    ServiceUnavailableError,
)
from .groq_engine import GroqLLMEngine, create_groq_llm_engine
from .groq_transport import DEFAULT_GROQ_ENDPOINT_URL
from .models import AvailabilityStatus, DEFAULT_ENDPOINT_URL, DEFAULT_GENERATE_TIMEOUT, GenerationResult, PromptEnvelope
from .protocol import LLMEngine

__all__ = [
    "AvailabilityStatus",
    "GenerationFailedError",
    "GenerationResult",
    "GroqLLMEngine",
    "InvalidResponseError",
    "LLMEngine",
    "LocalLLMEngine",
    "LocalLLMError",
    "MissingApiKeyError",
    "ModelMissingError",
    "PromptEnvelope",
    "RemoteGenerationFailedError",
    "RemoteLLMError",
    "RemoteServiceUnavailableError",
    "ServiceUnavailableError",
    "create_groq_llm_engine",
    "create_llm_engine",
    "create_local_llm_engine",
]


def create_llm_engine(
    provider: str,
    model_name: str,
    endpoint_url: str | None = None,
    *,
    timeout: float = 5.0,
    generate_timeout: float | None = None,
) -> LLMEngine:
    """Build exactly one engine for the given provider - never a composite
    that tries another provider on failure (research.md Decision 2,
    constitution 2.3 v2.0.0). Takes plain primitives rather than a
    `CLIConfiguration` object so this package (an earlier layer, per
    `docs/architecture.md`) never depends on `cli` (a later one); the
    caller (`cli.index_command`/`cli.serve_command`) is responsible for
    picking the right values out of its own configuration."""
    if provider == "local":
        return create_local_llm_engine(
            model_name,
            endpoint_url if endpoint_url is not None else DEFAULT_ENDPOINT_URL,
            timeout=timeout,
            generate_timeout=generate_timeout if generate_timeout is not None else DEFAULT_GENERATE_TIMEOUT,
        )
    if provider == "groq":
        return create_groq_llm_engine(
            model_name,
            endpoint_url if endpoint_url is not None else DEFAULT_GROQ_ENDPOINT_URL,
            timeout=timeout,
            generate_timeout=generate_timeout if generate_timeout is not None else 120.0,
        )
    raise ValueError(f"Unknown LLM provider {provider!r}; expected 'local' or 'groq'.")
