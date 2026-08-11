from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


DEFAULT_ENDPOINT_URL = "http://localhost:11434"
DEFAULT_MODEL_NAME = "nomic-embed-text"
Vector = tuple[float, ...]


def normalize_endpoint_url(endpoint_url: str) -> str:
    parsed = urlparse(endpoint_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("endpointUrl must use http or https")
    if not parsed.hostname:
        raise ValueError("endpointUrl must include a hostname")
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("endpointUrl must point to a local host")
    if parsed.path not in {"", "/"}:
        raise ValueError("endpointUrl must not include a path")
    return endpoint_url.rstrip("/")


def normalize_model_name(model_name: str) -> str:
    value = model_name.strip()
    if not value:
        raise ValueError("modelName must not be empty")
    return value


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    values: Vector

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", tuple(float(value) for value in self.values))

    def to_tuple(self) -> Vector:
        return self.values

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EmbeddingRequest:
    text: str
    sourceKind: str = "code"
    modelName: str = DEFAULT_MODEL_NAME
    options: dict[str, Any] = field(default_factory=dict)
    truncate: bool = True
    dimensions: int | None = None

    def __post_init__(self) -> None:
        if not self.text or not self.text.strip():
            raise ValueError("text must not be empty")
        object.__setattr__(self, "sourceKind", str(self.sourceKind).strip() or "code")
        object.__setattr__(self, "modelName", normalize_model_name(self.modelName))
        object.__setattr__(self, "options", dict(self.options))

    def to_prompt_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.modelName,
            "input": self.text,
            "truncate": self.truncate,
        }
        if self.options:
            payload["options"] = dict(self.options)
        if self.dimensions is not None:
            payload["dimensions"] = int(self.dimensions)
        return payload


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vector: Vector
    modelName: str
    endpointUrl: str
    rawResponse: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "vector", tuple(float(value) for value in self.vector))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EmbeddingAvailabilityStatus:
    available: bool
    runtimeReachable: bool
    modelInstalled: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
