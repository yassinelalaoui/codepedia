from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import GenerationFailedError, InvalidResponseError
from .models import AvailabilityStatus, GenerationResult, PromptEnvelope, normalize_endpoint_url, normalize_model_name


def _local_fallback_message(endpoint_url: str, model_name: str) -> str:
    return (
        f"Local LLM service at {endpoint_url} is unavailable for model '{model_name}'. "
        "Start Ollama (or your local llama.cpp server) and ensure the model is installed locally. "
        "This tool never falls back to a cloud provider."
    )


def _read_json(url: str, *, timeout: float) -> dict[str, Any]:
    request = Request(url, method="GET")
    with urlopen(request, timeout=timeout) as response:  # nosec: local-only HTTP
        raw = response.read().decode("utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("expected a JSON object")
    return payload


def _post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:  # nosec: local-only HTTP
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed


def _extract_model_names(payload: dict[str, Any]) -> tuple[str, ...]:
    models = payload.get("models", [])
    if not isinstance(models, list):
        raise ValueError("models payload must be a list")
    names: list[str] = []
    for item in models:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return tuple(names)


def _model_is_installed(requested: str, installed: tuple[str, ...]) -> bool:
    requested = normalize_model_name(requested)
    base_requested = requested.split(":", 1)[0]
    for item in installed:
        if item == requested or item == base_requested:
            return True
        if item.split(":", 1)[0] == base_requested:
            return True
    return False


@dataclass(slots=True)
class LocalLLMTransport:
    endpointUrl: str
    timeout: float = 5.0
    # Real generation is a much slower call than the version/tags probes
    # `timeout` governs (auto-regressive token-by-token inference, easily
    # tens of seconds on CPU-only hardware or a cold model) - it gets its
    # own, much more generous budget rather than sharing `timeout`.
    generateTimeout: float = 120.0

    def __post_init__(self) -> None:
        self.endpointUrl = normalize_endpoint_url(self.endpointUrl)

    def version(self) -> dict[str, Any]:
        return _read_json(f"{self.endpointUrl}/api/version", timeout=self.timeout)

    def list_models(self) -> tuple[str, ...]:
        payload = _read_json(f"{self.endpointUrl}/api/tags", timeout=self.timeout)
        return _extract_model_names(payload)

    def availability(self, model_name: str) -> AvailabilityStatus:
        try:
            self.version()
        except (HTTPError, URLError, ValueError, json.JSONDecodeError, TimeoutError):
            return AvailabilityStatus(
                available=False,
                serviceReachable=False,
                modelInstalled=False,
                message=_local_fallback_message(self.endpointUrl, model_name),
            )
        try:
            installed = self.list_models()
        except (HTTPError, URLError, ValueError, json.JSONDecodeError, TimeoutError):
            return AvailabilityStatus(
                available=False,
                serviceReachable=True,
                modelInstalled=False,
                message=_local_fallback_message(self.endpointUrl, model_name),
            )
        model_installed = _model_is_installed(model_name, installed)
        if not model_installed:
            return AvailabilityStatus(
                available=False,
                serviceReachable=True,
                modelInstalled=False,
                message=(
                    f"Local model '{model_name}' is not installed at {self.endpointUrl}. "
                    "Pull or install the model locally, then try again. "
                    "This tool never falls back to a cloud provider."
                ),
            )
        return AvailabilityStatus(
            available=True,
            serviceReachable=True,
            modelInstalled=True,
            message=f"Local model '{model_name}' is available at {self.endpointUrl}.",
        )

    def generate(self, model_name: str, prompt: PromptEnvelope) -> GenerationResult:
        payload = prompt.to_request_payload(model_name)
        try:
            response = _post_json(f"{self.endpointUrl}/api/generate", payload, timeout=self.generateTimeout)
        except TimeoutError:
            raise GenerationFailedError(
                f"Local LLM at {self.endpointUrl} did not respond within {self.generateTimeout:g}s "
                f"while generating with model '{model_name}'. The service is reachable but generation "
                "is taking longer than that - it may still be loading the model into memory, or the "
                "model may be slow on this hardware. Wait for it to finish loading and try again, use "
                "a smaller/faster model, or increase the generation timeout.",
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            ) from None
        except (HTTPError, URLError):
            raise GenerationFailedError(
                _local_fallback_message(self.endpointUrl, model_name),
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            ) from None
        except (ValueError, json.JSONDecodeError) as exc:
            raise InvalidResponseError(
                f"Local LLM response from {self.endpointUrl} could not be parsed.",
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            ) from exc

        text = response.get("response")
        if not isinstance(text, str):
            raise InvalidResponseError(
                f"Local LLM response from {self.endpointUrl} did not include generated text.",
                endpointUrl=self.endpointUrl,
                modelName=model_name,
            )
        return GenerationResult(
            text=text,
            modelName=str(response.get("model", model_name)),
            endpointUrl=self.endpointUrl,
            rawResponse=response,
        )
