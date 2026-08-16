# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the standalone `repo-scanner` binary
(specs/020-cli-packaging, research.md sections 2-4).

Build with: pyinstaller packaging/pyinstaller/repo-scanner.spec
(see packaging/build.py for the maintainer-facing wrapper around this).
"""

from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

REPO_ROOT = Path(SPECPATH).resolve().parent.parent  # noqa: F821 (SPECPATH is injected by PyInstaller)
SRC = REPO_ROOT / "src"

# copy_metadata("repo-scanner") bundles the installed distribution's
# .dist-info/METADATA into the frozen app, so `importlib.metadata.version(
# "repo-scanner")` - what `cli.main`'s `--version` flag calls - can find it
# at runtime even though there is no real site-packages install inside a
# one-file binary (research.md section 4).
datas = copy_metadata("repo-scanner")

# doc_generator's Jinja templates and static assets are loaded by path at
# runtime, so PyInstaller's static import analysis can't discover them on
# its own - they must be listed explicitly, mirroring the
# [tool.setuptools.package-data] fix in pyproject.toml (research.md section 3).
datas += [
    (str(SRC / "doc_generator" / "templates"), "doc_generator/templates"),
    (str(SRC / "doc_generator" / "assets"), "doc_generator/assets"),
]

# parser_engine.treesitter_runtime imports each language's tree-sitter
# grammar module by name from a lookup table (importlib-style dynamic
# import), which PyInstaller's static analysis cannot follow - every
# grammar package declared in pyproject.toml's dependencies must be listed
# here explicitly, or `repo-scanner index` would fail to parse that
# language's files only inside the frozen binary (research.md sections 2-3).
hiddenimports = [
    "tree_sitter",
    "tree_sitter_python",
    "tree_sitter_javascript",
    "tree_sitter_typescript",
    "tree_sitter_java",
    "tree_sitter_go",
    "tree_sitter_rust",
]

a = Analysis(  # noqa: F821 (Analysis/PYZ/EXE are injected by PyInstaller)
    [str(SRC / "cli" / "main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="repo-scanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
