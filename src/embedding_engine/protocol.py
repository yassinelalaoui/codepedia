from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import EmbeddingAvailabilityStatus, Vector


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Structural interface both `EmbeddingEngine` (local) and
    the local `EmbeddingEngine` satisfies - the embedding-side
    counterpart to `local_llm.LLMEngine` (contracts/provider-protocols.md)."""

    def isAvailable(self) -> bool: ...

    def checkAvailability(self) -> EmbeddingAvailabilityStatus: ...

    def embed(self, text: str) -> Vector: ...
