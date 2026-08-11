"""Beta module."""

from alpha import alpha_entry
from gamma import BaseThing


class Child(BaseThing):
    """Child class."""

    def run(self, value: int) -> int:
        def nested(delta: int) -> int:
            return alpha_entry(delta)

        return nested(value)


def helper(number: int) -> int:
    """Helper doc."""
    return number + 1
