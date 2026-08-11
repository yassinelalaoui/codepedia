"""Alpha module."""

from beta import helper
from beta import helper
from gamma import shared_value


def alpha_entry(value: int) -> int:
    """Alpha entry."""

    def inner(step: int) -> int:
        return helper(step)

    return inner(value) + shared_value()
