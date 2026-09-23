"""Every runtime-loaded asset directory reaches both ways of shipping the app.

There are two, and they are configured independently, which is how they drift:

- a pip install reads `[tool.setuptools.package-data]` in `pyproject.toml`;
- the standalone binary reads the `datas` list in the PyInstaller spec.

PyInstaller does not read setuptools' package-data, so adding a directory to
one does nothing for the other. That is exactly what happened to the hub: its
page bundle was declared in `pyproject.toml` when the homepage shipped, and the
PyInstaller spec - written earlier, for a project that had no homepage yet - was
never updated. The pip install was fine and the binary silently served a 404 on
`/`, because `hub_server.app` skips the static mount when the directory is
missing rather than failing loudly.

These tests discover the asset directories from the source tree rather than
naming them, so a package that grows one later is covered without anyone
remembering to come back here.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
SPEC_FILE = REPO_ROOT / "packaging" / "pyinstaller" / "codepedia.spec"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Directory names that are loaded by path at runtime rather than imported.
_ASSET_DIR_NAMES = ("assets", "templates")


def _runtime_asset_dirs() -> list[tuple[str, str]]:
    """Every non-empty `src/<package>/<assets|templates>/`, as (package, dir)."""
    found: list[tuple[str, str]] = []
    for package_dir in sorted(SRC.iterdir()):
        if not package_dir.is_dir() or not (package_dir / "__init__.py").exists():
            continue
        for name in _ASSET_DIR_NAMES:
            candidate = package_dir / name
            if candidate.is_dir() and any(candidate.iterdir()):
                found.append((package_dir.name, name))
    return found


def test_the_source_tree_actually_has_asset_directories_to_check():
    """Guards the guard: a discovery bug here would make every test below
    vacuously pass."""
    assert _runtime_asset_dirs(), "no asset directories discovered under src/"


@pytest.mark.parametrize(("package", "directory"), _runtime_asset_dirs())
def test_every_asset_directory_is_bundled_into_the_binary(package: str, directory: str):
    spec_text = SPEC_FILE.read_text(encoding="utf-8")

    # The spec builds each entry as `SRC / "<package>" / "<directory>"` and
    # names the destination `"<package>/<directory>"`. Assert on the
    # destination, which is the part that has to be exact.
    destination = f'"{package}/{directory}"'
    assert destination in spec_text, (
        f"{package}/{directory} is loaded by path at runtime but is not in the "
        f"PyInstaller spec's `datas`, so the frozen binary would not contain it. "
        f"Add it to {SPEC_FILE.relative_to(REPO_ROOT)}."
    )


@pytest.mark.parametrize(("package", "directory"), _runtime_asset_dirs())
def test_every_asset_directory_is_shipped_by_a_pip_install(package: str, directory: str):
    package_data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["setuptools"][
        "package-data"
    ]
    patterns = package_data.get(package, [])

    assert any(pattern.startswith(f"{directory}/") for pattern in patterns), (
        f"{package}/{directory} is loaded by path at runtime but no "
        f"[tool.setuptools.package-data] pattern covers it, so a pip install "
        f"would omit it."
    )
