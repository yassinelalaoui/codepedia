"""`overview.grounding`: one test per rule, on hand-written replies, no model.

Each rule is 038 research Decision 6's table row of the same name. The reply
objects are plain namespaces on purpose: grounding must accept anything shaped
like a reply, and must not need the narrator - the one module allowed an
engine - to be importable.
"""

from __future__ import annotations

import re
from dataclasses import replace
from types import SimpleNamespace

import pytest

from doc_generator.cross_references import build_symbol_lookup
from doc_generator.models import PageLink
from doc_generator.overview.evidence import FeatureBrief, OverviewEvidence
from doc_generator.overview.grounding import (
    MAX_LEAD_PARAGRAPHS,
    MAX_NARRATIVE_WORDS,
    MAX_SUBSYSTEM_PARAGRAPHS,
    accept_description,
    ground,
    render_paragraph,
)
from doc_generator.search_index import SearchIndexDocument, SearchIndexEntry

ROOT = "C:/work/sample-repo"


def _entry(name, kind, symbol_id, path):
    return SearchIndexEntry(
        name=name, kind=kind, symbolId=symbol_id, filePath=f"{ROOT}/{path}", pageUrl=f"modules/{symbol_id}.html", pageId=f"page-{symbol_id}"
    )


LOOKUP = build_symbol_lookup(
    SearchIndexDocument(
        generatedAt="",
        entries=(
            _entry("alpha", "module", "m-alpha", "alpha.py"),
            _entry("beta", "module", "m-beta", "beta.py"),
            _entry("alpha_entry", "function", "s-alpha-entry", "alpha.py"),
            _entry("Child", "class", "s-child", "beta.py"),
            _entry("Child.run", "method", "s-child-run", "beta.py"),
            _entry("__init__", "module", "m-init-a", "pkg_a/__init__.py"),
            _entry("__init__", "module", "m-init-b", "pkg_b/__init__.py"),
            _entry("store", "module", "m-store", "pkg_a/store.py"),
        ),
    )
)


def _brief(handle, key, title, kind="capability"):
    return FeatureBrief(
        handle=handle, featureKey=key, title=title, description="", kind=kind,
        anchorName="", anchorPath="", anchorSummary="", memberNames=(), entryPointCount=0,
    )


EVIDENCE = OverviewEvidence(
    repositoryName="sample-repo",
    languages=("Python", "TypeScript"),
    readmeLead="",
    features=(_brief("f0", "feat-core", "Core Engine"), _brief("f1", "feat-io", "Input Output")),
    omittedFeatureCount=0,
    entryFlows=(),
    majorFeatureKeys=("feat-core", "feat-io"),
    featureTitles=(("feat-core", "Core Engine"), ("feat-io", "Input Output")),
)
HANDLES = {"f0": "feat-core", "f1": "feat-io"}

GOOD = "The repository enters through `alpha_entry`, which hands work to [[f0]]."


def _ground(*lead, handle_map=HANDLES, evidence=EVIDENCE):
    return ground(SimpleNamespace(lead=list(lead), subsystems={}), evidence, LOOKUP, handle_map=handle_map)


def _rules(result):
    return [rejection.rule for rejection in result.rejected]


def test_a_good_paragraph_is_accepted():
    result = _ground(GOOD)

    assert len(result.lead) == 1
    assert result.rejected == ()


def test_empty_paragraph_is_dropped():  # G1
    result = _ground(GOOD, "   ")

    assert len(result.lead) == 1
    assert _rules(result) == ["G1"]


def test_unbalanced_backtick_rejects_the_paragraph():  # G2
    result = _ground(GOOD, "It calls `alpha_entry and stops.")

    assert _rules(result) == ["G2"]


def test_unknown_handle_rejects_the_paragraph():  # G3
    result = _ground(GOOD, "Work reaches `beta.py` and [[f7]].")

    assert _rules(result) == ["G3"]


def test_a_stale_handle_to_a_vanished_feature_rejects_the_paragraph():  # G3
    stale_map = {"f0": "feat-core", "f1": "feat-deleted"}
    result = _ground(GOOD, "Output leaves through `beta.py` in [[f1]].", handle_map=stale_map)

    assert _rules(result) == ["G3"]


def test_a_fabricated_symbol_rejects_its_paragraph():  # G4 — required by the runbook
    result = _ground(GOOD, "Loans are priced by `LoanPricingEngine` before `beta.py` stores them.")

    assert len(result.lead) == 1
    assert [(r.rule, r.token) for r in result.rejected] == [("G4", "LoanPricingEngine")]


