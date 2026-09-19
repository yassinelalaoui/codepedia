"""The Overview's module list reads cleanly (038 User Story 4, FR-029 to FR-034).

A repository of its own: two `__init__.py` files that would otherwise share a
label, a README that opens with a heading and emphasis, a module whose
docstring is too long for its row, and one with no docstring at all.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from doc_generator import DocGenerator, OverviewNarrator, open_doc_manifest_store

from ._doc_generator_support import index_repo, wrap_llm

LONG_DOCSTRING = "Loads " + "every record from the archive and checks it against the ledger " * 4 + "before returning"

SOURCES = {
    "pkg_a/__init__.py": '"""Package A."""\n',
    "pkg_b/__init__.py": "",
    "plain.py": "def plain():\n    return 1\n",
    "long.py": f'"""{LONG_DOCSTRING}"""\n\n\ndef load():\n    return 0\n',
    "README.md": (
        "# Fixture\n\n"
        "A *small* fixture with **emphasis** and `code` in it. "
        "It exists so that the module list has a documentation row whose opening runs well past "
        "the width of a single row on the page.\n"
    ),
}


class ScriptedEngine:
    modelName = "scripted"

    def __init__(self) -> None:
        self.calls = 0

    def isAvailable(self) -> bool:
        return True

    def generate(self, prompt) -> str:
        self.calls += 1
        return json.dumps({"lead": ["The repository keeps its loader in `long.py`."]})


def _home(tmp_path: Path, *, narrator: bool, name: str):
    root = tmp_path / "module-list-repo"
    if not root.exists():
        for relative, text in SOURCES.items():
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_text(text, encoding="utf-8")
    store, graph = index_repo(tmp_path, root, [root / relative for relative in SOURCES], f"{name}.sqlite")
    manifest = open_doc_manifest_store(tmp_path / f"{name}-manifest.sqlite")
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest,
        outputRoot=tmp_path / f"{name}-docs",
        repositoryRoot=root,
        overviewNarrator=OverviewNarrator(wrap_llm(ScriptedEngine()), cache=manifest) if narrator else None,
    )
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)
    return next(page for page in doc_set.pages if page.kind == "home")


def _rows(markdown: str) -> list[str]:
    section = markdown.split("## Modules", 1)[1]
    return [line for line in section.splitlines() if line.startswith("- [")]


def _row(rows: list[str], label: str) -> str:
    return next(row for row in rows if row.startswith(f"- [{label}]("))


_LINK = re.compile(r"\[(?:[^\]\\]|\\.)*\]\([^)]*\)")


def _description(row: str) -> str:
    """The text between the module link and the dependency link, unescaped."""
    middle = row.split(")", 1)[1].rsplit("[dependencies](", 1)[0].strip()
    return re.sub(r"\\(.)", r"\1", middle.removeprefix("—").strip())


def test_no_row_contains_orphaned_punctuation(tmp_path):  # FR-029
    for row in _rows(_home(tmp_path, narrator=False, name="g").contentMarkdown):
        outside_links = _LINK.sub("", row.removeprefix("- "))
        assert "(" not in outside_links and ")" not in outside_links, row


def test_no_two_rows_share_a_visible_label(tmp_path):  # FR-030
    labels = [re.match(r"- \[((?:[^\]\\]|\\.)*)\]", row).group(1) for row in _rows(_home(tmp_path, narrator=False, name="g").contentMarkdown)]

    assert len(labels) == len(set(labels)) == len(SOURCES)
    assert r"pkg\_a/\_\_init\_\_" in labels and r"pkg\_b/\_\_init\_\_" in labels


def test_a_prose_description_contains_no_raw_markup(tmp_path):  # FR-031
    home = _home(tmp_path, narrator=False, name="g")
    readme = _description(_row(_rows(home.contentMarkdown), "README"))
    item = next(li for li in re.findall(r"<li[^>]*>.*?</li>", home.renderedHtml, re.DOTALL) if ">README<" in li)
    visible = html.unescape(re.sub(r"<[^>]+>", "", item))

    assert readme.startswith("A small fixture with emphasis and code in it.")
    for marker in ("#", "*", "`", "\\"):
        assert marker not in readme
        assert marker not in visible


def test_a_long_description_ends_at_a_boundary_with_an_ellipsis(tmp_path):  # FR-032
    rows = _rows(_home(tmp_path, narrator=False, name="g").contentMarkdown)
    long_text = _description(_row(rows, "long"))
    readme = _description(_row(rows, "README"))

    # No sentence fits: cut at a word, marked.
    assert long_text.endswith("…")
    stem = long_text.removesuffix("…")
    assert LONG_DOCSTRING.startswith(stem) and LONG_DOCSTRING[len(stem)] == " "
    # A sentence fits: cut after it, and still marked (owner decision, research Decision 12).
    assert readme == "A small fixture with emphasis and code in it. …"


def test_every_row_keeps_its_module_and_dependency_links(tmp_path):  # FR-033
    rows = _rows(_home(tmp_path, narrator=False, name="g").contentMarkdown)

    for row in rows:
        assert re.match(r"- \[(?:[^\]\\]|\\.)*\]\(modules/[^)]+\.md\)", row), row
        assert re.search(r" \[dependencies\]\(diagrams/[^)]+\.md\)$", row), row
    assert _row(rows, "plain").endswith(")") and " — " not in _row(rows, "plain")


def test_the_module_list_is_identical_with_and_without_a_narrator(tmp_path):  # FR-034
    with_narrator = _home(tmp_path, narrator=True, name="with")
    without = _home(tmp_path, narrator=False, name="without")

    assert "The repository keeps its loader in" in with_narrator.contentMarkdown, "the reference page must carry prose"
    assert _rows(with_narrator.contentMarkdown) == _rows(without.contentMarkdown)
