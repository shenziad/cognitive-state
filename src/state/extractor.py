"""Interface for future API-based state extraction; no model is fixed yet."""

from typing import Protocol, Sequence

from .representation import CognitiveState


class StateExtractor(Protocol):
    def extract(self, history: Sequence[dict[str, str]], future_task: str) -> CognitiveState:
        """Produce a task-conditioned state using only the supplied history."""
        ...
