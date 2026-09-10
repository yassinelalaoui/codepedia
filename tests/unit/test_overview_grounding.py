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
