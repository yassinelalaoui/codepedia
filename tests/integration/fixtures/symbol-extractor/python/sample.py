"""Module doc."""

import os
from pkg import mod

class Base:
    pass


class Child(Base):
    """Child doc."""

    def method(self, x: int) -> str:
        """Method doc."""
        def inner(y: int) -> int:
            return helper(y)

        return helper(x) + inner(x)


def helper(value: int) -> int:
    return value

