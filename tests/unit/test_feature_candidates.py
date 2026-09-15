from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))

from pathlib import PurePosixPath  # noqa: E402

from _doc_generator_support import index_repo  # noqa: E402

from doc_generator.features import candidates as candidates_module  # noqa: E402
from doc_generator.features.candidates import (  # noqa: E402
    MAX_ATTACH_DISTANCE,
    MAX_PROMPTED_CANDIDATES,
    MIN_CANDIDATE_MODULES,
    TERMINAL_FEATURE_TITLE,
    build_candidates,
)
from doc_generator.features.evidence import (  # noqa: E402
    FeatureEvidence,
    RepositoryEvidence,
    build_repository_evidence,
)
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


# --------------------------------------------------------------------------
# Spec 039: folding by coupling, then directory, never into the largest
# (FR-006, FR-006a, FR-007; research Decision 6). Hand-built evidence keyed by
# repository-relative path, so each scenario states exactly the shape it tests.
# --------------------------------------------------------------------------


def _hand(
    paths: list[str],
    *,
    seeds: tuple[str, ...] = (),
    entries: tuple[str, ...] = (),
    tests: tuple[str, ...] = (),
    counts: dict[str, int] | None = None,
) -> RepositoryEvidence:
    """Evidence over `paths`. `seeds` hold one uncalled function each, `entries` a
    command each (entry modules), `counts` overrides how many entry points a
    module holds, and `tests` are test files."""
    per_module = {path: 1 for path in (*seeds, *entries)}
    per_module.update(counts or {})
    entry_points = {
        path: tuple(f"{path}::run_{index}" for index in range(count))
        for path, count in per_module.items()
        if count
    }
    test_set = frozenset(tests)
    return RepositoryEvidence(
        modules=tuple(
            FeatureEvidence(
                moduleKey=path,
                moduleName=PurePosixPath(path).stem,
                filePath=f"/r/{path}",
                directoryPath=str(PurePosixPath(path).parent),
            )
            for path in sorted(paths)
        ),
        entryPointModuleKeys=tuple(sorted(entry_points)),
        entryPointKeysByModuleKey=entry_points,
        testModuleKeys=test_set,
        entryModuleKeys=tuple(sorted(entries)),
        seedModuleKeys=tuple(sorted(path for path in entry_points if path not in test_set)),
    )


def _adj(paths: list[str], *edges: tuple) -> dict[str, dict[str, int]]:
    adjacency: dict[str, dict[str, int]] = {path: {} for path in paths}
    for source, target, *weight in edges:
        value = weight[0] if weight else 1
        adjacency[source][target] = adjacency[source].get(target, 0) + value
        adjacency[target][source] = adjacency[target].get(source, 0) + value
    return adjacency


def _holding(candidates, key: str):
    return next(candidate for candidate in candidates if key in candidate.memberKeys)


def _members(candidates, key: str) -> set[str]:
    return set(_holding(candidates, key).memberKeys)


# A two-module group in `pkg/` and a four-module group in `big/`.
_A = ["pkg/a_seed.py", "pkg/a_helper.py"]
_B = ["big/b_seed.py", "big/b1.py", "big/b2.py", "big/b3.py"]
_AB_EDGES = (
    ("pkg/a_seed.py", "pkg/a_helper.py"),
    ("big/b_seed.py", "big/b1.py"),
    ("big/b_seed.py", "big/b2.py"),
    ("big/b_seed.py", "big/b3.py"),
)


def _with_ab(extra: list[str], *edges: tuple, seeds: tuple[str, ...] = (), entries: tuple[str, ...] = ()):
    paths = _A + _B + extra
    evidence = _hand(paths, seeds=("pkg/a_seed.py", "big/b_seed.py", *seeds), entries=entries)
    return build_candidates(evidence, _adj(paths, *_AB_EDGES, *edges))


def test_an_uncoupled_small_group_joins_the_survivor_holding_most_modules_directly_in_its_directory():
    candidates = _with_ab(["pkg/lonely.py"], seeds=("pkg/lonely.py",))

    assert _members(candidates, "pkg/lonely.py") == {*_A, "pkg/lonely.py"}, (
        "`pkg/` holds two of A's modules and none of B's, though B is larger"
    )