def test_an_ambiguous_bare_name_rejects_its_paragraph():  # G4
    result = _ground(GOOD, "Each package starts in `__init__`.")

    assert _rules(result) == ["G4"]


def test_a_repo_relative_module_path_is_accepted():  # G4
    result = _ground("Storage lives in `pkg_a/store.py` and `pkg_a/__init__.py`.")

    assert result.rejected == ()


def test_the_repository_name_in_backticks_is_accepted_but_is_not_a_citation():  # G4, G7
    assert _ground("`sample-repo` is used through `alpha_entry`.").rejected == ()
    assert _rules(_ground(GOOD, "`sample-repo` is a small service.")) == ["G7"]


def test_an_unbackticked_snake_case_fabrication_rejects():  # G5
    result = _ground(GOOD, "Requests pass through compute_late_fees in `beta.py`.")

    assert [(r.rule, r.token) for r in result.rejected] == [("G5", "compute_late_fees")]


def test_an_unbackticked_real_snake_case_name_is_accepted():  # G5
    result = _ground("Requests start at alpha_entry in `alpha.py`.")

    assert result.rejected == ()


def test_an_unbackticked_fabricated_camelcase_rejects():  # G5
    result = _ground(GOOD, "The LedgerService in `beta.py` records each entry.")

    assert [(r.rule, r.token) for r in result.rejected] == [("G5", "LedgerService")]


def test_a_detected_language_name_is_allowed():  # G5
    result = _ground("The TypeScript client calls `alpha_entry`.")

    assert result.rejected == ()


def test_a_camelcase_word_from_the_evidence_text_is_allowed():  # G5
    """The repository describing its own stack is not the model inventing it."""
    briefed = replace(EVIDENCE.features[0], anchorSummary="Defines the FastAPI application.")
    evidence = replace(EVIDENCE, features=(briefed, EVIDENCE.features[1]))

    assert _ground("The FastAPI app starts in `alpha_entry`.", evidence=evidence).rejected == ()
    assert _rules(_ground("The FastAPI app starts in `alpha_entry`.")) == ["G5"]


def test_prose_slashes_are_not_paths():  # G5
    result = _ground("Input and/or output flows through `beta.py` for read/write access.")

    assert result.rejected == ()


def test_second_person_rejects():  # G6
    result = _ground(GOOD, "You start the program with `alpha_entry`.")

    assert [(r.rule, r.token) for r in result.rejected] == [("G6", "You")]


def test_a_banned_promotional_term_rejects():  # G6
    result = _ground(GOOD, "A robust pipeline in `beta.py` handles it.")

    assert [(r.rule, r.token) for r in result.rejected] == [("G6", "robust")]


def test_a_lead_paragraph_without_a_resolved_name_rejects():  # G7
    result = _ground(GOOD, "Everything else happens later.")

    assert _rules(result) == ["G7"]


def test_a_lead_paragraph_citing_only_a_subsystem_handle_rejects():  # G7, constitution 2.4
    result = _ground(GOOD, "Most of the work happens in [[f1]].")

    assert _rules(result) == ["G7"]


def test_the_lead_is_trimmed_to_four_paragraphs():  # G9
    result = _ground(*([GOOD] * (MAX_LEAD_PARAGRAPHS + 2)))

    assert len(result.lead) == MAX_LEAD_PARAGRAPHS
    assert _rules(result) == ["G9", "G9"]


def test_the_word_budget_trims_from_the_end():  # G9
    long = "The code in `beta.py` " + "keeps working steadily " * 250 + "until it stops."
    result = _ground(GOOD, long, GOOD)

    assert sum(paragraph.wordCount for paragraph in result.lead) < MAX_NARRATIVE_WORDS
    assert [(r.index, r.rule) for r in result.rejected] == [(1, "G9"), (2, "G9")]


def test_a_rejected_opening_paragraph_withholds_the_lead():  # G10, FR-010a
    result = _ground("It begins in `NoSuchModule`.", GOOD, GOOD)

    assert result.lead == ()
    assert result.leadWithheld is True
    assert _rules(result) == ["G4", "G10", "G10"]


def test_a_rejected_later_paragraph_leaves_the_others_in_order():  # FR-010
    second = "Then `Child.run` finishes the job in [[f1]]."
    result = _ground(GOOD, "Then `Nope` does things.", second)

    assert [render_paragraph(p, {}) for p in result.lead][1].startswith("Then `Child.run`")
    assert _rules(result) == ["G4"]


