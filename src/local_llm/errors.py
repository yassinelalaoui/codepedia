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


# Same shape as LocalLLMError (kind/message/endpointUrl/modelName) so both
# error families are handled identically wherever an engine's errors
# surface (e.g. chat_api/app.py's `_error_code_for`) - only the "kind"
# values below name causes that don't apply to a local engine.
@dataclass(frozen=True)
class RemoteLLMError(RuntimeError):
    kind: str
    message: str
    endpointUrl: str
    modelName: str
    # Seconds the provider itself asked us to wait, from the 429's `Retry-After`
    # header; None when it did not say. A trailing field with a default, so
    # every subclass's positional `super().__init__(kind, message, endpointUrl,
    # modelName)` still works unchanged - only the rate-limit subclasses pass it.
    # Read by `provider_routing.classify.retry_after_seconds`.
    retryAfterSeconds: float | None = None

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)

    def __str__(self) -> str:
        return self.message


class RemoteServiceUnavailableError(RemoteLLMError):
    def __init__(self, message: str, *, endpointUrl: str, modelName: str) -> None:
        super().__init__("service_unavailable", message, endpointUrl, modelName)


class MissingApiKeyError(RemoteLLMError):
    def __init__(self, message: str, *, endpointUrl: str, modelName: str) -> None:
        super().__init__("missing_api_key", message, endpointUrl, modelName)


class RemoteGenerationFailedError(RemoteLLMError):
    def __init__(self, message: str, *, endpointUrl: str, modelName: str) -> None:
        super().__init__("generation_failed", message, endpointUrl, modelName)


class RateLimitedError(RemoteLLMError):
    def __init__(
        self,
        message: str,
        *,
        endpointUrl: str,
        modelName: str,
        retryAfterSeconds: float | None = None,
    ) -> None:
        super().__init__("rate_limited", message, endpointUrl, modelName, retryAfterSeconds)
