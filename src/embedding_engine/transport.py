from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request
from urllib.parse import urljoin

from .errors import EmbeddingFailedError, InvalidResponseError, ModelMissingError, ServiceUnavailableError
from .models import (
    EmbeddingAvailabilityStatus,
    EmbeddingRequest,
    EmbeddingResult,
    normalize_endpoint_url,
)


def _build_url(endpoint_url: str, path: str) -> str:
    return urljoin(endpoint_url.rstrip("/") + "/", path.lstrip("/"))


@dataclass(slots=True)
class LocalEmbeddingTransport:
    endpointUrl: str
    timeout: float = 5.0

    def __post_init__(self) -> None:
        self.endpointUrl = normalize_endpoint_url(self.endpointUrl)

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(_build_url(self.endpointUrl, path), data=body, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
                if not raw:
                    return {}
                decoded = json.loads(raw.decode("utf-8"))
                if not isinstance(decoded, dict):
                    raise ValueError("response body must be a JSON object")
                return decoded
        except error.HTTPError as exc:
            detail = self._read_error_body(exc)
            raise InvalidResponseError(detail, endpointUrl=self.endpointUrl, modelName=str(payload.get("model", "")) if payload else "") from exc
        except (error.URLError, TimeoutError) as exc:
            raise ServiceUnavailableError(
                "The local embedding runtime is unavailable. Start the local service and try again.",
                endpointUrl=self.endpointUrl,
                modelName=str(payload.get("model", "")) if payload else "",
            ) from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise InvalidResponseError(
                "The local embedding runtime returned an invalid JSON response.",
                endpointUrl=self.endpointUrl,
                modelName=str(payload.get("model", "")) if payload else "",
            ) from exc

    def _read_error_body(self, exc: error.HTTPError) -> str:
        try:
            raw = exc.read().decode("utf-8").strip()
        except Exception:  # pragma: no cover
            raw = ""
        if raw:
            return raw
        return f"HTTP {exc.code} from local embedding runtime"

    def _model_name_matches(self, configured: str, candidate: str) -> bool:
        if configured == candidate:
            return True
        if ":" not in configured and candidate.split(":", 1)[0] == configured:
            return True
        if ":" not in candidate and configured.split(":", 1)[0] == candidate:
            return True
        return False

    def list_models(self) -> tuple[str, ...]:
        """Every installed model name known at this endpoint (via `/api/tags`).

        Reports both the `name` and `model` fields Ollama's `/api/tags`
        response may use per entry, matching `availability()`'s own matching
        below, deduplicated.
        """
        tags = self._request_json("GET", "/api/tags")
        models = tags.get("models", [])
        if not isinstance(models, list):
            raise InvalidResponseError(
                "The local embedding runtime responded, but the model list could not be read.",
                endpointUrl=self.endpointUrl,
                modelName="",
            )
        names: list[str] = []
        for entry in models:
            if not isinstance(entry, dict):
                continue
            for candidate in (str(entry.get("name", "")), str(entry.get("model", ""))):
                if candidate and candidate not in names:
                    names.append(candidate)
        return tuple(names)

    def availability(self, model_name: str) -> EmbeddingAvailabilityStatus:
        try:
            self._request_json("GET", "/api/version")
        except InvalidResponseError as exc:
            message = "The local embedding runtime responded, but the version payload was invalid."
            return EmbeddingAvailabilityStatus(False, True, False, message)
        except ServiceUnavailableError as exc:
            return EmbeddingAvailabilityStatus(
                False,
                False,
                False,
                "The local embedding runtime is not running. Start the local service before embedding.",
            )

        try:
            installed = self.list_models()
        except ServiceUnavailableError:
            return EmbeddingAvailabilityStatus(
                False,
                False,
                False,
                "The local embedding runtime is not running. Start the local service before embedding.",
            )
        except InvalidResponseError:
            return EmbeddingAvailabilityStatus(
                False,
                True,
                False,
                "The local embedding runtime responded, but the model list could not be read.",
            )

        if any(self._model_name_matches(model_name, candidate) for candidate in installed):
            return EmbeddingAvailabilityStatus(True, True, True, "The local embedding model is available.")

        return EmbeddingAvailabilityStatus(
            False,
            True,
            False,
            f"The local embedding model '{model_name}' is not installed. Pull or start the model locally and try again.",
        )

    def embed(self, request_data: EmbeddingRequest) -> EmbeddingResult:
        payload = request_data.to_prompt_payload()
        try:
            response = self._request_json("POST", "/api/embed", payload)
        except InvalidResponseError as exc:
            raise InvalidResponseError(
                "The local embedding runtime returned an invalid embedding response.",
                endpointUrl=self.endpointUrl,
                modelName=request_data.modelName,
            ) from exc
        except ServiceUnavailableError as exc:
            raise ServiceUnavailableError(
                "The local embedding runtime is unavailable. Start the local service and try again.",
                endpointUrl=self.endpointUrl,
                modelName=request_data.modelName,
            ) from exc

        vector = self._extract_vector(response, request_data.modelName)
        return EmbeddingResult(
            vector=vector,
            modelName=request_data.modelName,
            endpointUrl=self.endpointUrl,
            rawResponse=response,
        )

    def _extract_vector(self, response: dict[str, Any], model_name: str) -> tuple[float, ...]:
        if "embeddings" in response:
            embeddings = response["embeddings"]
            if isinstance(embeddings, list) and embeddings:
                first = embeddings[0]
                if isinstance(first, list):
                    return tuple(float(value) for value in first)
        if "embedding" in response and isinstance(response["embedding"], list):
            return tuple(float(value) for value in response["embedding"])
        raise InvalidResponseError(
            "The local embedding runtime response did not contain an embedding vector.",
            endpointUrl=self.endpointUrl,
            modelName=model_name,
        )
