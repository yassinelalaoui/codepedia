from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import httpx

from .errors import EmbeddingFailedError, MissingApiKeyError, RateLimitedError, ServiceUnavailableError
from .models import DEFAULT_EMBED_TIMEOUT, EmbeddingAvailabilityStatus, Vector

DEFAULT_OPENAI_ENDPOINT_URL = "https://api.openai.com/v1"

# Deliberately not validated by `models.normalize_endpoint_url`, which
# enforces the local-only hostname guarantee - OpenAI's endpoint is a
# genuine remote API, handled entirely separately (mirrors local_llm's
# Groq transport, research.md §4).
API_KEY_ENV_VAR = "OPENAI_API_KEY"


def _missing_key_message(model_name: str) -> str:
    return (
        f"No {API_KEY_ENV_VAR} environment variable is set. Set it to a valid OpenAI API key "
        f"to use the remote embedding model '{model_name}'. This project never reads or stores "
        "this key anywhere but the environment."
    )


@dataclass(slots=True)
class OpenAIEmbeddingTransport:
    endpointUrl: str = DEFAULT_OPENAI_ENDPOINT_URL
    timeout: float = 5.0
    embedTimeout: float = DEFAULT_EMBED_TIMEOUT

    def _api_key(self) -> Optional[str]:
        return os.environ.get(API_KEY_ENV_VAR)

    def availability(self, model_name: str) -> EmbeddingAvailabilityStatus:
        api_key = self._api_key()
        if not api_key:
            return EmbeddingAvailabilityStatus(False, True, False, _missing_key_message(model_name))
        try:
            response = httpx.get(
                f"{self.endpointUrl}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=self.timeout,
            )
        except httpx.TransportError:
            return EmbeddingAvailabilityStatus(
                False, False, False, f"OpenAI API at {self.endpointUrl} is unreachable."
            )
        if response.status_code in (401, 403):
            return EmbeddingAvailabilityStatus(
                False,
                True,
                False,
                f"OpenAI API rejected the configured {API_KEY_ENV_VAR} (HTTP {response.status_code}).",
            )
        if response.status_code == 429:
            return EmbeddingAvailabilityStatus(
                False, True, False, f"OpenAI API at {self.endpointUrl} is rate-limiting this key (HTTP 429)."
            )
        if response.status_code >= 400:
            return EmbeddingAvailabilityStatus(
                False, False, False, f"OpenAI API at {self.endpointUrl} returned HTTP {response.status_code}."
            )
        return EmbeddingAvailabilityStatus(
            True, True, True, f"Remote embedding model '{model_name}' is available via OpenAI."
        )

    def embed(self, text: str, model_name: str) -> Vector:
        api_key = self._api_key()
        if not api_key:
            raise MissingApiKeyError(
                _missing_key_message(model_name), endpointUrl=self.endpointUrl, modelName=model_name
            )
        payload = {"model": model_name, "input": text}
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            response = httpx.post(
                f"{self.endpointUrl}/embeddings", json=payload, headers=headers, timeout=self.embedTimeout
            )
        except httpx.TimeoutException:
            raise ServiceUnavailableError(
                f"OpenAI API at {self.endpointUrl} did not respond within {self.embedTimeout:g}s "
                f"while embedding with model '{model_name}'.",
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            ) from None
        except httpx.TransportError:
            raise ServiceUnavailableError(
                f"OpenAI API at {self.endpointUrl} is unreachable.",
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            ) from None

        if response.status_code in (401, 403):
            raise MissingApiKeyError(
                f"OpenAI API rejected the configured {API_KEY_ENV_VAR} (HTTP {response.status_code}).",
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            )
        if response.status_code == 429:
            raise RateLimitedError(
                f"OpenAI API at {self.endpointUrl} is rate-limiting requests for model '{model_name}' (HTTP 429).",
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            )
        if response.status_code >= 400:
            raise EmbeddingFailedError(
                f"OpenAI API at {self.endpointUrl} rejected the embedding request for model "
                f"'{model_name}' (HTTP {response.status_code}).",
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            )
        try:
            payload_response = response.json()
            vector = payload_response["data"][0]["embedding"]
            if not isinstance(vector, list):
                raise ValueError("embedding must be a list")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise EmbeddingFailedError(
                f"OpenAI API response from {self.endpointUrl} did not contain an embedding vector.",
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            ) from exc
        return tuple(float(value) for value in vector)
