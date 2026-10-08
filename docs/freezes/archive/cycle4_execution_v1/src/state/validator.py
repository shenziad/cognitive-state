"""Structural validation only; factual validity needs evidence and review."""

from math import isfinite
from typing import Any

from .representation import CognitiveState


def validate_state_json(value: Any) -> list[str]:
    errors: list[str] = []

    def obj(item: Any, keys: set[str], path: str) -> bool:
        if not isinstance(item, dict) or set(item) != keys:
            errors.append(f"{path} must be an object with exactly {sorted(keys)}")
            return False
        return True

    def text(item: Any, path: str) -> None:
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{path} must be a nonempty string")

    def strings(item: Any, path: str, required: bool = False) -> None:
        if not isinstance(item, list):
            errors.append(f"{path} must be an array")
            return
        if required and not item:
            errors.append(f"{path} must contain at least one item")
        for i, entry in enumerate(item):
            text(entry, f"{path}[{i}]")

    if not obj(value, {"goal", "world", "frontier"}, "state"):
        return errors
    g, w, f = value["goal"], value["world"], value["frontier"]
    if obj(g, {"objective", "success_criteria", "constraints", "preferences"}, "goal"):
        text(g["objective"], "goal.objective")
        for key in ("success_criteria", "constraints", "preferences"):
            strings(g[key], f"goal.{key}", required=key == "success_criteria")
    if obj(w, {"facts", "beliefs", "assumptions"}, "world"):
        strings(w["facts"], "world.facts")
        strings(w["assumptions"], "world.assumptions")
        if not isinstance(w["beliefs"], list):
            errors.append("world.beliefs must be an array")
        else:
            for i, belief in enumerate(w["beliefs"]):
                path = f"world.beliefs[{i}]"
                if obj(belief, {"claim", "confidence"}, path):
                    text(belief["claim"], f"{path}.claim")
                    confidence = belief["confidence"]
                    if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                            or not 0 <= confidence <= 1 or not isfinite(confidence)):
                        errors.append(f"{path}.confidence must be a finite number in [0, 1]")
    if obj(f, {"current_focus", "information_needs", "next_action"}, "frontier"):
        text(f["current_focus"], "frontier.current_focus")
        strings(f["information_needs"], "frontier.information_needs")
        text(f["next_action"], "frontier.next_action")
    return errors


def validate_state(state: CognitiveState) -> list[str]:
    return validate_state_json(state.to_dict())