def test_ground_none_equals_all_rejected():
    empty = ground(None, EVIDENCE, LOOKUP, handle_map=HANDLES)
    all_rejected = _ground("`Nope` one.")

    assert empty.lead == all_rejected.lead == ()
    assert empty.subsystems == all_rejected.subsystems == ()


@pytest.mark.parametrize(
    "hostile",
    [
        "# Heading `alpha_entry`",
        "| a | b | `alpha_entry` |",
        "<script>alert(1)</script> `alpha_entry`",
        "[click](http://evil) `alpha_entry`",
        "`alpha_entry` {: .ai-generated }",
        "* item `alpha_entry`",
    ],
)
def test_render_paragraph_neutralises_markdown_and_html_injection(hostile):  # FR-004
    result = _ground(hostile)
    rendered = render_paragraph(result.lead[0], {})

    # Every structural character survives only escaped - "\#", "\|", "\{" -
    # which python-markdown prints as text rather than parsing as syntax.
    assert not rendered.startswith(("#", "|", "*"))
    assert re.search(r"(?<!\\)<", rendered) is None
    assert re.search(r"(?<!\\)\]\(", rendered) is None
    assert re.search(r"(?<!\\)\{:", rendered) is None


def test_render_paragraph_links_handles_to_their_feature_pages():
    result = _ground(GOOD)
    links = {"feat-core": PageLink(fromPageId="home", toPageId="feature-core", label="Core Engine", relativePath="features/core.md")}

    assert render_paragraph(result.lead[0], links) == (
        "The repository enters through `alpha_entry`, which hands work to [Core Engine](features/core.md)\\."
    )


# --------------------------------------------------------------------------
# User Story 2 - one paragraph per major subsystem (FR-025, FR-025a)
# --------------------------------------------------------------------------

CORE = "The engine starts in `alpha_entry`, which lives in `alpha.py`."
IO = "Input and output pass through `beta.py`, where `Child.run` does the work."


def _ground_subsystems(subsystems, *lead, evidence=EVIDENCE, handle_map=HANDLES):
    reply = SimpleNamespace(lead=list(lead), subsystems=dict(subsystems))
    return ground(reply, evidence, LOOKUP, handle_map=handle_map)


def _subsystem_keys(result):
    return [key for key, _ in result.subsystems]


def test_a_subsystem_paragraph_is_accepted_under_its_feature_key():
    result = _ground_subsystems({"f0": CORE})

    assert _subsystem_keys(result) == ["feat-core"]
    assert result.rejected == ()


def test_a_subsystem_paragraph_citing_no_resolved_name_rejects():  # G7, FR-025
    result = _ground_subsystems({"f0": "The engine is where everything important happens in [[f0]].", "f1": IO})

    assert _subsystem_keys(result) == ["feat-io"]
    assert [(r.section, r.rule) for r in result.rejected] == [("subsystem", "G7")]


def test_a_four_sentence_subsystem_paragraph_rejects():  # G8
    four = "It starts in `alpha_entry`. It reads input. It checks it. It stops."
    result = _ground_subsystems({"f0": four, "f1": IO})

    assert _subsystem_keys(result) == ["feat-io"]
    assert [(r.section, r.rule) for r in result.rejected] == [("subsystem", "G8")]


def test_sentence_counting_ignores_dotted_names_and_abbreviations():  # G8
    three = (
        "It starts in `alpha_entry`, e.g. when a request arrives. "
        "Then `Child.run` in `beta.py` handles it, i.e. Work is done there. "
        "It returns vs. Raising an error."
    )
    result = _ground_subsystems({"f0": three})

    assert _subsystem_keys(result) == ["feat-core"]
    assert result.subsystems[0][1].sentenceCount == 3


def test_subsystem_paragraphs_follow_table_order_not_reply_order():  # G11
    result = _ground_subsystems({"f1": IO, "f0": CORE})

    assert _subsystem_keys(result) == ["feat-core", "feat-io"]


def test_a_withheld_subsystem_paragraph_leaves_the_others():  # FR-025a
    result = _ground_subsystems({"f0": "It is priced by `LoanPricingEngine`.", "f1": IO}, GOOD)

    assert _subsystem_keys(result) == ["feat-io"]
    assert len(result.lead) == 1
    assert [(r.section, r.rule) for r in result.rejected] == [("subsystem", "G4")]


def test_a_withheld_lead_leaves_the_subsystem_paragraphs():  # G10 does not reach them
    result = _ground_subsystems({"f0": CORE}, "It begins in `NoSuchModule`.")

    assert result.leadWithheld is True
    assert _subsystem_keys(result) == ["feat-core"]