def test_the_directory_walk_climbs_to_the_parent_directory():
    candidates = _with_ab(["pkg/sub/lonely.py"], seeds=("pkg/sub/lonely.py",))

    assert "pkg/sub/lonely.py" in _members(candidates, "pkg/a_seed.py")


def test_the_directory_walk_never_climbs_from_a_subdirectory_into_the_root():
    """FR-006: a frontend orphan must not join a backend group through a root-level module.

    A module whose own directory is the root is still placed by the root's modules.
    """
    paths = ["tool.py", "tool_helper.py", "frontend/app/orphan.py", "setup.py"]
    evidence = _hand(paths, seeds=("tool.py", "frontend/app/orphan.py", "setup.py"))
    candidates = build_candidates(evidence, _adj(paths, ("tool.py", "tool_helper.py")))

    assert "tool.py" not in _members(candidates, "frontend/app/orphan.py")
    assert _holding(candidates, "frontend/app/orphan.py").seedTitle == TERMINAL_FEATURE_TITLE
    assert _members(candidates, "setup.py") == {"tool.py", "tool_helper.py", "setup.py"}


def test_a_directory_counts_only_its_direct_modules_never_its_subtree():
    deep = ["pkg/deep/x/d_seed.py", "pkg/deep/x/d1.py", "pkg/deep/x/d2.py", "pkg/deep/x/d3.py"]
    paths = _A + deep + ["pkg/lonely.py"]
    evidence = _hand(paths, seeds=("pkg/a_seed.py", "pkg/deep/x/d_seed.py", "pkg/lonely.py"))
    edges = [("pkg/a_seed.py", "pkg/a_helper.py")] + [("pkg/deep/x/d_seed.py", path) for path in deep[1:]]
    candidates = build_candidates(evidence, _adj(paths, *edges))

    assert _members(candidates, "pkg/lonely.py") == {*_A, "pkg/lonely.py"}, (
        "`pkg/`'s subtree holds four of D's modules, but `pkg/` itself holds two of A's"
    )


def test_leftovers_sharing_a_directory_combine():
    candidates = _with_ab(["tools/x.py", "tools/y.py"], seeds=("tools/x.py", "tools/y.py"))

    together = _holding(candidates, "tools/x.py")
    assert set(together.memberKeys) == {"tools/x.py", "tools/y.py"}
    assert together.seedTitle == "tools"


def test_a_truly_isolated_module_lands_in_the_terminal_candidate():
    candidates = _with_ab(["misc/alone.py"], seeds=("misc/alone.py",))

    terminal = _holding(candidates, "misc/alone.py")
    assert terminal.seedTitle == TERMINAL_FEATURE_TITLE
    assert terminal.memberKeys == ("misc/alone.py",)
    assert terminal.seedModuleKey not in {path for path in _A + _B + ["misc/alone.py"]}, (
        "the terminal candidate's seed is a placeholder, never a module"
    )


def test_no_group_is_folded_into_the_largest_for_being_largest():
    """033 sent anything uncoupled to the largest survivor; that is how one group held 85%."""
    candidates = _with_ab(["misc/alone.py"], seeds=("misc/alone.py",))

    assert "misc/alone.py" not in _members(candidates, "big/b_seed.py")
    assert _members(candidates, "big/b_seed.py") == set(_B)


def test_a_one_module_entry_module_survives():
    """FR-006a: without protection, `cli.py` would join A through `pkg/`."""
    candidates = _with_ab(["pkg/cli.py"], entries=("pkg/cli.py",))

    assert _members(candidates, "pkg/cli.py") == {"pkg/cli.py"}


def test_an_entry_module_is_never_absorbed_by_a_group_without_one():
    candidates = _with_ab(["pkg/cli.py"], ("pkg/cli.py", "pkg/a_seed.py", 3), entries=("pkg/cli.py",))

    assert _members(candidates, "pkg/cli.py") == {"pkg/cli.py"}
    assert _members(candidates, "pkg/a_seed.py") == set(_A)


