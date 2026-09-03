"""The one module that touches a model - tested with no model at all.

Every engine here is a local recording double. Nothing in this file reaches a
network, and the failure paths are asserted rather than assumed: an unreachable
provider and a silently rejected call are indistinguishable from the outside,
which is exactly why "the wiki still built" is not evidence that anything worked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from doc_generator.features import CHARS_PER_TOKEN, PROVIDER_TOKEN_BUDGET
from doc_generator.features.candidates import MAX_PROMPTED_CANDIDATES, Candidate
from doc_generator.features.evidence import (
    MAX_README_PROMPT_CHARS,
    FeatureEvidence,
    RepositoryEvidence,
)
from doc_generator.features.planner import (
    CANDIDATE_HEADER_CHARS,
    MAX_MEMBER_SUMMARY_CHARS,
    MAX_MEMBERS_PER_CANDIDATE,
    MAX_PLAN_RESPONSE_TOKENS,
    MEMBER_LINE_OVERHEAD_CHARS,
    SYSTEM_PROMPT_CHARS,
    FeaturePlanner,
    assign_handles,
    build_feature_plan_prompt,
    parse_feature_plan,
    plan_cache_key,
    target_feature_count,
    worst_case_call_tokens,
    worst_case_prompt_tokens,
)
from doc_generator.manifest_store import open_doc_manifest_store

MODULE_KEY_PREFIX = "repo::C:/Users/someone/projects/codepedia::file::C:/Users/someone/projects/codepedia/src"


class RecordingEngine:
    """A local double. Counts calls, so "exactly one" is observable."""

    def __init__(self, reply: str = "", *, available: bool = True, raises: Exception | None = None):
        self.reply = reply
        self.available = available
        self.raises = raises
        self.calls = 0
        self.prompts: list = []

    def isAvailable(self) -> bool:
        return self.available

    def run(self, operation):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self

    @property
    def value(self) -> str:
        return self.reply

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.reply


class CapturingEngine(RecordingEngine):
    """Runs the operation, so the rendered prompt can be inspected."""

    def run(self, operation):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        self.reply_value = operation(self)
        return self

    @property
    def value(self) -> str:
        return getattr(self, "reply_value", self.reply)


def _evidence(count: int = 6) -> RepositoryEvidence:
    return RepositoryEvidence(
        modules=tuple(
            FeatureEvidence(
                moduleKey=f"{MODULE_KEY_PREFIX}/pkg/mod_{index}.py",
                moduleName=f"mod_{index}",
                filePath=f"/r/src/pkg/mod_{index}.py",
                directoryPath="src/pkg",
                docstring=f"Module {index} does a thing.",
            )
            for index in range(count)
        ),
        readmeBullets=("Indexes a repository", "Answers questions about it"),
        entryPointKeysByModuleKey={f"{MODULE_KEY_PREFIX}/pkg/mod_0.py": ("mod_0::module::run",)},
    )


def _candidates(count: int = 3) -> list[Candidate]:
    return [
        Candidate(
            seedModuleKey=f"{MODULE_KEY_PREFIX}/pkg/mod_{index}.py",
            seedTitle=f"pkg - mod_{index}",
            memberKeys=(f"{MODULE_KEY_PREFIX}/pkg/mod_{index}.py",),
        )
        for index in range(count)
    ]


def _reply(*features) -> str:
    return json.dumps(list(features))


# --------------------------------------------------------------------------
# The budget ceiling - computed from the constants, never restated
# --------------------------------------------------------------------------


def test_worst_case_call_fits_the_provider_budget():
    """The assertion this whole prompt design exists to satisfy.

    Deliberately computed *from* the constants, so raising any cap moves the
    number and reddens this test. A test asserting `== 6145` would restate the
    answer and could not catch that.
    """
    assert worst_case_call_tokens() <= PROVIDER_TOKEN_BUDGET


def test_the_budget_arithmetic_is_the_documented_one():
    """Guards against the ceiling being satisfied by a broken formula.

    Recomputed here independently of `planner`'s own helper: if the two ever
    disagree, one of them has stopped describing the prompt that is actually
    built.
    """
    member_line = MEMBER_LINE_OVERHEAD_CHARS + MAX_MEMBER_SUMMARY_CHARS
    per_candidate = CANDIDATE_HEADER_CHARS + MAX_MEMBERS_PER_CANDIDATE * member_line
    total_chars = (
        MAX_PROMPTED_CANDIDATES * per_candidate + MAX_README_PROMPT_CHARS + SYSTEM_PROMPT_CHARS
    )

    assert worst_case_prompt_tokens() == total_chars // CHARS_PER_TOKEN
    assert worst_case_call_tokens() == worst_case_prompt_tokens() + MAX_PLAN_RESPONSE_TOKENS


def test_raising_a_cap_would_break_the_budget(monkeypatch):
    """The ceiling has real headroom, but not unlimited headroom.

    Doubling the candidate cap must exceed the budget - otherwise the assertion
    above is satisfied by a formula that ignores its inputs.
    """
    import doc_generator.features.planner as planner_module

    monkeypatch.setattr(planner_module, "MAX_PROMPTED_CANDIDATES", MAX_PROMPTED_CANDIDATES * 4)
    assert planner_module.worst_case_call_tokens() > PROVIDER_TOKEN_BUDGET


def test_a_real_prompt_stays_under_the_worst_case():
    candidates = assign_handles(_candidates(MAX_PROMPTED_CANDIDATES))
    evidence = _evidence(MAX_PROMPTED_CANDIDATES)

    envelope = build_feature_plan_prompt(candidates, evidence)
    rendered = envelope.to_prompt_text()

    assert len(rendered) // CHARS_PER_TOKEN <= worst_case_prompt_tokens()


# --------------------------------------------------------------------------
# Handles, never module keys
# --------------------------------------------------------------------------


def test_no_module_key_reaches_the_prompt():
    """The cheapest possible guard on the token budget.

    A module key on the real repository averages 116.6 characters; 135 of them
    is ~3,900 tokens of identifiers before a word of prose. If one ever leaks
    into the prompt, this fails long before a provider starts rejecting calls.
    """
    candidates = assign_handles(_candidates(4))
    evidence = _evidence(4)

    rendered = build_feature_plan_prompt(candidates, evidence).to_prompt_text()

    assert MODULE_KEY_PREFIX not in rendered
    assert "::file::" not in rendered


def test_handles_are_ordinal_and_round_trip():
    candidates = assign_handles(_candidates(3))

    assert [candidate.handle for candidate in candidates] == ["c0", "c1", "c2"]
    rendered = build_feature_plan_prompt(candidates, _evidence(3)).to_prompt_text()
    for handle in ("c0", "c1", "c2"):
        assert f"{handle}:" in rendered


def test_a_handle_is_not_part_of_a_candidates_identity():
    """Nothing persists a handle, so renumbering between runs is harmless."""
    original = _candidates(2)

    assign_handles(original)

    assert all(candidate.handle == "" for candidate in original)


def test_only_the_first_members_of_a_candidate_are_described():
    candidate = Candidate(
        seedModuleKey=f"{MODULE_KEY_PREFIX}/pkg/mod_0.py",
        seedTitle="pkg - mod_0",
        memberKeys=tuple(f"{MODULE_KEY_PREFIX}/pkg/mod_{i}.py" for i in range(10)),
    )
    rendered = build_feature_plan_prompt(assign_handles([candidate]), _evidence(10)).to_prompt_text()

    described = [line for line in rendered.splitlines() if line.strip().startswith("- mod_")]
    assert len(described) == MAX_MEMBERS_PER_CANDIDATE


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def test_parses_a_well_formed_reply():
    plan = parse_feature_plan(
        _reply({"title": "Indexing", "description": "d", "kind": "capability", "memberCandidateIds": ["c0"]})
    )

    assert plan is not None
    assert plan.features[0].title == "Indexing"
    assert plan.features[0].memberCandidateIds == ("c0",)


def test_parses_json_wrapped_in_prose():
    """Models add preambles. That is not a reason to lose the answer."""
    plan = parse_feature_plan(
        'Sure! Here is the plan:\n```json\n'
        + _reply({"title": "A", "kind": "capability", "memberCandidateIds": ["c0"]})
        + "\n```\nHope that helps."
    )

    assert plan is not None and plan.features[0].title == "A"


@pytest.mark.parametrize(
    "text",
    ["", "   ", "not json at all", "{}", "[]", '["a string"]', '[{"title": "no handles"}]'],
)
def test_an_unusable_reply_yields_no_plan(text):
    assert parse_feature_plan(text) is None


def test_a_partly_usable_reply_keeps_only_the_usable_entries():
    plan = parse_feature_plan(
        _reply(
            {"title": "Good", "kind": "capability", "memberCandidateIds": ["c0"]},
            "not an object",
            {"title": "No handles"},
        )
    )

    assert plan is not None
    assert len(plan.features) == 1


# --------------------------------------------------------------------------
# The call itself - exactly one, or none
# --------------------------------------------------------------------------


def test_exactly_one_call_per_plan():
    engine = RecordingEngine(_reply({"title": "A", "kind": "capability", "memberCandidateIds": ["c0"]}))
    planner = FeaturePlanner(engine)

    planner.plan(_candidates(3), _evidence(3))

    assert engine.calls == 1


def test_an_unavailable_engine_makes_no_call_and_returns_no_plan():
    engine = RecordingEngine(available=False)
    planner = FeaturePlanner(engine)

    assert planner.plan(_candidates(3), _evidence(3)) is None
    assert engine.calls == 0


def test_a_runtime_error_returns_no_plan():
    """Every provider failure is a RuntimeError - and none of them is fatal."""
    engine = RecordingEngine(raises=RuntimeError("all providers exhausted"))
    planner = FeaturePlanner(engine)

    assert planner.plan(_candidates(3), _evidence(3)) is None


def test_an_attribute_error_is_not_disguised_as_an_unavailable_provider():
    """A wiring bug must stay loud.

    Catching `Exception` here would turn "the engine has no such method" into a
    silent fallback that looks exactly like an offline provider - the failure
    shape this project keeps shipping.
    """
    engine = RecordingEngine(raises=AttributeError("run"))
    planner = FeaturePlanner(engine)

    with pytest.raises(AttributeError):
        planner.plan(_candidates(3), _evidence(3))


def test_an_unparseable_reply_returns_no_plan():
    engine = RecordingEngine("I'm afraid I can't do that")
    planner = FeaturePlanner(engine)

    assert planner.plan(_candidates(3), _evidence(3)) is None


def test_no_planner_call_when_there_are_no_candidates():
    engine = RecordingEngine(_reply({"title": "A", "kind": "capability", "memberCandidateIds": ["c0"]}))
    planner = FeaturePlanner(engine)

    assert planner.plan([], _evidence(3)) is None
    assert engine.calls == 0


def test_the_planner_calls_the_provider_chain_not_the_engine_directly():
    """`run`, never `generate`: the CLI hands over a FailoverExecutor."""
    engine = CapturingEngine(
        _reply({"title": "A", "kind": "capability", "memberCandidateIds": ["c0"]})
    )
    planner = FeaturePlanner(engine)

    planner.plan(_candidates(3), _evidence(3))

    assert engine.calls == 1, "run() was not used"
    assert engine.prompts, "the operation handed to run() never reached generate()"


def test_the_prompt_requests_a_bounded_response():
    envelope = build_feature_plan_prompt(assign_handles(_candidates(2)), _evidence(2))

    assert envelope.options.get("max_tokens") == MAX_PLAN_RESPONSE_TOKENS


# --------------------------------------------------------------------------
# Caching - the difference between one call per index and one per regeneration
# --------------------------------------------------------------------------


def test_a_cache_hit_makes_no_call(tmp_path: Path):
    store = open_doc_manifest_store(tmp_path / "manifest.sqlite")
    reply = _reply({"title": "Indexing", "kind": "capability", "memberCandidateIds": ["c0"]})
    candidates, evidence = _candidates(3), _evidence(3)

    first_engine = RecordingEngine(reply)
    FeaturePlanner(first_engine, cache=store, repositoryId="repo::r").plan(candidates, evidence)
    assert first_engine.calls == 1

    second_engine = RecordingEngine(reply)
    plan = FeaturePlanner(second_engine, cache=store, repositoryId="repo::r").plan(
        candidates, evidence
    )

    assert second_engine.calls == 0, "a second regeneration must not consult the model again"
    assert plan is not None and plan.features[0].title == "Indexing"


def test_a_changed_structure_invalidates_the_cache(tmp_path: Path):
    store = open_doc_manifest_store(tmp_path / "manifest.sqlite")
    reply = _reply({"title": "A", "kind": "capability", "memberCandidateIds": ["c0"]})
    FeaturePlanner(RecordingEngine(reply), cache=store, repositoryId="repo::r").plan(
        _candidates(3), _evidence(3)
    )

    engine = RecordingEngine(reply)
    FeaturePlanner(engine, cache=store, repositoryId="repo::r").plan(_candidates(4), _evidence(4))

    assert engine.calls == 1, "a module was added, so the plan must be recomputed"


def test_the_cache_key_ignores_summaries(tmp_path: Path):
    """Summaries land between the two regenerations of one indexing run.

    A content-keyed cache would miss on the second pass and spend a second call
    every single run - which is the whole cost this cache exists to avoid.
    """
    before = _evidence(3)
    after = RepositoryEvidence(
        modules=tuple(
            FeatureEvidence(
                moduleKey=item.moduleKey,
                moduleName=item.moduleName,
                filePath=item.filePath,
                directoryPath=item.directoryPath,
                docstring=item.docstring,
                generatedSummary="A summary written by a model after indexing.",
            )
            for item in before.modules
        ),
        readmeBullets=before.readmeBullets,
        entryPointKeysByModuleKey=before.entryPointKeysByModuleKey,
    )

    assert plan_cache_key(before) == plan_cache_key(after)


def test_a_failed_call_is_not_cached(tmp_path: Path):
    store = open_doc_manifest_store(tmp_path / "manifest.sqlite")
    FeaturePlanner(RecordingEngine("garbage"), cache=store, repositoryId="repo::r").plan(
        _candidates(3), _evidence(3)
    )

    engine = RecordingEngine(_reply({"title": "A", "kind": "capability", "memberCandidateIds": ["c0"]}))
    FeaturePlanner(engine, cache=store, repositoryId="repo::r").plan(_candidates(3), _evidence(3))

    assert engine.calls == 1, "an unusable answer must not be remembered as the plan"


# --------------------------------------------------------------------------
# Target count
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "modules,expected", [(0, 8), (40, 8), (80, 10), (139, 17), (400, 20), (10_000, 20)]
)
def test_target_feature_count_is_clamped(modules, expected):
    assert target_feature_count(modules) == expected


def test_the_prompt_suppresses_the_reasoning_channel():
    """Measured against the model this project is configured with.

    `openai/gpt-oss-20b` is a reasoning model. Left at its default it spent
    7,941 characters of reasoning on this prompt, hit `finish_reason: length`,
    and returned **zero characters of content** - a rejected plan that looks
    exactly like an unreachable provider, which is the one failure shape this
    project keeps shipping.

    It is also a budget requirement, not only a correctness one: the unsuppressed
    run emitted more reasoning tokens than the entire per-minute allowance the
    prompt is sized against, so `test_worst_case_call_fits_the_provider_budget`
    is only true while this holds.
    """
    envelope = build_feature_plan_prompt(assign_handles(_candidates(2)), _evidence(2))

    assert envelope.options.get("reasoning_effort") == "low"
