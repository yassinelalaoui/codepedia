"""Beta module."""

from gamma import BaseThing


class Child(BaseThing):
    """Child class."""

    def run(self, value: int) -> int:
        return beta_helper(value)


def beta_helper(number: int) -> int:
    """Helper doc."""
    return number + 1