def test_only_major_features_receive_paragraphs_and_at_most_eight():
    briefs = tuple(_brief(f"f{i}", f"feat-{i}", f"Feature {i}") for i in range(10))
    evidence = replace(
        EVIDENCE,
        features=briefs,
        majorFeatureKeys=tuple(f"feat-{i}" for i in range(10) if i != 3)[:8],
        featureTitles=tuple((brief.featureKey, brief.title) for brief in briefs),
    )
    handles = {brief.handle: brief.featureKey for brief in briefs}

    result = _ground_subsystems({f"f{i}": CORE for i in range(10)}, evidence=evidence, handle_map=handles)

    assert len(result.subsystems) == MAX_SUBSYSTEM_PARAGRAPHS
    assert "feat-3" not in _subsystem_keys(result)
    assert _subsystem_keys(result) == list(evidence.majorFeatureKeys)


def test_an_unknown_subsystem_handle_rejects_its_paragraph():  # G3
    result = _ground_subsystems({"f7": CORE, "f1": IO})

    assert _subsystem_keys(result) == ["feat-io"]
    assert [r.rule for r in result.rejected] == ["G3"]


def test_the_word_budget_trims_subsystem_paragraphs_before_the_lead():  # G9
    long = "It passes through `beta.py` " + "and keeps working " * 190 + "until done."
    result = _ground_subsystems({"f0": CORE, "f1": long}, GOOD)

    assert len(result.lead) == 1
    assert _subsystem_keys(result) == ["feat-core"]
    assert [(r.section, r.rule) for r in result.rejected] == [("subsystem", "G9")]


def test_offered_count_includes_subsystem_paragraphs():
    result = _ground_subsystems({"f0": CORE, "f1": IO}, GOOD)

    assert result.offeredCount == 3
    assert result.paragraphCount == 3


def test_a_paragraph_for_a_subsystem_not_asked_for_is_ignored_not_dropped():
    """The prompt asks for majors only, but models write the rest anyway; on the
    sample repository every notice read "4 of 15 narrative paragraphs dropped"
    for paragraphs nobody asked for (research Decision 19). They are not
    published, and not counted either way."""
    evidence = replace(EVIDENCE, majorFeatureKeys=("feat-core",))

    result = _ground_subsystems({"f0": CORE, "f1": IO}, GOOD, evidence=evidence)

    assert _subsystem_keys(result) == ["feat-core"]
    assert result.rejected == ()
    assert result.offeredCount == 2
    assert result.unaskedCount == 1


def test_a_major_the_reply_wrote_nothing_for_counts_as_unwritten():
    """Measured on the sample repository: asked for eight, the model wrote three,
    and the terminal said nothing (research Decision 19). A paragraph that was
    written and then rejected is dropped, not unwritten."""
    missing = _ground_subsystems({"f0": CORE}, GOOD)
    rejected = _ground_subsystems({"f0": "It is priced by `LoanPricingEngine`."}, GOOD)
    lead_only = _ground(GOOD)

    assert (missing.unwrittenCount, missing.askedCount) == (1, 2)
    assert (rejected.unwrittenCount, rejected.askedCount) == (1, 2)
    assert lead_only.unwrittenCount == 2
    assert ground(None, EVIDENCE, LOOKUP, handle_map=HANDLES).unwrittenCount == 0


def test_an_invented_handle_still_counts_as_dropped():  # G3 is a real defect
    evidence = replace(EVIDENCE, majorFeatureKeys=("feat-core",))

    result = _ground_subsystems({"f0": CORE, "f9": IO}, GOOD, evidence=evidence)

    assert [r.rule for r in result.rejected] == ["G3"]
    assert result.offeredCount == 3
    assert result.unaskedCount == 0


# --------------------------------------------------------------------------
# accept_description - a planned description entering the table (FR-021)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description",
    [
        "Helps you load data from disk.",
        "Stores loans with `LoanStore`.",
        "Wraps the fabricated loan_pricing_engine helper.",
        "A powerful engine for everything.",
        "Links to [[f0]] directly.",
        "   ",
    ],
    ids=["second-person", "fabricated-code", "fabricated-snake", "promotional", "handle", "empty"],
)
def test_accept_description_rejects_second_person_and_fabricated_names(description):
    assert accept_description(description, EVIDENCE, LOOKUP) is None


def test_accept_description_passes_a_plain_sentence_through_escaped():
    accepted = accept_description("Runs the work in `alpha_entry` | and\nreports (results).", EVIDENCE, LOOKUP)

    assert accepted == "Runs the work in `alpha_entry` \\| and reports \\(results\\)\\."
