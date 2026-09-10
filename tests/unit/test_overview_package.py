"""The `overview` package's invariant, checked by inspection (038 contract §1).

`evidence` and `grounding` take no LLM engine - not an optional one defaulting
to `None`, none - and never import the model client. `narrator` is the only
module allowed one. A signature that cannot accept an engine cannot hide a
model dependency, so "this stage works with no model" is a fact about the code
rather than a promise in a docstring.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import doc_generator.overview.evidence as evidence_module
import doc_generator.overview.grounding as grounding_module
import doc_generator.overview.narrator as narrator_module

ENGINE_PARAMETER_NAMES = {"llmEngine", "engine", "llm_engine"}


def _public_callables(module):
    for name, member in vars(module).items():
        if name.startswith("_") or getattr(member, "__module__", None) != module.__name__:
            continue
        if inspect.isclass(member):
            yield f"{name}.__init__", member.__init__
        elif inspect.isfunction(member):
            yield name, member


@pytest.mark.parametrize("module", [evidence_module, grounding_module], ids=["evidence", "grounding"])
def test_only_the_narrator_accepts_an_engine(module):
    for name, function in _public_callables(module):
        try:
            parameters = inspect.signature(function).parameters
        except (TypeError, ValueError):
            continue
        assert not ENGINE_PARAMETER_NAMES & set(parameters), f"{module.__name__}.{name} accepts an engine"

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "local_llm" not in source, f"{module.__name__} imports the model client"


def test_the_narrator_is_the_module_that_does():
    assert "llmEngine" in inspect.signature(narrator_module.OverviewNarrator.__init__).parameters
