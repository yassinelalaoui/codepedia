from __future__ import annotations

from embedding_engine import EmbeddingEngine
from local_llm import LLMEngine

from .errors import LocalModelUnavailableError


def check_ai_dependencies(llm_engine: LLMEngine, embedding_engine: EmbeddingEngine) -> None:
    """Verify the local LLM and embedding model are available before any
    AI-dependent pipeline step runs (constitution 2.3; spec.md's
    "Local-model availability checks" requirement).

    Reuses `AvailabilityStatus`/`EmbeddingAvailabilityStatus`'s own message,
    which already distinguishes "service unreachable" from "model not
    installed" (008/009), rather than re-deriving that distinction here.
    """
    llm_status = llm_engine.checkAvailability()
    if not llm_status.available:
        raise LocalModelUnavailableError(llm_status.message)

    embedding_status = embedding_engine.checkAvailability()
    if not embedding_status.available:
        raise LocalModelUnavailableError(embedding_status.message)
