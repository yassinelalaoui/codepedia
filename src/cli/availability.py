from __future__ import annotations

from typing import Any

from .errors import LocalModelUnavailableError


def check_ai_dependencies(**stage_executors: Any) -> None:
    """Verify every named stage's provider chain has at least one available
    provider before any AI-dependent pipeline step runs (constitution 2.3;
    spec.md's "Local-model availability checks" requirement).

    Each keyword argument names a stage (e.g. `summary=...`,
    `embeddings=...`) and is anything exposing `FailoverExecutor.isAvailable()`
    - a raw single engine or a `provider_routing.FailoverExecutor` both work
    uniformly (research.md §13's C1 fix). Since a multi-provider chain has no
    single status message to faithfully surface, the error names the stage
    rather than repeating one engine's specific reason - the specific reason
    still surfaces in full once `FailoverExecutor.run`/`.stream` is actually
    attempted and raises `FailoverExhaustedError`.
    """
    for stage, executor in stage_executors.items():
        if not executor.isAvailable():
            raise LocalModelUnavailableError(
                f"No provider in the '{stage}' chain is currently available. Start the local "
                "service, install the required model, or check your remote provider credentials, "
                "then try again."
            )
