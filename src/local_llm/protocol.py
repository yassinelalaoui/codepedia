from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from .models import AvailabilityStatus, PromptEnvelope


@runtime_checkable
class LLMEngine(Protocol):
    """Structural interface both `LocalLLMEngine` and `GroqLLMEngine` satisfy.

    `isAvailableLocally` keeps its pre-streaming name for both engines
    despite now also describing a remote engine's reachability - renaming it
    would touch call sites across `chat`, `cli`, and every existing test for
    no behavioral benefit (research.md Decision 2).
    """

    def isAvailableLocally(self) -> bool: ...

    def checkAvailability(self) -> AvailabilityStatus: ...

    def generate(self, prompt: str | PromptEnvelope) -> str: ...

    def generateStream(self, prompt: str | PromptEnvelope) -> AsyncIterator[str]: ...
