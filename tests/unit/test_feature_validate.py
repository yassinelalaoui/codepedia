"""One test per row of the repair table, on hand-written input.

No model is involved anywhere in this file - `validate` takes no engine, so
there is nothing to stub and nothing that could quietly depend on one.
"""

from __future__ import annotations

from doc_generator.features.candidates import Candidate
from doc_generator.features.evidence import FeatureEvidence, RepositoryEvidence
from doc_generator.features.validate import (
    DEFAULT_FEATURE_KIND,
    MAX_TITLE_CHARACTERS,
    TERMINAL_FEATURE_TITLE,
    FeaturePlan,
    PlannedFeature,
    feature_sort_key,
    repair,
)


def _evidence(*names: str) -> RepositoryEvidence:
    return RepositoryEvidence(
        modules=tuple(
            FeatureEvidence(
                moduleKey=f"key::{name}",
                moduleName=name,
                filePath=f"/r/{name}.py",
                directoryPath=".",
            )
            for name in names
        )
    )


def _candidate(seed: str, *members: str) -> Candidate:
    return Candidate(
        seedModuleKey=f"key::{seed}",
        seedTitle=f"Area {seed}",
        memberKeys=tuple(f"key::{member}" for member in (members or (seed,))),
    )


def _adjacency(*names: str) -> dict[str, dict[str, int]]:
    return {f"key::{name}": {} for name in names}


def _repair(plan, candidates, names):
    return repair(plan, candidates, evidence=_evidence(*names), adjacency=_adjacency(*names))


def _all_module_keys(features) -> set[str]:
    return {key for feature in features for key in feature.moduleKeys}


# --------------------------------------------------------------------------
# The post-condition that proves the design held
# --------------------------------------------------------------------------


def test_repair_preserves_the_partition(tmp_path):
    """Every module in every candidate survives into exactly one feature.

    Because assignment is per candidate and candidates partition the repository,
    a module cannot be orphaned mid-feature - that failure mode is designed out
    rather than repaired. This is the assertion that proves it.
    """
    candidates = [_candidate("a", "a", "a2"), _candidate("b", "b"), _candidate("c", "c")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(title="First", kind="capability", memberCandidateIds=("c0", "c1")),
            PlannedFeature(title="Second", kind="subsystem", memberCandidateIds=("c2",)),
        )
    )

    features = _repair(plan, candidates, ("a", "a2", "b", "c"))

    expected = {key for candidate in candidates for key in candidate.memberKeys}
    assert _all_module_keys(features) == expected
    claimed = [key for feature in features for key in feature.moduleKeys]
    assert len(claimed) == len(set(claimed)), "no module may appear in two features"


# --------------------------------------------------------------------------
# The repair table, row by row
# --------------------------------------------------------------------------


def test_an_unknown_handle_is_ignored(tmp_path):
    candidates = [_candidate("a"), _candidate("b")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(title="First", kind="capability", memberCandidateIds=("c0", "c99")),
            PlannedFeature(title="Second", kind="subsystem", memberCandidateIds=("c1",)),
        )
    )

    features = _repair(plan, candidates, ("a", "b"))

    assert _all_module_keys(features) == {"key::a", "key::b"}
    assert {f.title for f in features} == {"First", "Second"}


def test_a_candidate_named_by_no_feature_becomes_its_own(tmp_path):
    candidates = [_candidate("a"), _candidate("b"), _candidate("c")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(title="First", kind="capability", memberCandidateIds=("c0",)),
            PlannedFeature(title="Second", kind="subsystem", memberCandidateIds=("c1",)),
        )
    )

    features = _repair(plan, candidates, ("a", "b", "c"))

    orphan = next(f for f in features if "key::c" in f.moduleKeys)
    assert orphan.title == "Area c", "it keeps its deterministic seed title"
    assert orphan.isPlanned is False, "and is not marked as model-written"


def test_a_candidate_named_twice_is_kept_in_the_first_feature_only(tmp_path):
    """Three candidates, not two, and deliberately.

    With only two, dropping the emptied second feature leaves a single feature -
    which correctly trips the "fewer than two features" rule and discards the
    whole plan, hiding the behaviour under test. A third candidate keeps two
    features standing so the duplicate-handle rule is what is being observed.
    """
    candidates = [_candidate("a"), _candidate("b"), _candidate("c")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(title="First", kind="capability", memberCandidateIds=("c0", "c1")),
            PlannedFeature(title="Second", kind="subsystem", memberCandidateIds=("c1",)),
            PlannedFeature(title="Third", kind="subsystem", memberCandidateIds=("c2",)),
        )
    )

    features = _repair(plan, candidates, ("a", "b", "c"))

    first = next(f for f in features if f.title == "First")
    assert set(first.moduleKeys) == {"key::a", "key::b"}
    assert not any(f.title == "Second" for f in features), "empty after repair, so dropped"
    assert _all_module_keys(features) == {"key::a", "key::b", "key::c"}


