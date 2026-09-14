"""`overview.narrator`: the one call, its budget, its cache and every failure.

The budget tests are computed from the constants, never from a literal, the way
`test_feature_planner.py` bounds the planner: raising any cap must move the
number and redden a test. A test asserting `== 4815` would restate the answer
and could not catch that.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

import doc_generator.overview.narrator as narrator_module
from doc_generator.manifest_store import open_doc_manifest_store
from doc_generator.overview import CHARS_PER_TOKEN, PROVIDER_TOKEN_BUDGET
from doc_generator.overview.evidence import (
    MAX_PROMPTED_ENTRY_FLOWS,
    MAX_PROMPTED_FEATURES,
    MAX_README_LEAD_CHARS,
    EntryFlow,
    FeatureBrief,
    OverviewEvidence,
)
from doc_generator.overview.narrator import (
    ENTRY_FLOW_CHARS,
    FEATURE_BLOCK_CHARS,
    HEADER_CHARS,
    MAX_NARRATIVE_RESPONSE_TOKENS,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_CHARS,
    OverviewNarrator,
    build_overview_prompt,
    narrative_cache_key,
    parse_narrative_reply,
    worst_case_call_tokens,
    worst_case_prompt_tokens,
)

REPLY = json.dumps({"lead": ["The system starts in `alpha_entry` and hands work to [[f0]]."]})


class RecordingEngine:
    """A local double for the FailoverExecutor. Counts calls, so "one" is observable."""

    def __init__(self, reply: str = REPLY, *, available: bool = True, raises: Exception | None = None):
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
        self.value = operation(self)
        return self

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.reply


def _brief(index: int, *, long: bool = False) -> FeatureBrief:
    filler = "x" * 400 if long else ""
    return FeatureBrief(
        handle=f"f{index}",
        featureKey=f"feature-{index}",
        title=f"Feature {index}" + ("y" * 50 if long else ""),
        description=f"Does {index}." + filler[:150],
        kind="capability",
        anchorName=f"mod{index}",
        anchorPath=f"src/pkg{index}/mod{index}.py" + filler[:100],
        anchorSummary="Summary." + filler[:110],
        memberNames=tuple(f"src/pkg{index}/m{m}.py" + filler[:40] for m in range(3)),
        entryPointCount=index,
    )


def _evidence(count: int = 3, *, long: bool = False) -> OverviewEvidence:
    briefs = tuple(_brief(i, long=long) for i in range(count))
    return OverviewEvidence(
        repositoryName="sample-repo" + ("z" * 200 if long else ""),
        languages=("Python",),
        readmeLead=("A tool that documents code. " * 40) if long else "A tool that documents code.",
        features=briefs,
        omittedFeatureCount=0,
        entryFlows=tuple(
            EntryFlow(
                qualifiedName="Cli.run" + ("q" * 300 if long else ""),
                kind="cli-command",
                modulePath="src/cli.py",
                featureHandle="f0",
                reachedHandles=tuple(f"f{i}" for i in range(min(count, 5))),
            )
            for _ in range(MAX_PROMPTED_ENTRY_FLOWS if long else 1)
        ),
        majorFeatureKeys=tuple(brief.featureKey for brief in briefs),
        featureTitles=tuple((brief.featureKey, brief.title) for brief in briefs),
    )


# --------------------------------------------------------------------------
# The budget ceiling - computed from the constants, never restated
# --------------------------------------------------------------------------


def test_worst_case_call_fits_the_provider_budget():
    assert worst_case_call_tokens() <= PROVIDER_TOKEN_BUDGET


def test_the_budget_arithmetic_is_the_documented_one():
    """Recomputed here independently, so a broken formula cannot satisfy the ceiling."""
    total_chars = (
        SYSTEM_PROMPT_CHARS
        + HEADER_CHARS
        + MAX_README_LEAD_CHARS
        + MAX_PROMPTED_FEATURES * FEATURE_BLOCK_CHARS
        + MAX_PROMPTED_ENTRY_FLOWS * ENTRY_FLOW_CHARS
    )

    assert worst_case_prompt_tokens() == total_chars // CHARS_PER_TOKEN
    assert worst_case_call_tokens() == worst_case_prompt_tokens() + MAX_NARRATIVE_RESPONSE_TOKENS


def test_raising_a_cap_would_break_the_budget(monkeypatch):
    """Real headroom, not unlimited headroom: the formula must depend on its inputs."""
    monkeypatch.setattr(narrator_module, "MAX_PROMPTED_FEATURES", MAX_PROMPTED_FEATURES * 4)

    assert narrator_module.worst_case_call_tokens() > PROVIDER_TOKEN_BUDGET


def test_system_prompt_fits_its_declared_size():
    assert len(SYSTEM_PROMPT) <= SYSTEM_PROMPT_CHARS


def test_a_real_prompt_stays_under_the_worst_case():
    """Maximum-size evidence, every field overlong: truncation holds the line."""
    envelope = build_overview_prompt(_evidence(MAX_PROMPTED_FEATURES, long=True))

    assert len(envelope.to_prompt_text()) // CHARS_PER_TOKEN <= worst_case_prompt_tokens()


def test_prompt_sets_low_reasoning_effort_and_the_response_cap():
    options = build_overview_prompt(_evidence()).options

    assert options == {"max_tokens": MAX_NARRATIVE_RESPONSE_TOKENS, "reasoning_effort": "low"}


def test_prompt_asks_for_two_to_four_lead_paragraphs_each_citing_a_listed_name():
    assert "two to four paragraphs" in SYSTEM_PROMPT
    assert "Every paragraph names at least one file or function in backticks" in SYSTEM_PROMPT
    assert "never directories" in SYSTEM_PROMPT
    assert "[[f2]]" in SYSTEM_PROMPT and "never f2 alone" in SYSTEM_PROMPT


def test_only_commands_routes_and_main_are_called_entry_points():
    """An uncalled function is labelled as such; paragraph 1 names an entry
    point only when a line is marked entry (research Decision 15)."""
    flows = tuple(
        EntryFlow(qualifiedName=f"f_{kind}", kind=kind, modulePath="src/a.py", featureHandle="", reachedHandles=())
        for kind in ("cli-command", "api-route", "main", "function")
    )
    text = build_overview_prompt(replace(_evidence(), entryFlows=flows)).promptText

    assert "entry (cli-command): `f_cli-command`" in text
    assert "entry (api-route): `f_api-route`" in text
    assert "entry (main): `f_main`" in text
    assert "uncalled: `f_function`" in text
    assert "entry (function)" not in text
    assert "main entry point" not in SYSTEM_PROMPT
    assert "if none is, it claims no entry point" in SYSTEM_PROMPT


def test_a_call_line_names_its_own_subsystem_apart_from_the_ones_it_reaches():
    """Written `file [[f3]] -> [[f5]]`, the owning subsystem read as a callee
    (research Decision 16)."""
    flow = EntryFlow(
        qualifiedName="App.main", kind="main", modulePath="src/App.java", featureHandle="f3", reachedHandles=("f5", "f1")
    )
    lone = replace(flow, reachedHandles=())
    text = build_overview_prompt(replace(_evidence(), entryFlows=(flow, lone))).promptText

    assert "entry (main): `App.main` in `src/App.java` (part of [[f3]]); its calls reach [[f5]], [[f1]]" in text
    assert "entry (main): `App.main` in `src/App.java` (part of [[f3]])\n" in text
    assert "->" not in text


def test_paragraph_three_lists_every_place_results_can_go_never_one_file():
    assert "names every such subsystem as a place results can go" in SYSTEM_PROMPT
    assert "never a single file as the only destination" in SYSTEM_PROMPT
    assert "then, next or finally" in SYSTEM_PROMPT


def test_prompt_asks_for_subsystem_paragraphs_keyed_by_handle():
    """User Story 2: one paragraph per *major* subsystem, keyed by its handle.
    Majors are marked in their own block, so the header does not grow."""
    evidence = replace(_evidence(3), majorFeatureKeys=("feature-0", "feature-2"))
    text = build_overview_prompt(evidence).promptText

    assert '"subsystems"' in SYSTEM_PROMPT
    assert "marked paragraph" in SYSTEM_PROMPT
    assert "at most three sentences" in SYSTEM_PROMPT
    assert "f0: Feature 0 (capability, 0 entry points, paragraph)" in text
    assert "f1: Feature 1 (capability, 1 entry points)" in text
    assert "f2: Feature 2 (capability, 2 entry points, paragraph)" in text


def test_format_version_two_changes_the_cache_key(monkeypatch):
    assert narrator_module.NARRATIVE_FORMAT_VERSION == "2"
    envelope = build_overview_prompt(_evidence())
    current = narrative_cache_key(envelope)
    monkeypatch.setattr(narrator_module, "NARRATIVE_FORMAT_VERSION", "1")

    assert narrator_module.narrative_cache_key(envelope) != current


def test_no_feature_key_or_url_reaches_the_prompt():
    text = build_overview_prompt(_evidence()).to_prompt_text()

    assert "feature-0" not in text
    assert "http" not in text


def test_truncation_never_leaves_an_unpaired_backtick():
    envelope = build_overview_prompt(_evidence(MAX_PROMPTED_FEATURES, long=True))

    for line in envelope.promptText.splitlines():
        assert line.count("`") % 2 == 0, line


def test_no_features_yields_skipped_with_reason_no_features_and_makes_no_call():
    engine = RecordingEngine()
    outcome = OverviewNarrator(engine).narrate(_evidence(0))

    assert (outcome.status, outcome.skipReason, engine.calls) == ("skipped", "no-features", 0)


# --------------------------------------------------------------------------
# The cache key - exactly what the model was shown
# --------------------------------------------------------------------------


def test_cache_key_is_stable_for_equal_evidence():
    assert narrative_cache_key(build_overview_prompt(_evidence())) == narrative_cache_key(build_overview_prompt(_evidence()))


def test_cache_key_changes_when_any_prompt_line_changes():
    base = _evidence()
    renamed = replace(base, features=(replace(base.features[0], title="Renamed"), *base.features[1:]))
    rewritten = replace(base, readmeLead="A different self-description.")

    keys = {narrative_cache_key(build_overview_prompt(evidence)) for evidence in (base, renamed, rewritten)}

    assert len(keys) == 3


# --------------------------------------------------------------------------
# Outcomes - one call, or none; never an exception for a provider behaviour
# --------------------------------------------------------------------------


def _narrator(tmp_path, engine):
    store = open_doc_manifest_store(tmp_path / "m.sqlite")
    return OverviewNarrator(engine, cache=store, repositoryId="repo"), store


def test_generated_reply_is_parsed_and_saved(tmp_path):
    narrator, store = _narrator(tmp_path, RecordingEngine())
    outcome = narrator.narrate(_evidence())

    assert outcome.status == "generated"
    assert outcome.reply.lead == ("The system starts in `alpha_entry` and hands work to [[f0]].",)
    assert store.load_latest_overview_narrative("repo")[1] == {"f0": "feature-0", "f1": "feature-1", "f2": "feature-2"}


def test_cache_hit_returns_cached_before_checking_availability(tmp_path):
    engine = RecordingEngine()
    narrator, _ = _narrator(tmp_path, engine)
    narrator.narrate(_evidence())
    engine.available = False

    outcome = narrator.narrate(_evidence())

    assert outcome.status == "cached"
    assert engine.calls == 1


def test_unavailable_engine_yields_unavailable(tmp_path):
    engine = RecordingEngine(available=False)
    narrator, _ = _narrator(tmp_path, engine)

    assert narrator.narrate(_evidence()).status == "unavailable"
    assert engine.calls == 0


def test_runtime_error_yields_failed(tmp_path):
    narrator, _ = _narrator(tmp_path, RecordingEngine(raises=RuntimeError("chain exhausted")))

    assert narrator.narrate(_evidence()).status == "failed"


def test_empty_reply_yields_unparseable(tmp_path):
    narrator, _ = _narrator(tmp_path, RecordingEngine(""))

    assert narrator.narrate(_evidence()).status == "unparseable"


def test_unparseable_reply_is_not_saved(tmp_path):
    narrator, store = _narrator(tmp_path, RecordingEngine("I'm afraid I can't do that"))

    assert narrator.narrate(_evidence()).status == "unparseable"
    assert store.load_latest_overview_narrative("repo") is None


def test_a_parseable_reply_is_saved_with_its_handle_map_even_if_nothing_grounds(tmp_path):
    fabricated = json.dumps({"lead": ["Everything happens in `DoesNotExist`."]})
    narrator, store = _narrator(tmp_path, RecordingEngine(fabricated))

    narrator.narrate(_evidence())

    assert store.load_latest_overview_narrative("repo")[0] == fabricated


def test_an_attribute_error_is_not_disguised_as_an_unavailable_provider(tmp_path):
    narrator, _ = _narrator(tmp_path, RecordingEngine(raises=AttributeError("run")))

    with pytest.raises(AttributeError):
        narrator.narrate(_evidence())


def test_the_narrator_calls_the_provider_chain_not_the_engine_directly(tmp_path):
    engine = RecordingEngine()
    narrator, _ = _narrator(tmp_path, engine)

    narrator.narrate(_evidence())

    assert engine.calls == 1, "run() was not used"
    assert engine.prompts, "the operation handed to run() never reached generate()"


@pytest.mark.parametrize(
    ("engine", "reason"),
    [
        (RecordingEngine(available=False), "unavailable"),
        (RecordingEngine(raises=RuntimeError("down")), "failed"),
        (RecordingEngine("not json"), "unparseable"),
    ],
)
def test_failure_with_an_earlier_row_returns_stale_with_the_stored_handle_map(tmp_path, engine, reason):
    store = open_doc_manifest_store(tmp_path / "m.sqlite")
    store.save_overview_narrative("repo", "an-older-prompt", REPLY, {"f0": "feature-old"})

    outcome = OverviewNarrator(engine, cache=store, repositoryId="repo").narrate(_evidence())

    assert outcome.status == "stale"
    assert outcome.staleReason == reason
    assert outcome.handleMap == {"f0": "feature-old"}
    assert outcome.reply.lead


def test_a_failure_never_overwrites_the_earlier_row(tmp_path):
    store = open_doc_manifest_store(tmp_path / "m.sqlite")
    store.save_overview_narrative("repo", "an-older-prompt", REPLY, {"f0": "feature-old"})

    OverviewNarrator(RecordingEngine("not json"), cache=store, repositoryId="repo").narrate(_evidence())

    assert store.load_latest_overview_narrative("repo") == (REPLY, {"f0": "feature-old"}, "")


def test_a_saved_reply_records_the_repository_fingerprint(tmp_path):
    narrator, store = _narrator(tmp_path, RecordingEngine())

    narrator.narrate(replace(_evidence(), repositoryFingerprint="fp-now"))

    assert store.load_latest_overview_narrative("repo")[2] == "fp-now"


def test_an_earlier_prompt_about_the_same_repository_is_not_stale(tmp_path):
    """Analyze finding I2: a prompt or format change alone - User Story 2's
    format version, a reworded system prompt - leaves the repository as it was,
    so its narrative must not be captioned "describes an earlier version"."""
    store = open_doc_manifest_store(tmp_path / "m.sqlite")
    store.save_overview_narrative("repo", "an-older-prompt", REPLY, {"f0": "feature-0"}, repository_fingerprint="fp-same")

    outcome = OverviewNarrator(RecordingEngine(available=False), cache=store, repositoryId="repo").narrate(
        replace(_evidence(), repositoryFingerprint="fp-same")
    )

    assert outcome.status == "previous-prompt"
    assert outcome.staleReason == "unavailable"
    assert outcome.reply.lead
    assert outcome.handleMap == {"f0": "feature-0"}


@pytest.mark.parametrize(("stored", "current"), [("fp-before", "fp-after"), ("", "fp-after"), ("", "")])
def test_a_different_or_unknown_fingerprint_is_still_stale(tmp_path, stored, current):
    store = open_doc_manifest_store(tmp_path / "m.sqlite")
    store.save_overview_narrative("repo", "an-older-prompt", REPLY, {}, repository_fingerprint=stored)

    outcome = OverviewNarrator(RecordingEngine(available=False), cache=store, repositoryId="repo").narrate(
        replace(_evidence(), repositoryFingerprint=current)
    )

    assert outcome.status == "stale"


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def test_parse_accepts_an_object_with_a_lead():
    assert parse_narrative_reply(REPLY).lead == ("The system starts in `alpha_entry` and hands work to [[f0]].",)


def test_parse_reads_the_subsystems_object():
    reply = parse_narrative_reply(
        json.dumps({"lead": ["One `a.py`."], "subsystems": {"f0": "Core `a.py`.", "f1": 7, "f2": "Io `b.py`."}})
    )

    assert reply.lead == ("One `a.py`.",)
    assert reply.subsystems == {"f0": "Core `a.py`.", "f2": "Io `b.py`."}


def test_parse_splits_blank_line_separated_paragraphs_in_one_string():
    reply = parse_narrative_reply(json.dumps({"lead": ["First `a.py`.\n\nSecond `b.py`.\n \nThird `c.py`."]}))

    assert reply.lead == ("First `a.py`.", "Second `b.py`.", "Third `c.py`.")


def test_parse_accepts_json_wrapped_in_prose():
    assert parse_narrative_reply(f"Here you go:\n{REPLY}\nThanks.").lead


@pytest.mark.parametrize("text", ["", "   ", "prose only", "[1, 2]", "{}", '{"lead": []}', '{"lead": [1, 2]}', "{not json}"])
def test_parse_rejects_a_list_prose_and_empty_objects(text):
    assert parse_narrative_reply(text) is None
