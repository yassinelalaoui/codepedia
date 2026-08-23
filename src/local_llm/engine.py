from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator

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


@dataclass(slots=True)
class LocalLLMEngine:
    modelName: str
    endpointUrl: str = DEFAULT_ENDPOINT_URL
    timeout: float = 5.0
    generateTimeout: float = DEFAULT_GENERATE_TIMEOUT
    _transport: LocalLLMTransport = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.modelName = normalize_model_name(self.modelName)
        self.endpointUrl = normalize_endpoint_url(self.endpointUrl)
        self._transport = LocalLLMTransport(
            self.endpointUrl, timeout=self.timeout, generateTimeout=self.generateTimeout
        )

    def checkAvailability(self) -> AvailabilityStatus:
        return self._transport.availability(self.modelName)

    def isAvailableLocally(self) -> bool:
        return self.checkAvailability().available

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
        async for fragment in self._transport.generate_stream(self.modelName, envelope):
            yield fragment

    def generate_result(self, prompt: str | PromptEnvelope) -> GenerationResult:
        envelope = prompt if isinstance(prompt, PromptEnvelope) else PromptEnvelope.from_prompt(prompt)
        status = self.checkAvailability()
        if not status.available:
            raise _availability_error(status, endpoint_url=self.endpointUrl, model_name=self.modelName)
        return self._transport.generate(self.modelName, envelope)


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
