"""Small metric helpers; task-specific rubrics belong to each benchmark."""

from collections.abc import Sequence


def task_success_rate(successes: Sequence[bool]) -> float:
    """Fraction of successful instances; requires at least one instance."""
    if not successes:
        raise ValueError("at least one instance is required")
    return sum(successes) / len(successes)


def token_reduction(full_context_tokens: int, condition_tokens: int) -> float:
    """Relative input-token reduction against a Full Context baseline."""
    if full_context_tokens <= 0 or condition_tokens < 0:
        raise ValueError("token counts must be nonnegative and baseline positive")
    return 1.0 - condition_tokens / full_context_tokens
