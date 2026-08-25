from __future__ import annotations

from dataclasses import dataclass, field

from .models import DEFAULT_EMBED_TIMEOUT, EmbeddingAvailabilityStatus, Vector, normalize_model_name
from .openai_transport import DEFAULT_OPENAI_ENDPOINT_URL, OpenAIEmbeddingTransport

DEFAULT_OPENAI_MODEL_NAME = "text-embedding-3-small"


@dataclass(slots=True)
class OpenAIEmbeddingProvider:
    """An explicitly opt-in remote embedding provider satisfying the same
    `EmbeddingProvider` protocol as `EmbeddingEngine` (research.md §3/§4) -
    structured exactly like `local_llm.GroqLLMEngine`."""

    modelName: str = DEFAULT_OPENAI_MODEL_NAME
    endpointUrl: str = DEFAULT_OPENAI_ENDPOINT_URL
    timeout: float = 5.0
    embedTimeout: float = DEFAULT_EMBED_TIMEOUT
    _transport: OpenAIEmbeddingTransport = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.modelName = normalize_model_name(self.modelName)
        self._transport = OpenAIEmbeddingTransport(
            self.endpointUrl, timeout=self.timeout, embedTimeout=self.embedTimeout
        )

    def checkAvailability(self) -> EmbeddingAvailabilityStatus:
        return self._transport.availability(self.modelName)

    def isAvailable(self) -> bool:
        return self.checkAvailability().available

    def embed(self, text: str) -> Vector:
        return self._transport.embed(text, self.modelName)


def create_openai_embedding_provider(
    model_name: str = DEFAULT_OPENAI_MODEL_NAME,
    *,
    endpoint_url: str = DEFAULT_OPENAI_ENDPOINT_URL,
    timeout: float = 5.0,
    embed_timeout: float = DEFAULT_EMBED_TIMEOUT,
) -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider(
        modelName=model_name, endpointUrl=endpoint_url, timeout=timeout, embedTimeout=embed_timeout
    )
