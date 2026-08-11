from __future__ import annotations

from dataclasses import dataclass, field

from .errors import (
    EmbeddingFailedError,
    InvalidInputError,
    InvalidResponseError,
    ModelMissingError,
    ServiceUnavailableError,
)
from .models import (
    DEFAULT_ENDPOINT_URL,
    DEFAULT_MODEL_NAME,
    EmbeddingAvailabilityStatus,
    EmbeddingRequest,
    EmbeddingResult,
    Vector,
    normalize_endpoint_url,
    normalize_model_name,
)
from .transport import LocalEmbeddingTransport


def _availability_error(status: EmbeddingAvailabilityStatus, *, endpoint_url: str, model_name: str) -> Exception:
    if not status.runtimeReachable:
        return ServiceUnavailableError(status.message, endpointUrl=endpoint_url, modelName=model_name)
    if not status.modelInstalled:
        return ModelMissingError(status.message, endpointUrl=endpoint_url, modelName=model_name)
    return EmbeddingFailedError(status.message, endpointUrl=endpoint_url, modelName=model_name)


@dataclass(slots=True)
class EmbeddingEngine:
    modelName: str = DEFAULT_MODEL_NAME
    endpointUrl: str = DEFAULT_ENDPOINT_URL
    timeout: float = 5.0
    _transport: LocalEmbeddingTransport = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.modelName = normalize_model_name(self.modelName)
        self.endpointUrl = normalize_endpoint_url(self.endpointUrl)
        self._transport = LocalEmbeddingTransport(self.endpointUrl, timeout=self.timeout)

    def checkAvailability(self) -> EmbeddingAvailabilityStatus:
        return self._transport.availability(self.modelName)

    def isAvailableLocally(self) -> bool:
        return self.checkAvailability().available

    def embed(self, text: str) -> Vector:
        try:
            request_data = EmbeddingRequest(text=text, modelName=self.modelName)
        except ValueError as exc:
            raise InvalidInputError(
                str(exc),
                endpointUrl=self.endpointUrl,
                modelName=self.modelName,
            ) from exc
        status = self.checkAvailability()
        if not status.available:
            raise _availability_error(status, endpoint_url=self.endpointUrl, model_name=self.modelName)
        try:
            result = self._transport.embed(request_data)
        except InvalidInputError:
            raise
        except InvalidResponseError:
            raise
        return result.vector

    def embed_result(self, text: str) -> EmbeddingResult:
        try:
            request_data = EmbeddingRequest(text=text, modelName=self.modelName)
        except ValueError as exc:
            raise InvalidInputError(
                str(exc),
                endpointUrl=self.endpointUrl,
                modelName=self.modelName,
            ) from exc
        status = self.checkAvailability()
        if not status.available:
            raise _availability_error(status, endpoint_url=self.endpointUrl, model_name=self.modelName)
        return self._transport.embed(request_data)


def create_embedding_engine(
    model_name: str = DEFAULT_MODEL_NAME,
    endpoint_url: str = DEFAULT_ENDPOINT_URL,
    *,
    timeout: float = 5.0,
) -> EmbeddingEngine:
    return EmbeddingEngine(modelName=model_name, endpointUrl=endpoint_url, timeout=timeout)
