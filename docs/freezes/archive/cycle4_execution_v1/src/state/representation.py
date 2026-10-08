"""Cognitive State v0.2 data structures; see docs/cognitive_state_definition.md."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GoalState:
    objective: str
    success_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)


@dataclass
class Belief:
    claim: str
    confidence: float


@dataclass
class WorldModel:
    facts: list[str] = field(default_factory=list)
    beliefs: list[Belief] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


@dataclass
class FrontierState:
    current_focus: str
    information_needs: list[str] = field(default_factory=list)
    next_action: str = ""


@dataclass
class CognitiveState:
    goal: GoalState
    world: WorldModel
    frontier: FrontierState

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable G/W/F representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CognitiveState":
        """Parse untrusted extractor output after strict JSON validation."""
        from .validator import validate_state_json

        errors = validate_state_json(value)
        if errors:
            raise ValueError("; ".join(errors))
        return cls(
            GoalState(**value["goal"]),
            WorldModel(facts=value["world"]["facts"],
                       beliefs=[Belief(**b) for b in value["world"]["beliefs"]],
                       assumptions=value["world"]["assumptions"]),
            FrontierState(**value["frontier"]),
        )
