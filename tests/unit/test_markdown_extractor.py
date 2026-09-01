"""Heading extraction for documentation files.

The mapping is heading -> existing symbol type (`##` becomes a class, `###` a
function owned by it, and nothing deeper is promoted at all), so these tests
assert the three things that mapping has to get right: which lines actually are
headings, identifiers that survive an edit elsewhere in the file, and that the
depth cap costs no prose.
"""

from __future__ import annotations

from pathlib import Path

from parser_engine.extractor import extract_symbols
from parser_engine.models import SourceFile


def _inventory(tmp_path: Path, text: str, name: str = "doc.md"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return extract_symbols(SourceFile(path=path, language="Markdown"))


def test_a_hash_inside_a_fenced_block_is_not_a_heading(tmp_path: Path):
    inventory = _inventory(
        tmp_path,
        "# Doc\n\n## Real\n\n```bash\n# not a heading\n## also not a heading\n```\n",
    )
    assert [item.name for item in inventory.classes] == ["Real"]


def test_a_tilde_fence_also_hides_headings(tmp_path: Path):
    inventory = _inventory(tmp_path, "# Doc\n\n~~~\n## hidden\n~~~\n\n## Visible\n")
    assert [item.name for item in inventory.classes] == ["Visible"]


def test_a_longer_closing_fence_still_closes_the_block(tmp_path: Path):
    inventory = _inventory(tmp_path, "# Doc\n\n```\n## hidden\n````\n\n## Visible\n")
    assert [item.name for item in inventory.classes] == ["Visible"]


def test_setext_underlines_are_headings(tmp_path: Path):
    inventory = _inventory(tmp_path, "# Doc\n\nLegacy Section\n--------------\n\nBody.\n")
    assert [item.name for item in inventory.classes] == ["Legacy Section"]


def test_a_thematic_break_is_not_a_setext_heading(tmp_path: Path):
    # `---` after a blank line separates content, it does not promote the
    # paragraph above it.
    inventory = _inventory(tmp_path, "# Doc\n\nParagraph.\n\n---\n\nMore.\n")
    assert inventory.classes == ()


def test_yaml_front_matter_is_metadata_not_prose(tmp_path: Path):
    inventory = _inventory(tmp_path, "---\ntitle: Spec\n---\n\n# Doc\n\nIntro.\n\n## One\n\nBody.\n")
    assert [item.name for item in inventory.classes] == ["One"]
    assert "title: Spec" not in inventory.module.docstring
    assert inventory.module.docstring == "# Doc\n\nIntro."


def test_repeated_heading_names_get_distinct_ids(tmp_path: Path):
    inventory = _inventory(tmp_path, "# Doc\n\n## Install\n\nOne.\n\n## Install\n\nTwo.\n")
    identifiers = [item.id for item in inventory.classes]
    assert len(identifiers) == 2
    assert len(set(identifiers)) == 2


def test_heading_ids_survive_a_paragraph_inserted_above_them(tmp_path: Path):
    """The property the whole id scheme exists for.

    `_stable_id` seeds on line numbers, which in prose means one inserted
    paragraph rewrites every anchor, every `search-index.json` entry and every
    stored chat citation below it.
    """
    before = _inventory(tmp_path, "# Doc\n\nIntro.\n\n## Install\n\nBody.\n")
    after = _inventory(tmp_path, "# Doc\n\nIntro.\n\nAn inserted paragraph.\n\n## Install\n\nBody.\n")

    assert before.module.id == after.module.id
    assert [item.id for item in before.classes] == [item.id for item in after.classes]
    # The spans really did move; it is only the identity that held still.
    assert before.classes[0].lineStart != after.classes[0].lineStart


def test_subsections_are_owned_by_the_section_above_them(tmp_path: Path):
    inventory = _inventory(
        tmp_path,
        "# Doc\n\n## Install\n\nBody.\n\n### From source\n\nA.\n\n### From a release\n\nB.\n\n## Usage\n\nC.\n",
    )
    install = next(item for item in inventory.classes if item.name == "Install")
    usage = next(item for item in inventory.classes if item.name == "Usage")

    assert len(install.methods) == 2
    assert usage.methods == ()
    assert all(item.owner == "class" for item in inventory.functions)


def test_a_subsection_without_a_section_above_it_belongs_to_the_module(tmp_path: Path):
    inventory = _inventory(tmp_path, "# Doc\n\nIntro.\n\n### Orphan\n\nBody.\n")
    assert [item.owner for item in inventory.functions] == ["module"]
    assert inventory.classes == ()


def test_a_section_spans_its_subsections_but_its_prose_does_not(tmp_path: Path):
    # The span feeds chunking and summarization, which need the whole section;
    # the docstring feeds the page, which must not repeat the subsections.
    inventory = _inventory(tmp_path, "# Doc\n\n## Install\n\nOwn prose.\n\n### Detail\n\nNested prose.\n")
    install = inventory.classes[0]

    assert install.docstring == "Own prose."
    assert install.lineEnd >= inventory.functions[0].lineEnd


def test_a_document_without_headings_still_yields_a_module(tmp_path: Path):
    inventory = _inventory(tmp_path, "Just prose, no headings at all.\n")
    assert inventory.module.name == "doc"
    assert inventory.module.docstring == "Just prose, no headings at all."
    assert inventory.classes == ()
    assert inventory.functions == ()


def test_headings_deeper_than_h3_do_not_become_symbols(tmp_path: Path):
    # Every promoted heading costs one LLM summary call and one embedding, and a
    # `####` is rarely a documentation unit anyone navigates to on its own.
    inventory = _inventory(
        tmp_path,
        "# Doc\n\n## Install\n\nOwn prose.\n\n### Detail\n\nNested prose.\n\n#### Deeper\n\nDeepest prose.\n",
    )

    assert [item.name for item in inventory.classes] == ["Install"]
    assert [item.name for item in inventory.functions] == ["Detail"]


def test_a_heading_past_the_cap_folds_into_the_promoted_heading_above_it(tmp_path: Path):
    # The saving must not be a loss: the docstring feeds the page, the chunks
    # and the search index, so text under a `####` has to survive the cap.
    inventory = _inventory(
        tmp_path,
        "# Doc\n\n### Detail\n\nOwn prose.\n\n#### Deeper\n\nDeepest prose.\n\n##### Deepest\n\nMore.\n",
    )
    detail = inventory.functions[0]

    assert "Deepest prose." in detail.docstring
    assert "More." in detail.docstring
    assert detail.docstring.startswith("Own prose.")


def test_a_document_whose_only_headings_are_past_the_cap_is_all_intro(tmp_path: Path):
    inventory = _inventory(tmp_path, "# Doc\n\nIntro.\n\n#### Deep\n\nDeep prose.\n")

    assert inventory.classes == ()
    assert inventory.functions == ()
    assert "Deep prose." in inventory.module.docstring


def test_a_section_and_a_subsection_of_the_same_name_get_distinct_ids(tmp_path: Path):
    """The ordinal counts per kind, so these two do not share a counter.

    A `##` and a `###` both named "Install" are different symbols, and each is
    the first of its kind - which means adding one never renumbers the other.
    """
    inventory = _inventory(tmp_path, "# Doc\n\n## Install\n\nOne.\n\n### Install\n\nTwo.\n")
    section = inventory.classes[0]
    subsection = inventory.functions[0]

    assert section.name == subsection.name == "Install"
    assert section.id != subsection.id
    assert section.id.startswith("class_")
    assert subsection.id.startswith("function_")
