"""Minimal structural checks before passing a state to an executor."""

from math import isfinite

from .representation import CognitiveState


def validate_state(state: CognitiveState) -> list[str]:
    """Return validation errors; an empty list means the structure is usable."""
    errors: list[str] = []
    if not state.goal.objective.strip():
        errors.append("goal.objective is required")
    if not state.frontier.current_focus.strip():
        errors.append("frontier.current_focus is required")
    if not state.frontier.next_action.strip():
        errors.append("frontier.next_action is required")
    for index, belief in enumerate(state.world.beliefs):
        if not belief.claim.strip():
            errors.append(f"world.beliefs[{index}].claim is required")
        if not isfinite(belief.confidence) or not 0.0 <= belief.confidence <= 1.0:
            errors.append(f"world.beliefs[{index}].confidence must be in [0, 1]")
    return errors
