"""Alpha module."""

from beta import beta_helper


def alpha_entry(value: int) -> int:
    """Alpha entry."""
    return beta_helper(value)
