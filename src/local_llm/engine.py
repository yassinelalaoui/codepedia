from __future__ import annotations

from dataclasses import dataclass, field

from .errors import GenerationFailedError, ModelMissingError, ServiceUnavailableError
from .models import (
    DEFAULT_ENDPOINT_URL,
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
    generateTimeout: float = 120.0
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
        envelope = prompt if isinstance(prompt, PromptEnvelope) else PromptEnvelope.from_prompt(prompt)
        status = self.checkAvailability()
        if not status.available:
            raise _availability_error(status, endpoint_url=self.endpointUrl, model_name=self.modelName)
        result = self._transport.generate(self.modelName, envelope)
        return result.text

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
    generate_timeout: float = 120.0,
) -> LocalLLMEngine:
    return LocalLLMEngine(
        modelName=model_name,
        endpointUrl=endpoint_url,
        timeout=timeout,
        generateTimeout=generate_timeout,
    )