def test_a_feature_left_empty_after_repair_is_dropped(tmp_path):
    candidates = [_candidate("a"), _candidate("b")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(title="Real", kind="capability", memberCandidateIds=("c0", "c1")),
            PlannedFeature(title="Ghost", kind="capability", memberCandidateIds=("c404",)),
        )
    )

    features = _repair(plan, candidates, ("a", "b"))

    assert not any(f.title == "Ghost" for f in features)


def test_an_empty_title_is_rejected_and_its_candidates_reassigned(tmp_path):
    candidates = [_candidate("a"), _candidate("b"), _candidate("c")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(title="   ", kind="capability", memberCandidateIds=("c0",)),
            PlannedFeature(title="Good", kind="capability", memberCandidateIds=("c1",)),
            PlannedFeature(title="Also Good", kind="subsystem", memberCandidateIds=("c2",)),
        )
    )

    features = _repair(plan, candidates, ("a", "b", "c"))

    assert _all_module_keys(features) == {"key::a", "key::b", "key::c"}
    reassigned = next(f for f in features if "key::a" in f.moduleKeys)
    assert reassigned.title == "Area a"


def test_an_over_long_title_is_rejected(tmp_path):
    candidates = [_candidate("a"), _candidate("b")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(
                title="x" * (MAX_TITLE_CHARACTERS + 1),
                kind="capability",
                memberCandidateIds=("c0",),
            ),
            PlannedFeature(title="Fine", kind="capability", memberCandidateIds=("c1",)),
        )
    )

    features = _repair(plan, candidates, ("a", "b"))

    assert all(len(f.title) <= MAX_TITLE_CHARACTERS for f in features)
    assert _all_module_keys(features) == {"key::a", "key::b"}


def test_a_duplicate_title_is_rejected(tmp_path):
    candidates = [_candidate("a"), _candidate("b"), _candidate("c")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(title="Same Name", kind="capability", memberCandidateIds=("c0",)),
            PlannedFeature(title="same name", kind="capability", memberCandidateIds=("c1",)),
            PlannedFeature(title="Other", kind="subsystem", memberCandidateIds=("c2",)),
        )
    )

    features = _repair(plan, candidates, ("a", "b", "c"))

    titles = [f.title.casefold() for f in features]
    assert len(titles) == len(set(titles)), "a duplicate title would collide in the sidebar"
    assert _all_module_keys(features) == {"key::a", "key::b", "key::c"}


def test_an_unrecognised_kind_is_defaulted_not_rejected(tmp_path):
    """Kind only affects ordering.

    Discarding a good title and description over a misspelled enum would be a
    worse outcome for the reader than one misplaced sidebar entry.
    """
    candidates = [_candidate("a"), _candidate("b")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(title="Kept", kind="MISCELLANEOUS", memberCandidateIds=("c0",)),
            PlannedFeature(title="Other", kind="capability", memberCandidateIds=("c1",)),
        )
    )

    features = _repair(plan, candidates, ("a", "b"))

    kept = next(f for f in features if f.title == "Kept")
    assert kept.kind == DEFAULT_FEATURE_KIND
    assert kept.isPlanned is True, "the feature survives, only its kind was replaced"


def test_a_kind_is_accepted_case_insensitively(tmp_path):
    candidates = [_candidate("a"), _candidate("b")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(title="Kept", kind="  Overview ", memberCandidateIds=("c0",)),
            PlannedFeature(title="Other", kind="capability", memberCandidateIds=("c1",)),
        )
    )

    features = _repair(plan, candidates, ("a", "b"))

    assert next(f for f in features if f.title == "Kept").kind == "overview"


