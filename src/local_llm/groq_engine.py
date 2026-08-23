from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator

from .errors import MissingApiKeyError, RemoteGenerationFailedError, RemoteServiceUnavailableError
from .groq_transport import DEFAULT_GROQ_ENDPOINT_URL, GroqLLMTransport
from .models import AvailabilityStatus, PromptEnvelope, normalize_model_name


def _availability_error(status: AvailabilityStatus, *, endpoint_url: str, model_name: str) -> Exception:
    if not status.serviceReachable:
        return RemoteServiceUnavailableError(status.message, endpointUrl=endpoint_url, modelName=model_name)
    if not status.modelInstalled:
        return MissingApiKeyError(status.message, endpointUrl=endpoint_url, modelName=model_name)
    return RemoteGenerationFailedError(status.message, endpointUrl=endpoint_url, modelName=model_name)


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
    _transport: GroqLLMTransport = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.modelName = normalize_model_name(self.modelName)
        self._transport = GroqLLMTransport(self.endpointUrl, timeout=self.timeout, generateTimeout=self.generateTimeout)

    def checkAvailability(self) -> AvailabilityStatus:
        return self._transport.availability(self.modelName)

    def isAvailableLocally(self) -> bool:
        return self.checkAvailability().available

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
        async for fragment in self._transport.generate_stream(self.modelName, envelope):
            yield fragment


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
