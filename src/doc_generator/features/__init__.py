"""Feature derivation: evidence -> candidates -> plan -> repair.

Four stages, of which **only the planner may fail**. `evidence`, `candidates`,
`fallback` and `validate` take no LLM engine argument at all - not an optional
one defaulting to `None`, none. A module that cannot accept an engine cannot
have a hidden model dependency, so "this stage works with no model" is a
property of the signature rather than a claim a test has to keep proving.

That matters here more than it looks: an unreachable model and a silently
rejected call produce the same wiki, so a navigation that quietly depended on
one would degrade with nothing anywhere reporting it.
"""

from __future__ import annotations

# The smallest per-minute token window this project is configured against
# (Groq's free tier). The planner's whole prompt-shaping design exists to fit
# inside it, so the number lives here rather than in `planner.py`: the test that
# asserts the ceiling must not import the module that could raise the ceiling.
PROVIDER_TOKEN_BUDGET = 8000

# Deliberately pessimistic. Real English runs nearer 4.5 characters per token,
# and a candidate's member lines are mostly identifiers, which tokenize worse
# than prose. Estimating low makes the budget assertion fail early rather than
# in production.
CHARS_PER_TOKEN = 4

__all__ = ["CHARS_PER_TOKEN", "PROVIDER_TOKEN_BUDGET"]
