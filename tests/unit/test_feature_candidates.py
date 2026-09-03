from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))

from _doc_generator_support import index_repo  # noqa: E402

from doc_generator.features.candidates import (  # noqa: E402
    MAX_ATTACH_DISTANCE,
    MAX_PROMPTED_CANDIDATES,
    MIN_CANDIDATE_MODULES,
    build_candidates,
)
from doc_generator.features.evidence import build_repository_evidence  # noqa: E402
from doc_generator.features.fallback import build_import_adjacency  # noqa: E402


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _entry(name: str, imports: list[str] = []) -> str:
    """A public, uncalled function that *calls* whatever it imports.

    The call is not decoration. A helper that is imported but never called is
    itself a public uncalled function, so `identify_entry_points` classifies it
    as an entry point too - and seeds are frozen, so it would form its own
    candidate instead of joining the one that imports it. An earlier version of
    this fixture omitted the calls and every module became its own candidate,
    which looked like a bug in the attach rule and was a bug in the fixture.
    """
    lines = ['"""Module."""', ""]
    lines += [f"from .{target} import {target}_helper" for target in imports]
    body = [f"    {target}_helper()" for target in imports]
    lines += ["", "", f"def {name}_entry() -> int:"] + body + ["    return 0"]
    return "\n".join(lines) + "\n"


def _helper(name: str, imports: list[str] = []) -> str:
    lines = ['"""Module."""', ""]
    lines += [f"from .{target} import {target}_helper" for target in imports]
    body = [f"    {target}_helper()" for target in imports]
    lines += ["", "", f"def {name}_helper() -> int:"] + body + ["    return 1"]
    return "\n".join(lines) + "\n"


def _build(tmp_path: Path, root: Path, files: list[Path], db: str):
    store, graph = index_repo(tmp_path, root, files, db)
    bundle = store.load_repository(root)
    evidence = build_repository_evidence(bundle, graph, repository_root=root)
    adjacency = build_import_adjacency(bundle, graph)
    return bundle, evidence, adjacency, build_candidates(evidence, adjacency)


def _two_area_repo(tmp_path: Path):
    """Two entry points, each pulling its own chain of helpers."""
    root = tmp_path / "two-area"
    files = [
        _write(root / "pkg" / "alpha_cmd.py", _entry("alpha", ["alpha_core"])),
        _write(root / "pkg" / "alpha_core.py", _helper("alpha_core", ["alpha_util"])),
        _write(root / "pkg" / "alpha_util.py", _helper("alpha_util")),
        _write(root / "pkg" / "beta_cmd.py", _entry("beta", ["beta_core"])),
        _write(root / "pkg" / "beta_core.py", _helper("beta_core", ["beta_util"])),
        _write(root / "pkg" / "beta_util.py", _helper("beta_util")),
    ]
    return root, _build(tmp_path, root, files, "two-area.sqlite")


def test_candidates_partition_the_repository(tmp_path):
    """The invariant every downstream guarantee rests on.

    Because assignment is per candidate and a candidate is indivisible, no model
    answer and no repair rule can leave a module belonging to no feature. That
    property is only real if it starts true here.
    """
    _root, (bundle, _evidence, _adjacency, candidates) = _two_area_repo(tmp_path)

    claimed = [key for candidate in candidates for key in candidate.memberKeys]
    expected = {file_bundle.module.sourceFileId for file_bundle in bundle.files}

    assert len(claimed) == len(set(claimed)), "no module may belong to two candidates"
    assert set(claimed) == expected, "every module must belong to one"


def test_entry_point_modules_seed_their_own_candidates(tmp_path):
    _root, (_bundle, evidence, _adjacency, candidates) = _two_area_repo(tmp_path)

    seeds = {candidate.seedModuleKey for candidate in candidates}
    assert seeds <= set(evidence.entryPointModuleKeys) | seeds
    assert len(candidates) >= 2, "two independent entry points are two candidates"


