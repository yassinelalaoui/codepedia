from __future__ import annotations

from dataclasses import dataclass


# No slots=True: combined with frozen=True, it makes the dataclass decorator
# rebuild this class as a new object, but the generated __setattr__ closes
# over the pre-rebuild one. Any later attribute set on a subclass instance -
# including Python's own exception machinery setting __traceback__/__cause__
# while chaining/re-raising - then hits `super(old_class, self)` and raises
# an unrelated TypeError instead of letting the real error surface.
@dataclass(frozen=True)
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
