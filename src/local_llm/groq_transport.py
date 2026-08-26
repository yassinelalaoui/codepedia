from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import AsyncIterator

import httpx

from .errors import MissingApiKeyError, RateLimitedError, RemoteGenerationFailedError
from .models import AvailabilityStatus, PromptEnvelope

DEFAULT_GROQ_ENDPOINT_URL = "https://api.groq.com/openai/v1"

# Deliberately not a `local_llm.models`-validated endpoint: that validator
# (normalize_endpoint_url) enforces the local-only hostname guarantee and
# must stay untouched by this feature - Groq's endpoint is handled entirely
# separately, per research.md Decision 5.
API_KEY_ENV_VAR = "GROQ_API_KEY"


def _missing_key_message(endpoint_url: str, model_name: str) -> str:
    return (
        f"No {API_KEY_ENV_VAR} environment variable is set. Set it to a valid Groq API key "
        f"to use the remote model '{model_name}' at {endpoint_url}. This project never reads "
        "or stores this key anywhere but the environment - see `codepedia config --llm-provider groq`."
    )


def _build_messages(prompt: PromptEnvelope) -> list[dict[str, str]]:
    # Reuses PromptEnvelope.to_prompt_text() as a single "user" message,
    # exactly the same flattened prompt text the local engine sends -
    # keeps both engines behaviorally equivalent for the same envelope.
    return [{"role": "user", "content": prompt.to_prompt_text()}]


@dataclass(slots=True)
class GroqLLMTransport:
    endpointUrl: str = DEFAULT_GROQ_ENDPOINT_URL
    timeout: float = 5.0
    generateTimeout: float = 120.0

    def _api_key(self) -> str | None:
        return os.environ.get(API_KEY_ENV_VAR)

    def availability(self, model_name: str) -> AvailabilityStatus:
        api_key = self._api_key()
        if not api_key:
            # A missing key is a local configuration problem, not a network
            # one - serviceReachable=True keeps `_availability_error`
            # (groq_engine.py) picking MissingApiKeyError rather than
            # RemoteServiceUnavailableError for this case.
            return AvailabilityStatus(
                available=False,
                serviceReachable=True,
                modelInstalled=False,
                message=_missing_key_message(self.endpointUrl, model_name),
            )
        try:
            response = httpx.get(
                f"{self.endpointUrl}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=self.timeout,
            )
        except httpx.TransportError:
            return AvailabilityStatus(
                available=False,
                serviceReachable=False,
                modelInstalled=False,
                message=f"Groq API at {self.endpointUrl} is unreachable.",
            )
        if response.status_code in (401, 403):
            return AvailabilityStatus(
                available=False,
                serviceReachable=True,
                modelInstalled=False,
                message=f"Groq API rejected the configured {API_KEY_ENV_VAR} (HTTP {response.status_code}).",
            )
        if response.status_code == 429:
            return AvailabilityStatus(
                available=False,
                serviceReachable=True,
                modelInstalled=True,
                message=f"Groq API at {self.endpointUrl} is rate-limiting this key (HTTP 429).",
                rateLimited=True,
            )
        if response.status_code >= 400:
            return AvailabilityStatus(
                available=False,
                serviceReachable=False,
                modelInstalled=False,
                message=f"Groq API at {self.endpointUrl} returned HTTP {response.status_code}.",
            )
        try:
            payload = response.json()
            installed = {item.get("id") for item in payload.get("data", []) if isinstance(item, dict)}
        except (ValueError, json.JSONDecodeError):
            installed = set()
        if installed and model_name not in installed:
            return AvailabilityStatus(
                available=False,
                serviceReachable=True,
                modelInstalled=False,
                message=f"Model '{model_name}' was not found among Groq's available models at {self.endpointUrl}.",
            )
        return AvailabilityStatus(
            available=True,
            serviceReachable=True,
            modelInstalled=True,
            message=f"Remote model '{model_name}' is available via Groq.",
        )

    async def generate_stream(self, model_name: str, prompt: PromptEnvelope) -> AsyncIterator[str]:
        api_key = self._api_key()
        if not api_key:
            raise MissingApiKeyError(
                _missing_key_message(self.endpointUrl, model_name),
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            )
        payload = {"model": model_name, "messages": _build_messages(prompt), "stream": True}
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.generateTimeout) as client:
                async with client.stream(
                    "POST", f"{self.endpointUrl}/chat/completions", json=payload, headers=headers
                ) as response:
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError:
                        if response.status_code == 429:
                            raise RateLimitedError(
                                f"Groq API at {self.endpointUrl} is rate-limiting requests for model "
                                f"'{model_name}' (HTTP 429).",
                                endpointUrl=self.endpointUrl,
                                modelName=model_name,
                            ) from None
                        raise RemoteGenerationFailedError(
                            f"Groq API at {self.endpointUrl} rejected the request for model "
                            f"'{model_name}' (HTTP {response.status_code}).",
                            endpointUrl=self.endpointUrl,
                            modelName=model_name,
                        ) from None
                    async for line in response.aiter_lines():
                        if not line.strip() or not line.startswith("data:"):
                            continue
                        data = line[len("data:") :].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError as exc:
                            raise RemoteGenerationFailedError(
                                f"Groq API response from {self.endpointUrl} could not be parsed.",
                                endpointUrl=self.endpointUrl,
                                modelName=model_name,
                            ) from exc
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        text = delta.get("content")
                        if isinstance(text, str) and text:
                            yield text
        except httpx.TimeoutException:
            raise RemoteGenerationFailedError(
                f"Groq API at {self.endpointUrl} did not respond within {self.generateTimeout:g}s "
                f"while generating with model '{model_name}'.",
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            ) from None
        except httpx.TransportError:
            raise RemoteGenerationFailedError(
                f"Groq API at {self.endpointUrl} is unreachable.",
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            ) from None