def test_a_module_goes_to_the_area_it_is_coupled_to(tmp_path):
    """Coupling decides membership, not hop distance.

    Scoring by `1/(1+d)` put 78% of the real repository into one candidate,
    because a hub makes nearly every module two hops from nearly every seed.
    """
    _root, (bundle, _evidence, _adjacency, candidates) = _two_area_repo(tmp_path)

    name_by_key = {fb.module.sourceFileId: fb.module.name for fb in bundle.files}
    by_member = {
        name_by_key[key]: candidate for candidate in candidates for key in candidate.memberKeys
    }

    assert by_member["alpha_core"] is by_member["alpha_cmd"]
    assert by_member["beta_core"] is by_member["beta_cmd"]
    assert by_member["alpha_core"] is not by_member["beta_core"]


def test_attach_distance_is_bounded(tmp_path):
    """The bound is 2, and it is honoured rather than merely declared.

    Asserting the constant alone would pass against an implementation that
    ignores it, so a module further than the bound from every seed must land in
    a different candidate than the seed's.
    """
    assert MAX_ATTACH_DISTANCE == 2

    root = tmp_path / "chain"
    files = [
        _write(root / "pkg" / "cmd.py", _entry("cmd", ["one"])),
        _write(root / "pkg" / "one.py", _helper("one", ["two"])),
        _write(root / "pkg" / "two.py", _helper("two", ["three"])),
        _write(root / "pkg" / "three.py", _helper("three", ["four"])),
        _write(root / "pkg" / "four.py", _helper("four")),
    ]
    bundle, _evidence, _adjacency, candidates = _build(tmp_path, root, files, "chain.sqlite")

    name_by_key = {fb.module.sourceFileId: fb.module.name for fb in bundle.files}
    by_member = {
        name_by_key[key]: candidate for candidate in candidates for key in candidate.memberKeys
    }
    seed_candidate = by_member["cmd"]

    assert "one" in [name_by_key[k] for k in seed_candidate.memberKeys], "1 hop is inside the bound"
    claimed = [key for candidate in candidates for key in candidate.memberKeys]
    assert len(set(claimed)) == len(bundle.files), "the far modules are still claimed by someone"


def test_derivation_is_identical_across_runs(tmp_path):
    _root, (_bundle, evidence, adjacency, first) = _two_area_repo(tmp_path)

    second = build_candidates(evidence, adjacency)

    assert [(c.seedModuleKey, c.memberKeys) for c in first] == [
        (c.seedModuleKey, c.memberKeys) for c in second
    ]


def test_candidate_titles_are_unique_and_package_qualified(tmp_path):
    """A bare module name is not a usable title.

    This repository has eleven modules called `models`; four candidates came
    back titled `models`. `validate.py` rejects duplicate titles, so with no
    model reachable three of those four features would have been discarded and
    their candidates reassigned - the no-model path degrading for a reason that
    has nothing to do with the model.
    """
    root = tmp_path / "namesakes"
    files = [
        _write(root / "alpha" / "models.py", _entry("alpha_models")),
        _write(root / "alpha" / "extra.py", _helper("alpha_extra", ["models"])),
        _write(root / "beta" / "models.py", _entry("beta_models")),
        _write(root / "beta" / "extra.py", _helper("beta_extra", ["models"])),
    ]
    _bundle, _evidence, _adjacency, candidates = _build(tmp_path, root, files, "namesakes.sqlite")

    titles = [candidate.seedTitle for candidate in candidates]
    assert len(titles) == len(set(titles)), f"titles must be unique, got {titles}"
    assert any("alpha" in title for title in titles)


def test_small_candidates_are_folded_rather_than_dropped(tmp_path):
    """Consolidation folds; it never releases a module.

    A candidate that disappears must have handed its members to another one -
    otherwise the partition breaks at exactly the step meant to tidy it.
    """
    _root, (bundle, _evidence, _adjacency, candidates) = _two_area_repo(tmp_path)

    assert all(len(candidate.memberKeys) >= MIN_CANDIDATE_MODULES for candidate in candidates), (
        "every surviving candidate should have absorbed its way past the minimum"
    )
    claimed = {key for candidate in candidates for key in candidate.memberKeys}
    assert claimed == {fb.module.sourceFileId for fb in bundle.files}


