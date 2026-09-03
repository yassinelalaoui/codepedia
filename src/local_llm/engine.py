from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from .errors import GenerationFailedError, ModelMissingError, ServiceUnavailableError
from .models import (
    DEFAULT_ENDPOINT_URL,
    DEFAULT_GENERATE_TIMEOUT,
    AvailabilityStatus,
    GenerationResult,
    PromptEnvelope,
    normalize_endpoint_url,
    normalize_model_name,
)
from .transport import LocalLLMTransport


def _availability_error(status: AvailabilityStatus, *, endpoint_url: str, model_name: str) -> Exception:
    if not status.serviceReachable:
        return ServiceUnavailableError(status.message, endpointUrl=endpoint_url, modelName=model_name)
    if not status.modelInstalled:
        return ModelMissingError(status.message, endpointUrl=endpoint_url, modelName=model_name)
    return GenerationFailedError(status.message, endpointUrl=endpoint_url, modelName=model_name)


# How long an "available" verdict stays good without re-probing - the same
# reasoning, and the same duration, as `groq_engine._AVAILABILITY_TTL_SECONDS`.
# Every `generateStream` and `generate_result` pre-flights `checkAvailability`,
# which is a `GET /api/tags` listing every installed model, so summarizing a
# repository cost two round-trips per symbol where one would do. Localhost makes
# each cheap, not free, and the pre-flight is paid once per summary across a
# pool of `summaryConcurrency` threads all pointed at the same Ollama.
_AVAILABILITY_TTL_SECONDS = 60.0


@dataclass(slots=True)
class LocalLLMEngine:
    modelName: str
    endpointUrl: str = DEFAULT_ENDPOINT_URL
    timeout: float = 5.0
    generateTimeout: float = DEFAULT_GENERATE_TIMEOUT
    availabilityTtlSeconds: float = _AVAILABILITY_TTL_SECONDS
    _transport: LocalLLMTransport = field(init=False, repr=False)
    _availability_lock: threading.Lock = field(init=False, repr=False)
    _cached_availability: Optional[AvailabilityStatus] = field(init=False, repr=False, default=None)
    _cached_availability_at: float = field(init=False, repr=False, default=0.0)

    def __post_init__(self) -> None:
        self.modelName = normalize_model_name(self.modelName)
        self.endpointUrl = normalize_endpoint_url(self.endpointUrl)
        self._transport = LocalLLMTransport(
            self.endpointUrl, timeout=self.timeout, generateTimeout=self.generateTimeout
        )
        # One engine instance is shared by every thread of the indexing pool.
        self._availability_lock = threading.Lock()

    def checkAvailability(self) -> AvailabilityStatus:
        """The last "available" verdict, re-probed at most once per TTL.

        Only a positive verdict is cached. An unavailable one is never reused:
        a model still loading, or an Ollama that has not been started yet, is
        exactly the state a caller wants to see clear as soon as it does, and
        re-probing is what notices that.
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

    def listInstalledModels(self) -> tuple[str, ...]:
        return self._transport.list_models()

    def generate(self, prompt: str | PromptEnvelope) -> str:
        """Sync convenience wrapper: drains `generateStream` and
        concatenates (research.md Decision 1) - behaviorally identical to
        joining every fragment `generateStream` yields."""

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
            # a stale "available" - a model unloaded mid-run reads as reachable
            # for a whole TTL otherwise.
            self._invalidate_availability()
            raise

    def generate_result(self, prompt: str | PromptEnvelope) -> GenerationResult:
        envelope = prompt if isinstance(prompt, PromptEnvelope) else PromptEnvelope.from_prompt(prompt)
        status = self.checkAvailability()
        if not status.available:
            raise _availability_error(status, endpoint_url=self.endpointUrl, model_name=self.modelName)
        try:
            return self._transport.generate(self.modelName, envelope)
        except Exception:
            self._invalidate_availability()
            raise


def create_local_llm_engine(
    model_name: str,
    endpoint_url: str = DEFAULT_ENDPOINT_URL,
    *,
    timeout: float = 5.0,
    generate_timeout: float = DEFAULT_GENERATE_TIMEOUT,
) -> LocalLLMEngine:
    return LocalLLMEngine(
        modelName=model_name,
        endpointUrl=endpoint_url,
        timeout=timeout,
        generateTimeout=generate_timeout,
    )
