from __future__ import annotations

from dataclasses import dataclass


# No slots=True - see local_llm/errors.py's LocalLLMError for why (frozen +
# slots rebuilds the class and breaks exception-chaining attribute sets).
@dataclass(frozen=True)
class FailoverExhaustedError(RuntimeError):
    stage: str
    attempted: tuple[str, ...]
    message: str
    kind: str = "failover_exhausted"

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)

    def __str__(self) -> str:
        return self.message