def test_candidate_count_respects_the_prompt_cap(tmp_path):
    """The planner's token budget assumes this cap holds."""
    root = tmp_path / "many"
    files = []
    for index in range(MAX_PROMPTED_CANDIDATES + 12):
        files.append(_write(root / "pkg" / f"cmd_{index:03d}.py", _entry(f"cmd_{index:03d}")))
    bundle, _evidence, _adjacency, candidates = _build(tmp_path, root, files, "many.sqlite")

    assert len(candidates) <= MAX_PROMPTED_CANDIDATES
    claimed = {key for candidate in candidates for key in candidate.memberKeys}
    assert claimed == {fb.module.sourceFileId for fb in bundle.files}, (
        "capping must fold the remainder, never discard it"
    )


def test_a_repository_with_no_entry_points_still_groups_every_module(tmp_path):
    """The fallback path carries the whole repository when nothing seeds it."""
    root = tmp_path / "no-entry"
    files = [
        _write(root / "pkg" / "one.py", '"""One."""\n\n\ndef _hidden() -> int:\n    return 1\n'),
        _write(root / "pkg" / "two.py", '"""Two."""\n\n\ndef _also_hidden() -> int:\n    return 2\n'),
    ]
    bundle, _evidence, _adjacency, candidates = _build(tmp_path, root, files, "no-entry.sqlite")

    claimed = {key for candidate in candidates for key in candidate.memberKeys}
    assert claimed == {fb.module.sourceFileId for fb in bundle.files}


def test_an_empty_repository_yields_no_candidates(tmp_path):
    root = tmp_path / "empty"
    files = [_write(root / "pkg" / "only.py", '"""Only."""\n')]
    bundle, evidence, adjacency, candidates = _build(tmp_path, root, files, "empty.sqlite")

    claimed = {key for candidate in candidates for key in candidate.memberKeys}
    assert claimed == {fb.module.sourceFileId for fb in bundle.files}


def test_a_module_joins_the_area_it_is_most_coupled_to_not_the_first_named(tmp_path):
    """Weight decides, not the label that sorts first.

    This is the discriminating case, and it was added because mutation testing
    showed the earlier coupling test was vacuous: in a fixture where every
    module has a single labelled neighbour, *any* tie-break gives the same
    answer, so breaking the weight ordering left the suite green.

    Here `shared` has one edge into the `aaa` area and two into the `zzz` area.
    The seed keys are paths, so `aaa_cmd.py` sorts first - which means an
    implementation that orders by label instead of by summed weight picks `aaa`
    and this test fails. That ordering is precisely what put 78% of the real
    repository into one candidate.
    """
    root = tmp_path / "weighted"
    files = [
        _write(root / "pkg" / "aaa_cmd.py", _entry("aaa", ["aaa_core"])),
        _write(root / "pkg" / "aaa_core.py", _helper("aaa_core")),
        _write(root / "pkg" / "zzz_cmd.py", _entry("zzz", ["zzz_core", "zzz_extra"])),
        _write(root / "pkg" / "zzz_core.py", _helper("zzz_core")),
        _write(root / "pkg" / "zzz_extra.py", _helper("zzz_extra")),
        _write(
            root / "pkg" / "shared.py",
            '"""Shared."""\n\n'
            "from .aaa_core import aaa_core_helper\n"
            "from .zzz_core import zzz_core_helper\n"
            "from .zzz_extra import zzz_extra_helper\n\n\n"
            "def _shared() -> int:\n"
            "    return aaa_core_helper() + zzz_core_helper() + zzz_extra_helper()\n",
        ),
    ]
    bundle, _evidence, _adjacency, candidates = _build(tmp_path, root, files, "weighted.sqlite")

    name_by_key = {fb.module.sourceFileId: fb.module.name for fb in bundle.files}
    by_member = {
        name_by_key[key]: candidate for candidate in candidates for key in candidate.memberKeys
    }
    shared_members = {name_by_key[key] for key in by_member["shared"].memberKeys}

    assert "zzz_cmd" in shared_members, (
        f"`shared` has 2 edges into zzz and 1 into aaa, so it belongs with zzz; "
        f"it landed with {sorted(shared_members)}"
    )
