"""Interface for continuing a task from one of the experimental inputs."""

from typing import Any, Protocol


class AgentExecutor(Protocol):
    def run(self, task: str, context: str, config: dict[str, Any]) -> dict[str, Any]:
        """Return actions and outcome for evaluation; implementation comes later."""
        ...
