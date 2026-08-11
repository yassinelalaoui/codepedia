from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LocalLLMError(RuntimeError):
    kind: str
    message: str
    endpointUrl: str
    modelName: str

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)

    def __str__(self) -> str:
        return self.message


class ServiceUnavailableError(LocalLLMError):
    def __init__(self, message: str, *, endpointUrl: str, modelName: str) -> None:
        super().__init__("service_unavailable", message, endpointUrl, modelName)


class ModelMissingError(LocalLLMError):
    def __init__(self, message: str, *, endpointUrl: str, modelName: str) -> None:
        super().__init__("model_missing", message, endpointUrl, modelName)


class InvalidResponseError(LocalLLMError):
    def __init__(self, message: str, *, endpointUrl: str, modelName: str) -> None:
        super().__init__("invalid_response", message, endpointUrl, modelName)


class GenerationFailedError(LocalLLMError):
    def __init__(self, message: str, *, endpointUrl: str, modelName: str) -> None:
        super().__init__("generation_failed", message, endpointUrl, modelName)