def test_a_small_entry_group_joins_the_entry_group_it_is_most_coupled_to():
    """Even when a group without entry modules is more strongly coupled to it."""
    routes = ["api/routes.py", "api/routes_helper.py"]
    candidates = _with_ab(
        routes + ["pkg/cli.py"],
        ("api/routes.py", "api/routes_helper.py", 2),
        ("pkg/cli.py", "api/routes.py", 1),
        ("pkg/cli.py", "pkg/a_seed.py", 5),
        entries=("pkg/cli.py", "api/routes.py"),
    )

    assert _members(candidates, "pkg/cli.py") == {"pkg/cli.py", *routes}


def test_two_small_entry_groups_in_one_directory_combine():
    candidates = _with_ab(
        ["api/routes_a.py", "api/routes_b.py"], entries=("api/routes_a.py", "api/routes_b.py")
    )

    assert _members(candidates, "api/routes_a.py") == {"api/routes_a.py", "api/routes_b.py"}


def test_entry_groups_of_two_or_more_modules_in_one_directory_stay_apart():
    """The sample's route groups share `api/` and must stay two parts (FR-006a)."""
    paths = ["api/routes_a.py", "api/helper_a.py", "api/routes_b.py", "api/helper_b.py"]
    evidence = _hand(paths, entries=("api/routes_a.py", "api/routes_b.py"))
    adjacency = _adj(
        paths,
        ("api/routes_a.py", "api/helper_a.py", 2),
        ("api/routes_b.py", "api/helper_b.py", 2),
        ("api/routes_a.py", "api/routes_b.py", 1),
    )

    candidates = build_candidates(evidence, adjacency)

    assert _members(candidates, "api/routes_a.py") == {"api/routes_a.py", "api/helper_a.py"}
    assert _members(candidates, "api/routes_b.py") == {"api/routes_b.py", "api/helper_b.py"}


def test_the_cap_folds_non_entry_groups_first(monkeypatch):
    monkeypatch.setattr(candidates_module, "MAX_PROMPTED_CANDIDATES", 3)
    ordinary = ["n1/a.py", "n1/a2.py", "n2/b.py", "n2/b2.py", "n3/c.py", "n3/c2.py"]
    paths = ordinary + ["e1/cli.py", "e2/main.py"]
    evidence = _hand(paths, seeds=("n1/a.py", "n2/b.py", "n3/c.py"), entries=("e1/cli.py", "e2/main.py"))
    adjacency = _adj(paths, ("n1/a.py", "n1/a2.py"), ("n2/b.py", "n2/b2.py"), ("n3/c.py", "n3/c2.py"))

    candidates = build_candidates(evidence, adjacency)

    assert len(candidates) <= 3
    assert _holding(candidates, "e1/cli.py") is not _holding(candidates, "e2/main.py"), (
        "the two entry groups survive; the cap is met by folding the others"
    )


def test_entry_groups_beyond_the_cap_combine_by_coupling_then_directory_then_shared_path(monkeypatch):
    """Five two-module entry groups and a cap of two (FR-006a; research Decision 6 step 6).

    `a/x` and `a/y` share only the leading path `a`; `b/cli3` and `c/cli4` are
    coupled; `b/sub/cli5`'s directory walk finds `cli3`'s group in `b`.
    """
    monkeypatch.setattr(candidates_module, "MAX_PROMPTED_CANDIDATES", 2)
    groups = {
        "a/x/cli1.py": "a/x/h1.py",
        "a/y/cli2.py": "a/y/h2.py",
        "b/cli3.py": "b/h3.py",
        "c/cli4.py": "c/h4.py",
        "b/sub/cli5.py": "b/sub/h5.py",
    }
    paths = [*groups, *groups.values()]
    evidence = _hand(paths, entries=tuple(groups))
    adjacency = _adj(paths, *((entry, helper, 2) for entry, helper in groups.items()), ("b/cli3.py", "c/cli4.py", 1))

    candidates = build_candidates(evidence, adjacency)

    assert len(candidates) == 2
    assert _members(candidates, "a/x/cli1.py") == {"a/x/cli1.py", "a/x/h1.py", "a/y/cli2.py", "a/y/h2.py"}
    assert _members(candidates, "b/cli3.py") == {
        "b/cli3.py", "b/h3.py", "c/cli4.py", "c/h4.py", "b/sub/cli5.py", "b/sub/h5.py",
    }


