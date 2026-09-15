"""Structural clustering, now the fallback path rather than the main one.

Adapted from `test_sections.py`. The assertions that still describe live
behaviour are kept; what changed is the API they exercise
(`build_fallback_groups` over evidence, rather than `build_sections` over a
whole bundle) and the fact that this code now answers a narrower question -
"how do I group the modules no entry point reaches?".

`test_sections.py` stays in place until A4 deletes `sections.py` with it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))

from _doc_generator_support import build_indexed_repo, index_repo  # noqa: E402
from dependency_graph import DependencyGraph  # noqa: E402
from parser_engine import SourceFile, extract_symbols  # noqa: E402

from doc_generator.features.candidates import build_candidates  # noqa: E402
from doc_generator.features.evidence import build_repository_evidence  # noqa: E402
from doc_generator.features.fallback import (  # noqa: E402
    MIN_FALLBACK_MODULES,
    SPLIT_THRESHOLD_MODULES,
    build_fallback_groups,
    build_import_adjacency,
    default_group_title,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _module(name: str) -> str:
    return f'"""The {name} module."""\n\n\ndef _{name}() -> int:\n    return 1\n'


def _importing_module(name: str, imported: str) -> str:
    return (
        f'"""The {name} module."""\n\n'
        f"from .{imported} import _{imported}\n\n\n"
        f"def _{name}() -> int:\n    return _{imported}()\n"
    )


def _evidence_and_adjacency(tmp_path: Path, root: Path, files: list[Path], db: str):
    store, graph = index_repo(tmp_path, root, files, db)
    bundle = store.load_repository(root)
    evidence = build_repository_evidence(bundle, graph, repository_root=root)
    return evidence, build_import_adjacency(bundle, graph), bundle


def test_groups_are_keyed_by_full_directory_path_not_directory_name(tmp_path):
    """`api/models` and `db/models` are two areas that share a folder name.

    Grouping by `Path(...).parent.name` would collapse them into one "models"
    bucket, describing a structure the repository does not have.
    """
    root = tmp_path / "colliding"
    files = [
        _write(root / "api" / "models.py", _module("api_models")),
        _write(root / "api" / "handlers.py", _module("handlers")),
        _write(root / "db" / "models.py", _module("db_models")),
        _write(root / "db" / "store.py", _module("store")),
    ]
    evidence, adjacency, _bundle = _evidence_and_adjacency(tmp_path, root, files, "colliding.sqlite")

    groups = build_fallback_groups(evidence.modules, adjacency)

    directories = {group.directoryPath for group in groups}
    assert "api" in directories and "db" in directories


def test_every_module_belongs_to_exactly_one_group(tmp_path):
    root = tmp_path / "one-group"
    files = [
        _write(root / "core" / "engine.py", _module("engine")),
        _write(root / "core" / "registry.py", _importing_module("registry", "engine")),
        _write(root / "web" / "server.py", _module("server")),
        _write(root / "web" / "routes.py", _importing_module("routes", "server")),
    ]
    evidence, adjacency, bundle = _evidence_and_adjacency(tmp_path, root, files, "one-group.sqlite")

    groups = build_fallback_groups(evidence.modules, adjacency)

    claimed = [key for group in groups for key in group.memberKeys]
    assert len(claimed) == len(set(claimed))
    assert set(claimed) == {fb.module.sourceFileId for fb in bundle.files}


def test_grouping_is_deterministic_across_runs(tmp_path):
    root = tmp_path / "deterministic"
    files = [
        _write(root / "core" / "engine.py", _module("engine")),
        _write(root / "core" / "registry.py", _importing_module("registry", "engine")),
    ]
    evidence, adjacency, _bundle = _evidence_and_adjacency(tmp_path, root, files, "det.sqlite")

    first = build_fallback_groups(evidence.modules, adjacency)
    second = build_fallback_groups(evidence.modules, adjacency)

    assert [(g.leadModuleKey, g.memberKeys) for g in first] == [
        (g.leadModuleKey, g.memberKeys) for g in second
    ]


def test_a_single_module_directory_is_absorbed_into_what_it_imports(tmp_path):
    """`tools/` holds one module, which imports one from `core/`."""
    root = tmp_path / "absorption"
    files = [
        _write(root / "core" / "engine.py", _module("engine")),
        _write(root / "core" / "registry.py", _importing_module("registry", "engine")),
        _write(root / "tools" / "probe.py", '"""probe."""\n\nfrom ..core.registry import _registry\n\n\ndef _probe() -> int:\n    return _registry()\n'),
    ]
    evidence, adjacency, _bundle = _evidence_and_adjacency(tmp_path, root, files, "absorb.sqlite")

    groups = build_fallback_groups(evidence.modules, adjacency)

    assert all(
        len(group.memberKeys) >= MIN_FALLBACK_MODULES or len(groups) == 1 for group in groups
    ), "a one-module directory is navigation noise, not a concept"


def test_a_directory_below_the_split_threshold_is_never_split(tmp_path):
    root = tmp_path / "small"
    files = [
        _write(root / "pkg" / f"mod_{index}.py", _module(f"mod_{index}"))
        for index in range(SPLIT_THRESHOLD_MODULES - 2)
    ]
    evidence, adjacency, _bundle = _evidence_and_adjacency(tmp_path, root, files, "small.sqlite")

    groups = build_fallback_groups(evidence.modules, adjacency)

    assert len([g for g in groups if g.directoryPath == "pkg"]) == 1


def test_default_title_names_the_directory_and_its_lead_module():
    assert default_group_title("src/chat", "session", split=False) == "chat"
    assert default_group_title("src/chat", "session", split=True) == "chat - session"
    assert default_group_title(".", "main", split=False) == "Root"


def test_documents_are_grouped_by_the_fallback_because_nothing_calls_them(tmp_path):
    """The path prose actually takes, which `src/` alone cannot exercise.

    `identify_entry_points` skips prose files outright, so no README and no
    document is ever reached by an entry point - meaning no candidate can be
    seeded from one and every document arrives here. This repository's own
    `src/` tree contains zero prose files, so without a fixture like this one
    the fallback would look like a rare branch when on a real indexing run it
    groups the entire documentation set.
    """
    root = tmp_path / "docs-repo"
    code = _write(root / "pkg" / "app.py", '"""App."""\n\n\ndef run() -> int:\n    return 1\n')
    doc_one = _write(root / "docs" / "guide.md", "# Guide\n\nHow to use it.\n\n## Setup\n\nSteps.\n")
    doc_two = _write(root / "docs" / "faq.md", "# FAQ\n\nQuestions.\n\n## Why\n\nBecause.\n")

    inventories = [
        extract_symbols(SourceFile(path=code, language="python")),
        extract_symbols(SourceFile(path=doc_one, language="Markdown")),
        extract_symbols(SourceFile(path=doc_two, language="Markdown")),
    ]
    graph = DependencyGraph.build_from_inventories(inventories, sourceFile=str(root))

    from repository_metadata import RepositoryMetadataStore, compute_content_hash
    store = RepositoryMetadataStore(tmp_path / "docs-repo.sqlite")
    store.ensure_repository(root, detected_languages=("python", "Markdown"))
    for inventory, language in zip(inventories, ("python", "Markdown", "Markdown")):
        source_path = Path(inventory.sourceFile)
        store.store_inventory(
            repository_root=root,
            source_file=SourceFile(path=source_path, language=language),
            inventory=inventory,
            content_hash=compute_content_hash(source_path),
        )
    bundle = store.load_repository(root)

    evidence = build_repository_evidence(bundle, graph, repository_root=root)
    adjacency = build_import_adjacency(bundle, graph)

    documents = [item for item in evidence.modules if item.filePath.endswith(".md")]
    assert len(documents) == 2, "both documents must have evidence rows"
    assert all(item.reachingEntryPointKeys == () for item in documents), (
        "no entry point reaches a document - that is why they need the fallback"
    )

    candidates = build_candidates(evidence, adjacency)
    claimed = {key for candidate in candidates for key in candidate.memberKeys}
    assert claimed == {fb.module.sourceFileId for fb in bundle.files}, (
        "documents must still be claimed by a candidate, or they vanish from the wiki"
    )


# --- Spec 039: the root limit, and Java and JS/TS edges -----------------------


def test_a_lone_subdirectory_never_joins_a_root_group_by_ancestry():
    """039 FR-006: `frontend/x/` shares no imports with the root-level files.

    033 absorbed a directory too small to stand alone into the root group when
    no nearer ancestor was one. Now it stays apart, for folding to place.
    """
    from doc_generator.features.evidence import FeatureEvidence

    evidence = [
        FeatureEvidence(moduleKey=key, moduleName=Path(key).stem, filePath=f"/r/{key}", directoryPath=directory)
        for key, directory in (("a.py", "."), ("b.py", "."), ("frontend/x/lone.py", "frontend/x"))
    ]

    groups = build_fallback_groups(evidence, {item.moduleKey: {} for item in evidence})

    lone = next(group for group in groups if "frontend/x/lone.py" in group.memberKeys)
    assert lone.memberKeys == ("frontend/x/lone.py",)


def _by_path(bundle, root: Path, adjacency) -> dict[str, dict[str, object]]:
    path = {
        fb.module.sourceFileId: Path(fb.module.filePath).resolve().relative_to(root.resolve()).as_posix()
        for fb in bundle.files
    }
    return {path[a]: {path[b]: weight for b, weight in row.items()} for a, row in adjacency.items()}


def test_python_adjacency_is_unchanged(tmp_path):
    """FR-005, pinned to values taken from 033's code before 039 changed this module.

    Each Python import weighs 2: 033 counts an edge from both of its ends. The
    second fixture has two `models.py`, a relative import, a package-relative
    `from . import`, a dotted absolute import and stdlib imports that must add
    nothing.
    """
    root, store, graph = build_indexed_repo(tmp_path)
    bundle = store.load_repository(root)
    assert _by_path(bundle, root, build_import_adjacency(bundle, graph)) == {
        "alpha.py": {"beta.py": 2},
        "beta.py": {"alpha.py": 2, "gamma.py": 2},
        "gamma.py": {"beta.py": 2},
    }

    pkgs = tmp_path / "pkgs"
    sources = {
        "app/__init__.py": "",
        "app/models.py": "class Item:\n    pass\n",
        "app/service.py": "from .models import Item\nimport os\nfrom __future__ import annotations\n\n\ndef make():\n    return Item()\n",
        "app/cli.py": "from .service import make\nfrom . import models\n\n\ndef run():\n    return make()\n",
        "lib/models.py": "import json\n\n\nclass Other:\n    pass\n",
        "lib/util.py": "from lib.models import Other\nimport os\n\n\ndef helper():\n    return Other()\n",
    }
    files = [_write(pkgs / name, text) for name, text in sources.items()]
    store, graph = index_repo(tmp_path, pkgs, files, "pkgs.sqlite")
    bundle = store.load_repository(pkgs)
    adjacency = build_import_adjacency(bundle, graph)

    assert _by_path(bundle, pkgs, adjacency) == {
        "app/__init__.py": {"app/cli.py": 2},
        "app/cli.py": {"app/__init__.py": 2, "app/service.py": 2},
        "app/models.py": {"app/service.py": 2},
        "app/service.py": {"app/cli.py": 2, "app/models.py": 2},
        "lib/models.py": {"lib/util.py": 2},
        "lib/util.py": {"lib/models.py": 2},
    }
    assert all(type(weight) is int for row in adjacency.values() for weight in row.values()), (
        "Python weights stay `int`, value for value"
    )


def test_java_and_ts_edges_are_merged_into_the_adjacency(tmp_path):
    root = tmp_path / "mixed"
    files = [
        _write(root / "api" / "Controller.java", "package api;\n\nimport svc.Service;\n\npublic class Controller {}\n"),
        _write(root / "svc" / "Service.java", "package svc;\n\npublic class Service {}\n"),
        _write(root / "web" / "page.ts", "import { load } from './data';\n\nexport const page = load;\n"),
        _write(root / "web" / "data.ts", "export const load = 1;\n"),
        _write(root / "tools" / "alpha.py", _importing_module("alpha", "beta")),
        _write(root / "tools" / "beta.py", _module("beta")),
    ]
    store, graph = index_repo(tmp_path, root, files, "mixed.sqlite")
    bundle = store.load_repository(root)

    adjacency = _by_path(bundle, root, build_import_adjacency(bundle, graph))

    assert len(adjacency) == len(bundle.files), "every module keeps a row"
    assert adjacency["api/Controller.java"] == {"svc/Service.java": 1}
    assert adjacency["web/page.ts"] == {"web/data.ts": 1}
    assert adjacency["tools/alpha.py"] == {"tools/beta.py": 2}, "Python keeps 033's weight"
