from __future__ import annotations

from typing import Any

from .errors import LocalModelUnavailableError


def check_ai_dependencies(**stage_engines: Any) -> None:
    """Verify every named stage's engine is available before any
    AI-dependent pipeline step runs (spec.md's "Local-model availability
    checks" requirement).

    Each keyword argument names a stage (e.g. `summary=...`,
    `embeddings=...`) and is anything exposing `isAvailable()` - in practice
    `local_llm.LocalLLMEngine` or `embedding_engine.EmbeddingEngine`.

    The error names the stage and the remedy rather than repeating the
    engine's own status message, because at this point the useful information
    is which stage cannot proceed; the engine's specific reason surfaces in
    full the moment a call is actually attempted.
    """
    for stage, engine in stage_engines.items():
        if not engine.isAvailable():
            raise LocalModelUnavailableError(
                f"The model for the '{stage}' stage is not available. Start Ollama and make sure "
                "the configured model is installed (`ollama list`, then `ollama pull <model>`), "
                "then try again."
            )
