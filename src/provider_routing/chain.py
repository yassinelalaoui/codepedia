from __future__ import annotations

from dataclasses import dataclass

_KNOWN_KINDS = ("local", "groq", "openai")
_KNOWN_STAGES = ("embeddings", "summary", "chat")


@dataclass(frozen=True, slots=True)
class ProviderRef:
    """One provider entry within a chain (data-model.md `ProviderRef`).

    `str(ref)`/`ProviderRef.parse(...)` round-trip the `"<kind>:<model>"`
    form persisted in `CLIConfiguration`'s chain fields and stored as
    `attempted_provider`/`result_provider`/`generated_by` values.
    """

    kind: str
    model: str

    def __post_init__(self) -> None:
        if self.kind not in _KNOWN_KINDS:
            raise ValueError(f"kind must be one of {_KNOWN_KINDS!r}, got {self.kind!r}")
        if not self.model or not self.model.strip():
            raise ValueError("model must not be empty")

    def __str__(self) -> str:
        return f"{self.kind}:{self.model}"

    @classmethod
    def parse(cls, value: str) -> "ProviderRef":
        if ":" not in value:
            raise ValueError(f"invalid provider reference {value!r}; expected '<kind>:<model>'")
        kind, _, model = value.partition(":")
        return cls(kind=kind, model=model)


@dataclass(frozen=True, slots=True)
class ProviderChain:
    """An ordered, non-empty chain of providers for one AI-consuming stage
    (data-model.md `ProviderChain`)."""

    stage: str
    providers: tuple[ProviderRef, ...]

    def __post_init__(self) -> None:
        if self.stage not in _KNOWN_STAGES:
            raise ValueError(f"stage must be one of {_KNOWN_STAGES!r}, got {self.stage!r}")
        if not self.providers:
            raise ValueError("providers must be a non-empty tuple")
