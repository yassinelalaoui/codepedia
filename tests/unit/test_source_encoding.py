"""No source file carries UTF-8 that was decoded as cp1252 and saved again.

That round trip turned every "—" in `generator.py` into "â€”", so each Overview,
dependency-diagram and call-sequence page title read "… â€” Documentation" -
and no rendering test noticed, because none compares titles character by
character. The sequences below are what that corruption always produces; none
occurs in real prose or code here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# "â€" starts every corrupted dash, quote and ellipsis; "Â§" is a corrupted "§";
# "â†" a corrupted arrow.
MOJIBAKE = ("â€", "Â§", "â†")
SCANNED = [
    path
    for pattern in ("src/**/*.py", "src/**/*.jinja", "frontend/src/**/*.css", "frontend/src/**/*.ts", "frontend/src/**/*.tsx")
    for path in REPO_ROOT.glob(pattern)
    # Built and vendored bundles are not hand-edited source.
    if "assets" not in path.parts and "node_modules" not in path.parts
]


@pytest.mark.parametrize("path", SCANNED, ids=lambda path: path.relative_to(REPO_ROOT).as_posix())
def test_source_file_has_no_double_encoded_utf8(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    found = [sequence for sequence in MOJIBAKE if sequence in text]
    assert not found, f"{path.name} contains double-encoded UTF-8: {found}"
