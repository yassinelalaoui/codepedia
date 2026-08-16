from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


DEFAULT_ENDPOINT_URL = "http://localhost:11434"

# Real generation (auto-regressive token-by-token inference) is much slower
# than a version/tags probe, especially on CPU-only hardware or a model
# that's still loading - 120s is a generous default, and still user-tunable
# via `repo-scanner config --llm-generate-timeout` for slower setups.
DEFAULT_GENERATE_TIMEOUT = 120.0


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


def validate_model_name(model_name: str) -> str:
    value = model_name.strip()
    if not value:
        raise ValueError("modelName must not be empty")
    return value


def normalize_model_name(model_name: str) -> str:
    return validate_model_name(model_name)


@dataclass(frozen=True, slots=True)
class PromptEnvelope:
    promptText: str
    context: tuple[str, ...] = ()
    systemPrompt: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.promptText or not self.promptText.strip():
            raise ValueError("promptText must not be empty")
        object.__setattr__(self, "context", tuple(str(item) for item in self.context if str(item).strip()))
        object.__setattr__(self, "options", dict(self.options))

    @classmethod
    def from_prompt(
        cls,
        prompt_text: str,
        *,
        context: str | Sequence[str] | None = None,
        system_prompt: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> "PromptEnvelope":
        if context is None:
            normalized_context: tuple[str, ...] = ()
        elif isinstance(context, str):
            normalized_context = (context,)
        else:
            normalized_context = tuple(context)
        return cls(
            promptText=prompt_text,
            context=normalized_context,
            systemPrompt=system_prompt,
            options=dict(options or {}),
        )

    def to_prompt_text(self) -> str:
        sections: list[str] = []
        if self.systemPrompt:
            sections.append(f"System:\n{self.systemPrompt.strip()}")
        if self.context:
            context_text = "\n".join(item.strip() for item in self.context if item.strip())
            if context_text:
                sections.append(f"Context:\n{context_text}")
        sections.append(f"Prompt:\n{self.promptText.strip()}")
        return "\n\n".join(sections)

    def to_request_payload(self, model_name: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_name,
            "prompt": self.to_prompt_text(),
            "stream": False,
        }
        if self.options:
            payload["options"] = dict(self.options)
        return payload


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    modelName: str
    endpointUrl: str
    rawResponse: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AvailabilityStatus:
    available: bool
    serviceReachable: bool
    modelInstalled: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
