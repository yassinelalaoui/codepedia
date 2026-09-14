"""`prose.disambiguated_labels`: every row of the Overview's module list its own name (038 US4).

Display only, like `display_label`: the function returns strings to render and
nothing else, so these tests look at nothing but the strings.
"""

from __future__ import annotations

import random

from doc_generator.prose import disambiguated_labels
from repository_metadata.models import ModuleSymbol

ROOT = "C:/work/sample-repo"


def _module(relative_path: str) -> ModuleSymbol:
    stem = relative_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return ModuleSymbol(
        id=f"m:{relative_path}",
        sourceFileId=f"sf:{relative_path}",
        kind="module",
        name=stem,
        lineStart=1,
        lineEnd=1,
        filePath=f"{ROOT}/{relative_path}",
    )


def _labels(*paths: str) -> dict[str, str]:
    labels = disambiguated_labels([_module(path) for path in paths], ROOT)
    return {key.removeprefix("sf:"): label for key, label in labels.items()}


def test_unique_code_labels_are_unchanged():
    assert _labels("src/app/alpha.py", "src/lib/beta.py") == {"src/app/alpha.py": "alpha", "src/lib/beta.py": "beta"}


def test_duplicate_init_modules_get_the_shortest_unique_path_tail():
    labels = _labels(
        "src/bibliotheca/__init__.py",
        "src/bibliotheca/api/__init__.py",
        "src/bibliotheca/core/__init__.py",
        "web/x/a/__init__.py",
        "lib/x/a/__init__.py",
        "src/bibliotheca/app.py",
    )

    assert labels == {
        "src/bibliotheca/__init__.py": "bibliotheca/__init__",
        "src/bibliotheca/api/__init__.py": "api/__init__",
        "src/bibliotheca/core/__init__.py": "core/__init__",
        "web/x/a/__init__.py": "web/x/a/__init__",
        "lib/x/a/__init__.py": "lib/x/a/__init__",
        "src/bibliotheca/app.py": "app",
    }


def test_prose_files_keep_their_display_label():
    labels = _labels("docs/architecture.md", "src/architecture.py", "README.md")

    assert labels["docs/architecture.md"] == "docs/architecture"
    assert labels["README.md"] == "README"
    assert labels["src/architecture.py"] == "architecture"


def test_labels_are_deterministic_across_input_order():
    paths = [f"pkg{i}/sub/__init__.py" for i in range(6)] + ["pkg0/other/__init__.py", "solo.py"]
    expected = _labels(*paths)
    shuffled = paths[:]
    random.Random(38).shuffle(shuffled)

    assert _labels(*shuffled) == expected
    assert len(set(expected.values())) == len(paths)


def test_a_label_never_includes_the_extension():
    labels = _labels("src/api/search.py", "web/static/search.ts", "a/__init__.py", "b/__init__.py")

    assert labels["src/api/search.py"] == "api/search"
    assert labels["web/static/search.ts"] == "static/search"
    assert not any(label.endswith((".py", ".ts")) for label in labels.values())


def test_files_differing_only_by_extension_keep_it_to_stay_distinct():
    """The one case no extension-free tail can separate (spec FR-030 wins)."""
    labels = _labels("web/search.py", "web/search.ts")

    assert labels == {"web/search.py": "web/search.py", "web/search.ts": "web/search.ts"}
