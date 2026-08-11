from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbeddingError(RuntimeError):
    kind: str
    message: str
    endpointUrl: str
    modelName: str

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)

    def __str__(self) -> str:
        return self.message


class ServiceUnavailableError(EmbeddingError):
    def __init__(self, message: str, *, endpointUrl: str, modelName: str) -> None:
        super().__init__("service_unavailable", message, endpointUrl, modelName)


class ModelMissingError(EmbeddingError):
    def __init__(self, message: str, *, endpointUrl: str, modelName: str) -> None:
        super().__init__("model_missing", message, endpointUrl, modelName)


class InvalidInputError(EmbeddingError):
    def __init__(self, message: str, *, endpointUrl: str, modelName: str) -> None:
        super().__init__("invalid_input", message, endpointUrl, modelName)


class InvalidResponseError(EmbeddingError):
    def __init__(self, message: str, *, endpointUrl: str, modelName: str) -> None:
        super().__init__("invalid_response", message, endpointUrl, modelName)


class EmbeddingFailedError(EmbeddingError):
    def __init__(self, message: str, *, endpointUrl: str, modelName: str) -> None:
        super().__init__("embedding_failed", message, endpointUrl, modelName)
