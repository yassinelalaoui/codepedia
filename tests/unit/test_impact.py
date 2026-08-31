"""Navigation invalidation: what makes an *untouched* page stale.

The section/module tree is rendered into every page's sidebar and once more on
the home page, so it is the one thing a per-page impact set cannot express. The
tests below pin the two ways it changes: the set of pages moves, or a section
gets a new name.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))

from _doc_generator_support import build_indexed_repo  # noqa: E402

from doc_generator import links  # noqa: E402
from doc_generator.impact import compute_regeneration_impact  # noqa: E402
from doc_generator.models import PageManifestEntry  # noqa: E402
from doc_generator.sections import build_sections  # noqa: E402


def _entry(page_id: str, kind: str) -> PageManifestEntry:
    return PageManifestEntry(
        pageId=page_id,
        kind=kind,
        sourceSymbolIds=(),
        contentHash="hash",
        outputPathMarkdown=f"{page_id}.md",
        outputPathHtml=f"{page_id}.html",
        lastGeneratedAt="2026-01-01T00:00:00+00:00",
    )


def _settled_repo(tmp_path: Path):
    """A repository whose manifest already describes exactly today's pages.

    Nothing structural has moved, so every flag below is answering only the
    question the test asks it.
    """
    root, store, graph = build_indexed_repo(tmp_path)
    bundle = store.load_repository(root)
    sections = build_sections(bundle, graph, repository_root=root).sections

    entries = [
        _entry(links.module_page_id(file_bundle.module.sourceFileId), "module") for file_bundle in bundle.files
    ]
    entries += [_entry(links.section_page_id(section.key), "section") for section in sections]
    entries.append(_entry(links.HOME_PAGE_ID, "home"))
    return bundle, graph, sections, entries


def test_an_unchanged_tree_regenerates_no_navigation(tmp_path):
    bundle, graph, sections, entries = _settled_repo(tmp_path)

    impact = compute_regeneration_impact(
        bundle=bundle,
        dependency_graph=graph,
        previous_entries=entries,
        sections=sections,
        previous_section_titles={section.key: section.title for section in sections},
    )

    assert impact.requiresNavigationRegeneration is False
    assert impact.requiresHomePageRegeneration is False


def test_a_renamed_section_invalidates_every_page(tmp_path):
    """B4: the page id set is identical, and the sidebar is still wrong.

    A section's page id is derived from its directory, never its title, so a
    narrator that renames "src" to "Parsing Engine" moves no page - and under
    the set-comparison-only predicate this shipped as "nothing changed", leaving
    the old name in the sidebar of every page that did not happen to regenerate.
    """
    bundle, graph, sections, entries = _settled_repo(tmp_path)
    previous_titles = {section.key: section.title for section in sections}
    renamed = (replace(sections[0], title="Parsing Engine", isNarrated=True), *sections[1:])

    impact = compute_regeneration_impact(
        bundle=bundle,
        dependency_graph=graph,
        previous_entries=entries,
        sections=renamed,
        previous_section_titles=previous_titles,
    )

    assert previous_titles[renamed[0].key] != renamed[0].title
    assert {links.section_page_id(section.key) for section in renamed} == {
        links.section_page_id(section.key) for section in sections
    }, "the page id set is unchanged - only the name moved"
    assert impact.requiresNavigationRegeneration is True
    assert impact.requiresHomePageRegeneration is True


def test_a_never_narrated_section_is_not_treated_as_renamed(tmp_path):
    """No stored title means no narration has run, not a rename.

    The first documentation run has an empty narration table, and reading that
    as "every section was renamed" would make the very first incremental run
    regenerate everything for no reason.
    """
    bundle, graph, sections, entries = _settled_repo(tmp_path)

    impact = compute_regeneration_impact(
        bundle=bundle,
        dependency_graph=graph,
        previous_entries=entries,
        sections=sections,
        previous_section_titles={},
    )

    assert impact.requiresNavigationRegeneration is False


def test_a_removed_module_still_invalidates_the_navigation(tmp_path):
    """The pre-existing trigger keeps working, unmerged predicate or not."""
    bundle, graph, sections, entries = _settled_repo(tmp_path)
    entries.append(_entry(links.module_page_id("a-module-that-is-gone"), "module"))

    impact = compute_regeneration_impact(
        bundle=bundle,
        dependency_graph=graph,
        previous_entries=entries,
        sections=sections,
        previous_section_titles={section.key: section.title for section in sections},
    )

    assert impact.requiresNavigationRegeneration is True
