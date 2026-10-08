"""Benchmark contract; datasets and rubrics are selected per experiment."""

from typing import Any, Protocol


class Benchmark(Protocol):
    def evaluate(self, instance_id: str, agent_result: dict[str, Any]) -> dict[str, float]:
        """Score observable goal completion, tool use and decisions."""
        ...
