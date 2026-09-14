"""`overview.evidence`: the bounded, ordered facts the narrative may use.

No model anywhere in this file - the module refuses one by signature
(`test_overview_package.py`). Caps are asserted from the constants, so raising
one cannot silently widen the prompt the narrator's budget test bounds.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))

from _doc_generator_support import build_indexed_repo, index_repo  # noqa: E402

from doc_generator.features.candidates import build_candidates  # noqa: E402
from doc_generator.features.evidence import build_repository_evidence  # noqa: E402
from doc_generator.features.fallback import build_import_adjacency  # noqa: E402
from doc_generator.features.validate import Feature, FeatureMember, repair  # noqa: E402
from doc_generator.overview.evidence import (  # noqa: E402
    MAX_ANCHOR_SUMMARY_CHARS,
    MAX_MEMBER_NAMES,
    MAX_PROMPTED_ENTRY_FLOWS,
    MAX_PROMPTED_FEATURES,
    MAX_README_LEAD_CHARS,
    MAX_REACHED_FEATURES,
    MAX_SUBSYSTEM_PARAGRAPHS,
    build_overview_evidence,
    is_test_path,
    read_readme_lead,
)


def _feature(index: int, root: Path, *, kind: str = "capability", members: int = 2, docstring: str = "", summary: str = "") -> Feature:
    member_list = tuple(
        FeatureMember(
            moduleKey=f"key-{index}-{m}",
            name=f"mod_{index}_{m}",
            filePath=str(root / f"pkg{index}" / f"mod_{index}_{m}.py"),
            docstring=docstring if m == 0 else "",
            generatedSummary=summary if m == 0 else "",
        )
        for m in range(members)
    )
    return Feature(
        key=f"key-{index}-0",
        title=f"Feature {index}",
        description=f"Does thing {index}.",
        kind=kind,  # type: ignore[arg-type]
        members=member_list,
        exposedEntryPointCount=index,
    )


def _synthetic(tmp_path, features):
    root, store, graph = build_indexed_repo(tmp_path)
    bundle = store.load_repository(root)
    return build_overview_evidence(features, bundle, graph, repository_root=root), root


def _real(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    bundle = store.load_repository(root)
    repository_evidence = build_repository_evidence(bundle, graph, repository_root=root)
    adjacency = build_import_adjacency(bundle, graph)
    features = repair(None, build_candidates(repository_evidence, adjacency), evidence=repository_evidence, adjacency=adjacency)
    return root, bundle, graph, repository_evidence, features


def test_features_follow_navigation_order_and_cap_at_max_prompted_features(tmp_path):
    root = tmp_path / "sample-repo"
    features = [_feature(i, root) for i in range(MAX_PROMPTED_FEATURES + 3)]
    evidence, _ = _synthetic(tmp_path, features)

    assert [brief.featureKey for brief in evidence.features] == [f.key for f in features[:MAX_PROMPTED_FEATURES]]


def test_omitted_feature_count_counts_the_rest(tmp_path):
    root = tmp_path / "sample-repo"
    evidence, _ = _synthetic(tmp_path, [_feature(i, root) for i in range(MAX_PROMPTED_FEATURES + 3)])

    assert evidence.omittedFeatureCount == 3
    assert len(evidence.featureTitles) == MAX_PROMPTED_FEATURES + 3


def test_handles_are_f0_to_fn_in_navigation_order(tmp_path):
    root = tmp_path / "sample-repo"
    evidence, _ = _synthetic(tmp_path, [_feature(i, root) for i in range(4)])

    assert [brief.handle for brief in evidence.features] == ["f0", "f1", "f2", "f3"]
    assert evidence.handle_map() == {f"f{i}": f"key-{i}-0" for i in range(4)}


def test_major_feature_keys_skip_tooling_and_cap_at_eight(tmp_path):
    root = tmp_path / "sample-repo"
    features = [_feature(i, root, kind="tooling" if i % 3 == 0 else "capability") for i in range(MAX_PROMPTED_FEATURES)]
    evidence, _ = _synthetic(tmp_path, features)

    assert len(evidence.majorFeatureKeys) <= MAX_SUBSYSTEM_PARAGRAPHS
    assert all(not key.startswith(("key-0-", "key-3-", "key-6-", "key-9-")) for key in evidence.majorFeatureKeys)
    assert list(evidence.majorFeatureKeys) == [f.key for f in features if f.kind != "tooling"][:MAX_SUBSYSTEM_PARAGRAPHS]


def test_anchor_summary_prefers_docstring_then_generated_summary_first_sentence_capped_at_120(tmp_path):
    root = tmp_path / "sample-repo"
    long_sentence = "Word " * 60 + "end."
    features = [
        _feature(0, root, docstring="Docstring first. Second.", summary="Summary."),
        _feature(1, root, summary="Only a summary. More."),
        _feature(2, root, docstring=long_sentence),
        _feature(3, root),
    ]
    evidence, _ = _synthetic(tmp_path, features)
    summaries = [brief.anchorSummary for brief in evidence.features]

    assert summaries[0] == "Docstring first."
    assert summaries[1] == "Only a summary."
    assert len(summaries[2]) <= MAX_ANCHOR_SUMMARY_CHARS
    assert summaries[3] == ""


def test_member_names_exclude_the_anchor_and_cap_at_three(tmp_path):
    root = tmp_path / "sample-repo"
    evidence, _ = _synthetic(tmp_path, [_feature(0, root, members=6)])
    brief = evidence.features[0]

    assert len(brief.memberNames) == MAX_MEMBER_NAMES
    assert all("mod_0_0" not in name for name in brief.memberNames)
    assert brief.anchorPath == "pkg0/mod_0_0.py"


def test_entry_flows_rank_by_modules_reached_then_stable_key_and_cap_at_six(tmp_path):
    root, bundle, graph, repository_evidence, features = _real(tmp_path)
    evidence = build_overview_evidence(features, bundle, graph, repository_root=root)

    assert 0 < len(evidence.entryFlows) <= MAX_PROMPTED_ENTRY_FLOWS
    # `alpha_entry` calls into beta, so it reaches more modules than any
    # uncalled leaf and must lead the list.
    assert evidence.entryFlows[0].qualifiedName == "alpha_entry"
    assert evidence.entryFlows[0].modulePath == "alpha.py"


def _entry_kinds_repo(tmp_path):
    """A command, a `main`, an uncalled function reaching more than either, and a test.

    Ranked by reach alone, `busy` and the test would lead - the shape that let a
    Spring service implementation pass for the entry point (research Decision 15).
    """
    root = tmp_path / "kinds-repo"
    (root / "tests").mkdir(parents=True)
    sources = {
        "leaf_a.py": "def work_a():\n    return 1\n",
        "leaf_b.py": "def work_b():\n    return 2\n",
        "cli.py": "from leaf_a import work_a\n\n\n@app.command()\ndef run():\n    return work_a()\n",
        "launcher.py": "def main():\n    return 0\n",
        "busy.py": "from leaf_a import work_a\nfrom leaf_b import work_b\n\n\ndef busy():\n    return work_a() + work_b()\n",
        "tests/test_leaves.py": (
            "from leaf_a import work_a\nfrom leaf_b import work_b\n\n\n"
            "def test_leaves():\n    assert work_a() + work_b() == 3\n"
        ),
    }
    for name, text in sources.items():
        (root / name).write_text(text, encoding="utf-8")
    store, graph = index_repo(tmp_path, root, [root / name for name in sources], "kinds.sqlite")
    return root, store.load_repository(root), graph


def test_commands_routes_and_main_lead_the_entry_flows_and_tests_are_left_out(tmp_path):
    root, bundle, graph = _entry_kinds_repo(tmp_path)
    flows = build_overview_evidence([], bundle, graph, repository_root=root).entryFlows
    by_name = {flow.qualifiedName: flow for flow in flows}

    assert [flow.kind for flow in flows[:2]] == ["cli-command", "main"]
    assert by_name["main"].modulePath == "launcher.py"
    assert by_name["busy"].kind == "function"
    assert "test_leaves" not in by_name


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_api.py",
        "src/test/java/com/acme/WalletTest.java",
        "pkg/service_test.go",
        "web/__tests__/app.js",
        "web/src/app.spec.ts",
        "conftest.py",
    ],
)
def test_test_files_are_recognised_by_directory_or_name(path):
    assert is_test_path(path)


@pytest.mark.parametrize("path", ["src/latest.py", "src/contest.py", "backend/Wallet.java", "web/src/app.ts"])
def test_ordinary_files_are_not_test_files(path):
    assert not is_test_path(path)


def test_reached_handles_are_ordered_by_first_contact_depth_and_cap_at_five(tmp_path):
    root, bundle, graph, repository_evidence, features = _real(tmp_path)
    evidence = build_overview_evidence(features, bundle, graph, repository_root=root)
    handles = {brief.handle for brief in evidence.features}

    for flow in evidence.entryFlows:
        assert len(flow.reachedHandles) <= MAX_REACHED_FEATURES
        assert set(flow.reachedHandles) <= handles
        assert flow.featureHandle not in flow.reachedHandles


def test_readme_lead_is_the_first_prose_paragraph_after_the_title(tmp_path):
    (tmp_path / "README.md").write_text(
        "# Project\n\n[![badge](x.svg)](y)\n\n- a list item\n\n"
        "Project **turns** code into a wiki. It runs locally.\n\n## Install\n\nLater text.\n",
        encoding="utf-8",
    )

    assert read_readme_lead(tmp_path) == "Project turns code into a wiki. It runs locally."


def test_readme_lead_is_capped(tmp_path):
    (tmp_path / "README.md").write_text("# P\n\n" + "Sentence here. " * 100, encoding="utf-8")

    assert 0 < len(read_readme_lead(tmp_path)) <= MAX_README_LEAD_CHARS


def test_readme_lead_is_empty_without_a_readme(tmp_path):
    assert read_readme_lead(tmp_path) == ""


def test_building_twice_gives_equal_evidence(tmp_path):
    root, bundle, graph, repository_evidence, features = _real(tmp_path)

    first = build_overview_evidence(features, bundle, graph, repository_root=root)
    second = build_overview_evidence(features, bundle, graph, repository_root=root)

    assert first == second