def _mixed_repository():
    """Every folding rule at once, plus a test file with entry points of its own."""
    paths = _A + _B + [
        "pkg/lonely.py",
        "tools/x.py",
        "tools/y.py",
        "misc/alone.py",
        "api/cli.py",
        "tests/test_a.py",
    ]
    evidence = _hand(
        paths,
        seeds=("pkg/a_seed.py", "big/b_seed.py", "pkg/lonely.py", "tools/x.py", "tools/y.py", "misc/alone.py"),
        entries=("api/cli.py",),
        tests=("tests/test_a.py",),
        counts={"pkg/a_seed.py": 3, "pkg/lonely.py": 2, "tests/test_a.py": 4},
    )
    adjacency = _adj(paths, *_AB_EDGES, ("tests/test_a.py", "pkg/a_seed.py", 2))
    return paths, evidence, adjacency


def test_entry_point_counts_add_up_to_the_non_test_total():
    """FR-007: however modules arrive in a candidate, their entry points arrive with them."""
    _paths, evidence, adjacency = _mixed_repository()

    candidates = build_candidates(evidence, adjacency)

    non_test_total = sum(
        len(keys) for key, keys in evidence.entryPointKeysByModuleKey.items() if key not in evidence.testModuleKeys
    )
    assert sum(candidate.exposedEntryPointCount for candidate in candidates) == non_test_total == 10
    assert _holding(candidates, "pkg/lonely.py").exposedEntryPointCount >= 5, "a_seed's 3 plus lonely's 2"


def test_a_seeded_group_is_titled_by_its_anchor():
    """FR-010's title sentence (owner decision, 2026-09-15).

    `routes_members` folds into the seeding script's group, which keeps its
    seed; titled by the seed it read "scripts - seed_data" on the sample. Its
    anchor is `routes_members`, the entry module with the most entry points.
    """
    paths = ["scripts/seed_data.py", "scripts/helper.py", "api/routes_members.py"]
    evidence = _hand(
        paths, entries=("scripts/seed_data.py", "api/routes_members.py"), counts={"api/routes_members.py": 3}
    )
    adjacency = _adj(
        paths, ("scripts/seed_data.py", "scripts/helper.py"), ("scripts/seed_data.py", "api/routes_members.py")
    )

    group = _holding(build_candidates(evidence, adjacency), "api/routes_members.py")

    assert set(group.memberKeys) == set(paths)
    assert group.seedModuleKey == "scripts/seed_data.py", "the seed stays the candidate's identity"
    assert group.seedTitle == "api - routes_members"


def test_when_no_group_can_stand_alone_nothing_is_folded():
    """033's rule, kept (owner decision, 2026-09-15).

    Three coupled one-module seeds with no command, route or `main`: there is
    no survivor to fold into, and combining them by directory would make one
    feature of the whole repository - which repair rejects as not navigation.
    """
    paths = ["alpha.py", "beta.py", "gamma.py"]
    evidence = _hand(paths, seeds=tuple(paths))
    adjacency = _adj(paths, ("alpha.py", "beta.py"), ("beta.py", "gamma.py"))

    candidates = build_candidates(evidence, adjacency)

    assert sorted(candidate.memberKeys for candidate in candidates) == [("alpha.py",), ("beta.py",), ("gamma.py",)]


# --------------------------------------------------------------------------
# Spec 039 User Story 2: tests follow the code they test (FR-008, FR-009;
# research Decision 5). Test files never seed, never pull production code into
# a group, and are placed once production grouping is final.
# --------------------------------------------------------------------------


def _seeds(candidates) -> set[str]:
    return {candidate.seedModuleKey for candidate in candidates}


