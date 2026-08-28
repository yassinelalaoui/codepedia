from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from .errors import MissingApiKeyError, RateLimitedError, RemoteGenerationFailedError, RemoteServiceUnavailableError
from .groq_transport import DEFAULT_GROQ_ENDPOINT_URL, GroqLLMTransport
from .models import AvailabilityStatus, PromptEnvelope, normalize_model_name


def _availability_error(status: AvailabilityStatus, *, endpoint_url: str, model_name: str) -> Exception:
    if status.rateLimited:
        return RateLimitedError(status.message, endpointUrl=endpoint_url, modelName=model_name)
    if not status.serviceReachable:
        return RemoteServiceUnavailableError(status.message, endpointUrl=endpoint_url, modelName=model_name)
    if not status.modelInstalled:
        return MissingApiKeyError(status.message, endpointUrl=endpoint_url, modelName=model_name)
    return RemoteGenerationFailedError(status.message, endpointUrl=endpoint_url, modelName=model_name)


# How long an "available" verdict stays good without re-probing. Each
# `generateStream` pre-flights `GET /models`, so summarizing a repository used
# to cost two HTTP round-trips per symbol - one of them pure overhead, and one
# more request counted against the very rate limit it was checking for. A
# minute is short enough that a key revoked mid-run is noticed almost at once,
# and long enough to erase the second request across a whole indexing pass.
_AVAILABILITY_TTL_SECONDS = 60.0


@dataclass(slots=True)
class GroqLLMEngine:
    """An explicitly opt-in remote engine satisfying the same `LLMEngine`
    Protocol as `LocalLLMEngine` (research.md Decision 2/5) - never
    constructed unless an operator has deliberately configured
    `llmProvider: "groq"` (see `local_llm.create_llm_engine`)."""

    modelName: str
    endpointUrl: str = DEFAULT_GROQ_ENDPOINT_URL
    timeout: float = 5.0
    generateTimeout: float = 120.0
    availabilityTtlSeconds: float = _AVAILABILITY_TTL_SECONDS
    _transport: GroqLLMTransport = field(init=False, repr=False)
    _availability_lock: threading.Lock = field(init=False, repr=False)
    _cached_availability: Optional[AvailabilityStatus] = field(init=False, repr=False, default=None)
    _cached_availability_at: float = field(init=False, repr=False, default=0.0)

    def __post_init__(self) -> None:
        self.modelName = normalize_model_name(self.modelName)
        self._transport = GroqLLMTransport(self.endpointUrl, timeout=self.timeout, generateTimeout=self.generateTimeout)
        # One engine instance is shared by every thread of the indexing pool.
        self._availability_lock = threading.Lock()

    def checkAvailability(self) -> AvailabilityStatus:
        """The last "available" verdict, re-probed at most once per TTL.

        Only a positive verdict is cached. An unavailable one is never reused:
        a rate limit or an outage is exactly the state a caller wants to see
        clear as soon as it does, and re-probing is what notices that.
        """
        now = time.monotonic()
        with self._availability_lock:
            cached = self._cached_availability
            if cached is not None and now - self._cached_availability_at < self.availabilityTtlSeconds:
                return cached
        status = self._transport.availability(self.modelName)
        with self._availability_lock:
            if status.available:
                self._cached_availability = status
                self._cached_availability_at = time.monotonic()
            else:
                self._invalidate_availability_locked()
        return status

    def _invalidate_availability_locked(self) -> None:
        self._cached_availability = None
        self._cached_availability_at = 0.0

    def _invalidate_availability(self) -> None:
        with self._availability_lock:
            self._invalidate_availability_locked()

    def isAvailableLocally(self) -> bool:
        return self.checkAvailability().available

    def isAvailable(self) -> bool:
        return self.isAvailableLocally()

    def generate(self, prompt: str | PromptEnvelope) -> str:
        async def _drain() -> str:
            fragments = [fragment async for fragment in self.generateStream(prompt)]
            return "".join(fragments)

        return asyncio.run(_drain())

    async def generateStream(self, prompt: str | PromptEnvelope) -> AsyncIterator[str]:
        envelope = prompt if isinstance(prompt, PromptEnvelope) else PromptEnvelope.from_prompt(prompt)
        status = self.checkAvailability()
        if not status.available:
            raise _availability_error(status, endpoint_url=self.endpointUrl, model_name=self.modelName)
        try:
            async for fragment in self._transport.generate_stream(self.modelName, envelope):
                yield fragment
        except Exception:
            # A real generation failure contradicts whatever the cached verdict
            # said, so the next caller must probe for itself rather than trust
            # a stale "available".
            self._invalidate_availability()
            raise


def create_groq_llm_engine(
    model_name: str,
    endpoint_url: str = DEFAULT_GROQ_ENDPOINT_URL,
    *,
    timeout: float = 5.0,
    generate_timeout: float = 120.0,
) -> GroqLLMEngine:
    return GroqLLMEngine(
        modelName=model_name,
        endpointUrl=endpoint_url,
        timeout=timeout,
        generateTimeout=generate_timeout,
    )
