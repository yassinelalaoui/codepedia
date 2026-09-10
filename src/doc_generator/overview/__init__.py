"""The Overview page's narrative: evidence -> narrator -> grounding.

Three stages, of which **only the narrator may fail**. `evidence` and
`grounding` take no LLM engine argument at all - not an optional one defaulting
to `None`, none. `narrator` is the only module in this package that accepts
one, so "this stage works with no model" is a property of the signatures, and
`tests/unit/test_overview_package.py` checks it by inspection rather than by
trusting this sentence.

The shape is `features/`'s on purpose: one bounded call, a deterministic
acceptance pass, and failure that costs prose and never structure. A wiki built
with no provider and one built with a working key differ in the paragraphs at
the top of the Overview and nowhere else.

The budget constants are `features`' own, re-exported rather than restated: the
narrator's worst case is asserted against the same window the planner's is.
"""

from __future__ import annotations

from ..features import CHARS_PER_TOKEN, PROVIDER_TOKEN_BUDGET

__all__ = ["CHARS_PER_TOKEN", "PROVIDER_TOKEN_BUDGET"]