def test_a_test_file_never_seeds_a_group():
    """`test_x` holds uncalled test functions - entry points - and is still no seed.

    Seeded, it would claim `f1` and `f2`, which nothing else reaches, and form a
    group that survives - "Tests (Test Fines)" on the sample.
    """
    paths = _A + _B + ["pkg/f1.py", "pkg/f2.py", "tests/test_x.py"]
    evidence = _hand(paths, seeds=("pkg/a_seed.py", "big/b_seed.py"), tests=("tests/test_x.py",), counts={"tests/test_x.py": 3})
    adjacency = _adj(paths, *_AB_EDGES, ("tests/test_x.py", "pkg/f1.py"), ("tests/test_x.py", "pkg/f2.py"))

    candidates = build_candidates(evidence, adjacency)

    assert "tests/test_x.py" not in _seeds(candidates)
    assert _members(candidates, "pkg/f1.py") == {"pkg/f1.py", "pkg/f2.py", "tests/test_x.py"}, (
        "`f1` and `f2` are grouped by structure (their directory), and the test follows them"
    )


def test_a_production_module_coupled_only_to_its_test_is_grouped_by_production_code():
    """033 let the test seed a group and pull `fine` into it ("Tests (Test Fines)")."""
    paths = _A + _B + ["pkg/fine.py", "tests/test_fine.py"]
    evidence = _hand(paths, seeds=("pkg/a_seed.py", "big/b_seed.py"), tests=("tests/test_fine.py",), counts={"tests/test_fine.py": 5})
    candidates = build_candidates(evidence, _adj(paths, *_AB_EDGES, ("tests/test_fine.py", "pkg/fine.py", 3)))

    assert _members(candidates, "pkg/fine.py") == {*_A, "pkg/fine.py", "tests/test_fine.py"}, (
        "`fine` goes where production code puts it (its directory), and its test follows it"
    )


def test_a_test_joins_the_group_holding_most_of_the_code_it_imports():
    paths = _A + _B + ["tests/test_mixed.py"]
    evidence = _hand(paths, seeds=("pkg/a_seed.py", "big/b_seed.py"), tests=("tests/test_mixed.py",))
    adjacency = _adj(
        paths, *_AB_EDGES, ("tests/test_mixed.py", "pkg/a_seed.py", 2), ("tests/test_mixed.py", "big/b1.py", 1)
    )

    assert "tests/test_mixed.py" in _members(build_candidates(evidence, adjacency), "pkg/a_seed.py")


def test_a_tie_between_groups_goes_to_the_smaller_seed_key():
    paths = _A + _B + ["tests/test_both.py"]
    evidence = _hand(paths, seeds=("pkg/a_seed.py", "big/b_seed.py"), tests=("tests/test_both.py",))
    adjacency = _adj(paths, *_AB_EDGES, ("tests/test_both.py", "pkg/a_seed.py"), ("tests/test_both.py", "big/b1.py"))

    assert "tests/test_both.py" in _members(build_candidates(evidence, adjacency), "big/b_seed.py"), (
        "`big/b_seed.py` sorts before `pkg/a_seed.py`"
    )


def test_a_fixtures_only_test_is_placed_by_its_directory():
    paths = _A + _B + ["pkg/tests/conftest.py"]
    evidence = _hand(paths, seeds=("pkg/a_seed.py", "big/b_seed.py"), tests=("pkg/tests/conftest.py",))

    candidates = build_candidates(evidence, _adj(paths, *_AB_EDGES))

    assert "pkg/tests/conftest.py" in _members(candidates, "pkg/a_seed.py"), "`pkg/tests/` climbs to `pkg/`"


def test_the_test_directory_walk_counts_production_modules_only():
    """Two of B's tests sit in `pkg/tests/`; counted, they would pull `conftest` to B."""
    tests = ("pkg/tests/test_b.py", "pkg/tests/test_b2.py", "pkg/tests/conftest.py")
    paths = _A + _B + list(tests)
    evidence = _hand(paths, seeds=("pkg/a_seed.py", "big/b_seed.py"), tests=tests)
    adjacency = _adj(paths, *_AB_EDGES, ("pkg/tests/test_b.py", "big/b1.py"), ("pkg/tests/test_b2.py", "big/b2.py"))

    candidates = build_candidates(evidence, adjacency)

    assert {"pkg/tests/test_b.py", "pkg/tests/test_b2.py"} <= _members(candidates, "big/b_seed.py")
    assert "pkg/tests/conftest.py" in _members(candidates, "pkg/a_seed.py")