def test_unplaced_candidates_with_unusable_titles_land_in_the_terminal_feature(tmp_path):
    """Constructed explicitly, not left to emerge from the uncovered rule."""
    candidates = [
        _candidate("a"),
        Candidate(seedModuleKey="key::b", seedTitle="   ", memberKeys=("key::b",)),
        Candidate(seedModuleKey="key::c", seedTitle="", memberKeys=("key::c",)),
    ]
    plan = FeaturePlan(
        features=(PlannedFeature(title="Real", kind="capability", memberCandidateIds=("c0",)),)
    )

    features = _repair(plan, candidates, ("a", "b", "c"))

    terminal = next(f for f in features if f.title == TERMINAL_FEATURE_TITLE)
    assert set(terminal.moduleKeys) == {"key::b", "key::c"}
    assert terminal.kind == "tooling"
    assert _all_module_keys(features) == {"key::a", "key::b", "key::c"}


def test_fewer_than_two_features_discards_the_whole_plan(tmp_path):
    """One feature holding everything is not navigation."""
    candidates = [_candidate("a"), _candidate("b"), _candidate("c")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(
                title="Everything", kind="overview", memberCandidateIds=("c0", "c1", "c2")
            ),
        )
    )

    features = _repair(plan, candidates, ("a", "b", "c"))

    assert len(features) == 3, "fell back to one feature per candidate"
    assert all(f.isPlanned is False for f in features)
    assert {f.title for f in features} == {"Area a", "Area b", "Area c"}


# --------------------------------------------------------------------------
# No plan at all - the path that must be identical to a failed call
# --------------------------------------------------------------------------


def test_no_plan_yields_one_feature_per_candidate(tmp_path):
    candidates = [_candidate("a"), _candidate("b")]

    features = _repair(None, candidates, ("a", "b"))

    assert {f.title for f in features} == {"Area a", "Area b"}
    assert all(f.isPlanned is False for f in features)
    assert _all_module_keys(features) == {"key::a", "key::b"}


def test_no_candidates_yields_no_features(tmp_path):
    assert _repair(None, [], ()) == ()


# --------------------------------------------------------------------------
# Identity and ordering
# --------------------------------------------------------------------------


def test_a_feature_is_keyed_by_its_anchor_module(tmp_path):
    candidates = [_candidate("a", "a", "a2"), _candidate("b")]

    features = _repair(None, candidates, ("a", "a2", "b"))

    for feature in features:
        assert feature.key in feature.moduleKeys, "the anchor must be one of the members"
        assert feature.anchorModuleKey == feature.key


def test_no_two_features_share_a_key(tmp_path):
    """A key is a page address; two features sharing one would overwrite."""
    candidates = [_candidate("a"), _candidate("b"), _candidate("c")]

    features = _repair(None, candidates, ("a", "b", "c"))

    keys = [f.key for f in features]
    assert len(keys) == len(set(keys))


def test_features_are_ordered_general_to_specific(tmp_path):
    candidates = [_candidate("a"), _candidate("b"), _candidate("c"), _candidate("d")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(title="Tools", kind="tooling", memberCandidateIds=("c0",)),
            PlannedFeature(title="Whole", kind="overview", memberCandidateIds=("c1",)),
            PlannedFeature(title="Inner", kind="subsystem", memberCandidateIds=("c2",)),
            PlannedFeature(title="Offers", kind="capability", memberCandidateIds=("c3",)),
        )
    )

    features = _repair(plan, candidates, ("a", "b", "c", "d"))

    assert [f.kind for f in features] == ["overview", "capability", "subsystem", "tooling"]


def test_ordering_is_stable_across_runs(tmp_path):
    candidates = [_candidate("a"), _candidate("b"), _candidate("c")]

    first = _repair(None, candidates, ("a", "b", "c"))
    second = _repair(None, candidates, ("a", "b", "c"))

    assert [f.key for f in first] == [f.key for f in second]
    assert [feature_sort_key(f) for f in first] == [feature_sort_key(f) for f in second]


def test_a_planned_feature_is_marked_and_a_fallback_one_is_not(tmp_path):
    """Gates the AI-generated marker - constitution 2.4."""
    candidates = [_candidate("a"), _candidate("b"), _candidate("c")]
    plan = FeaturePlan(
        features=(
            PlannedFeature(title="Named", kind="capability", memberCandidateIds=("c0",)),
            PlannedFeature(title="Also Named", kind="capability", memberCandidateIds=("c1",)),
        )
    )

    features = _repair(plan, candidates, ("a", "b", "c"))

    assert next(f for f in features if f.title == "Named").isPlanned is True
    assert next(f for f in features if f.title == "Area c").isPlanned is False
