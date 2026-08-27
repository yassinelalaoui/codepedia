from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))

from _doc_generator_support import build_indexed_repo, index_repo  # noqa: E402

from doc_generator.sections import (  # noqa: E402
    MIN_SECTION_MODULES,
    SPLIT_THRESHOLD_MODULES,
    build_sections,
    default_section_title,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _module(name: str) -> str:
    return f'"""The {name} module."""\n\n\ndef {name}() -> int:\n    return 1\n'


def _importing_module(name: str, imported: str) -> str:
    return f'"""The {name} module."""\n\nfrom {imported} import {imported}\n\n\ndef {name}() -> int:\n    return {imported}()\n'


def _colliding_directories_repo(tmp_path: Path):
    """Two areas whose directories both contain a `models` module.

    Under a grouping keyed on the directory *name* these would still be two
    buckets, but under one keyed on `Path(...).parent.name` of a deeper tree
    they would collapse; either way the point is that `api` and `db` are two
    areas, and nothing about the files' names may merge them.
    """
    root = tmp_path / "colliding-repo"
    files = [
        _write(root / "api" / "models.py", _module("models")),
        _write(root / "api" / "handlers.py", _module("handlers")),
        _write(root / "db" / "models.py", _module("db_models")),  # module name is the file name: `models`
        _write(root / "db" / "store.py", _module("store")),
    ]
    store, graph = index_repo(tmp_path, root, files, "colliding-repo.sqlite")
    return root, store, graph


def _absorption_repo(tmp_path: Path):
    """`tools/` holds a single module, which imports one from `core/`."""
    root = tmp_path / "absorption-repo"
    files = [
        _write(root / "core" / "engine.py", _module("engine")),
        _write(root / "core" / "registry.py", _importing_module("registry", "engine")),
        _write(root / "tools" / "probe.py", _importing_module("probe", "registry")),
    ]
    store, graph = index_repo(tmp_path, root, files, "absorption-repo.sqlite")
    return root, store, graph


def test_sections_are_keyed_by_full_directory_path_not_directory_name(tmp_path):
    root, store, graph = _colliding_directories_repo(tmp_path)
    bundle = store.load_repository(root)

    selection = build_sections(bundle, graph, repository_root=root)

    module_names_by_directory = {
        section.directoryPath: {member.name for member in section.members} for section in selection.sections
    }
    # Both directories contain a module named `models`; they must stay apart.
    assert module_names_by_directory == {
        "api": {"models", "handlers"},
        "db": {"models", "store"},
    }


def test_every_module_belongs_to_exactly_one_section(tmp_path):
    root, store, graph = _colliding_directories_repo(tmp_path)
    bundle = store.load_repository(root)

    selection = build_sections(bundle, graph, repository_root=root)

    assigned = [member.moduleKey for section in selection.sections for member in section.members]
    assert sorted(assigned) == sorted(file_bundle.module.sourceFileId for file_bundle in bundle.files)
    assert len(assigned) == len(set(assigned))


def test_section_derivation_is_deterministic_across_runs(tmp_path):
    root, store, graph = _colliding_directories_repo(tmp_path)
    bundle = store.load_repository(root)

    assert build_sections(bundle, graph, repository_root=root) == build_sections(
        bundle, graph, repository_root=root
    )


def test_single_module_directory_is_absorbed_into_the_section_it_imports(tmp_path):
    root, store, graph = _absorption_repo(tmp_path)
    bundle = store.load_repository(root)

    selection = build_sections(bundle, graph, repository_root=root)

    assert "tools" not in {section.directoryPath for section in selection.sections}
    probe_key = next(
        file_bundle.module.sourceFileId for file_bundle in bundle.files if file_bundle.module.name == "probe"
    )
    assert selection.by_module_key()[probe_key].directoryPath == "core"
    assert all(len(section.members) >= MIN_SECTION_MODULES for section in selection.sections)


def test_sections_report_the_neighbours_they_exchange_imports_with(tmp_path):
    """`api` and `db` never import each other, so neither has a neighbour."""
    root, store, graph = _colliding_directories_repo(tmp_path)
    bundle = store.load_repository(root)

    selection = build_sections(bundle, graph, repository_root=root)

    assert all(section.neighborKeys == () for section in selection.sections)


def test_flat_repository_yields_one_root_section(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    bundle = store.load_repository(root)

    selection = build_sections(bundle, graph, repository_root=root)

    assert len(selection.sections) == 1
    section = selection.sections[0]
    assert section.directoryPath == "."
    assert section.title == "Root"
    assert {member.name for member in section.members} == {"alpha", "beta", "gamma"}
    assert section.neighborKeys == ()


def test_membership_hash_tracks_members_not_their_contents(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    bundle = store.load_repository(root)
    section = build_sections(bundle, graph, repository_root=root).sections[0]

    rewritten = replace(section, members=tuple(replace(m, docstring="rewritten") for m in section.members))
    reduced = replace(section, members=section.members[:-1])

    assert rewritten.membershipHash() == section.membershipHash()
    assert reduced.membershipHash() != section.membershipHash()


def test_oversized_directory_splits_into_communities(tmp_path):
    """One directory, two clusters of modules with no import between them."""
    root = tmp_path / "wide-repo"
    files = []
    for cluster in ("red", "blue"):
        hub = f"{cluster}_hub"
        files.append(_write(root / "pkg" / f"{hub}.py", _module(hub)))
        for index in range(SPLIT_THRESHOLD_MODULES // 2):
            leaf = f"{cluster}_leaf_{index}"
            files.append(_write(root / "pkg" / f"{leaf}.py", _importing_module(leaf, hub)))
    store, graph = index_repo(tmp_path, root, files, "wide-repo.sqlite")
    bundle = store.load_repository(root)

    selection = build_sections(bundle, graph, repository_root=root)

    assert len(bundle.files) > SPLIT_THRESHOLD_MODULES
    assert len(selection.sections) == 2
    assert {section.directoryPath for section in selection.sections} == {"pkg"}
    assert len({section.key for section in selection.sections}) == 2
    for section in selection.sections:
        clusters = {member.name.split("_")[0] for member in section.members}
        assert clusters in ({"red"}, {"blue"}), "a community must not mix the two clusters"
        # The hub is the most internally connected member, so it names the split.
        assert section.title.endswith("_hub")


def test_a_directory_below_the_split_threshold_is_never_split(tmp_path):
    root = tmp_path / "narrow-repo"
    files = [_write(root / "pkg" / "hub.py", _module("hub"))]
    files += [
        _write(root / "pkg" / f"leaf_{index}.py", _importing_module(f"leaf_{index}", "hub"))
        for index in range(3)
    ]
    files.append(_write(root / "pkg" / "island.py", _module("island")))
    store, graph = index_repo(tmp_path, root, files, "narrow-repo.sqlite")
    bundle = store.load_repository(root)

    selection = build_sections(bundle, graph, repository_root=root)

    assert len(selection.sections) == 1
    assert len(selection.sections[0].members) == len(files)


def test_default_title_names_the_directory_and_its_lead_module():
    assert default_section_title(".", ".") == "Root"
    assert default_section_title("src/doc_generator", "src/doc_generator") == "doc_generator"
    assert default_section_title("pkg#red_hub", "pkg") == "pkg - red_hub"