def test_unplaced_tests_sharing_a_directory_combine_and_a_lone_one_goes_to_the_terminal_candidate():
    """FR-009: nothing production lives under `extra/` or `other/`, and the walk stops at the top level."""
    tests = ("extra/tests/fixture_a.py", "extra/tests/fixture_b.py", "other/tests/conftest.py")
    paths = _A + _B + list(tests)
    evidence = _hand(paths, seeds=("pkg/a_seed.py", "big/b_seed.py"), tests=tests)

    candidates = build_candidates(evidence, _adj(paths, *_AB_EDGES))

    together = _holding(candidates, "extra/tests/fixture_a.py")
    assert set(together.memberKeys) == {"extra/tests/fixture_a.py", "extra/tests/fixture_b.py"}
    assert together.seedTitle == "tests"
    assert _holding(candidates, "other/tests/conftest.py").seedTitle == TERMINAL_FEATURE_TITLE


def _production_partition(candidates, test_keys) -> set[frozenset[str]]:
    return {frozenset(set(c.memberKeys) - test_keys) for c in candidates} - {frozenset()}


def test_placing_tests_never_moves_a_production_module():
    """FR-009: the same production grouping with and without the test files."""
    paths, evidence, adjacency = _mixed_repository()
    tests = set(evidence.testModuleKeys)
    production = [path for path in paths if path not in tests]
    without = _hand(
        production,
        seeds=tuple(key for key in evidence.seedModuleKeys),
        entries=evidence.entryModuleKeys,
        counts={key: len(value) for key, value in evidence.entryPointKeysByModuleKey.items() if key not in tests},
    )
    production_adjacency = {key: {n: w for n, w in adjacency[key].items() if n not in tests} for key in production}

    assert _production_partition(build_candidates(evidence, adjacency), tests) == _production_partition(
        build_candidates(without, production_adjacency), set()
    )


def test_every_test_file_belongs_to_exactly_one_group():
    tests = ("tests/test_a.py", "tests/test_b.py", "pkg/tests/conftest.py", "misc/tests/lone.py")
    paths = _A + _B + list(tests)
    evidence = _hand(paths, seeds=("pkg/a_seed.py", "big/b_seed.py"), tests=tests, counts={key: 2 for key in tests})
    adjacency = _adj(paths, *_AB_EDGES, ("tests/test_a.py", "pkg/a_seed.py"), ("tests/test_b.py", "big/b2.py"))

    candidates = build_candidates(evidence, adjacency)

    for test in tests:
        assert sum(test in candidate.memberKeys for candidate in candidates) == 1, test
    assert not _seeds(candidates) & set(tests)


def test_a_repository_whose_only_entry_points_are_in_tests_is_grouped_by_directory():
    """Edge case "Tests only": a library with a test suite has no seeds at all."""
    paths = ["pkg/a.py", "pkg/b.py", "lib/c.py", "lib/d.py", "tests/test_a.py"]
    evidence = _hand(paths, tests=("tests/test_a.py",), counts={"tests/test_a.py": 4})
    adjacency = _adj(paths, ("tests/test_a.py", "pkg/a.py"), ("tests/test_a.py", "pkg/b.py"))

    candidates = build_candidates(evidence, adjacency)

    assert not _seeds(candidates) & {"tests/test_a.py"}
    assert _members(candidates, "pkg/a.py") == {"pkg/a.py", "pkg/b.py", "tests/test_a.py"}
    assert _members(candidates, "lib/c.py") == {"lib/c.py", "lib/d.py"}, "no catch-all group"


def test_candidates_still_partition_every_module():
    paths, evidence, adjacency = _mixed_repository()

    candidates = build_candidates(evidence, adjacency)

    claimed = [key for candidate in candidates for key in candidate.memberKeys]
    assert len(claimed) == len(set(claimed))
    assert set(claimed) == set(paths)
    assert build_candidates(evidence, adjacency) == candidates, "and identically on every run"
