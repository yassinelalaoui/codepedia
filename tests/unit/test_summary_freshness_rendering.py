"""How a summary's freshness reaches the page.

Both markers are `attr_list` annotations on a Markdown paragraph, and
`attr_list` only binds `{: .class }` to the block it terminates. Written without
a blank line between them the summary and its staleness note formed a *single*
paragraph, so the last annotation won and the `.ai-generated` badge was emitted
as literal text on every summary in the wiki. These pin the rendered classes
rather than the template's source.
"""

from __future__ import annotations

from doc_generator.html_render import render_page_html
from doc_generator.markdown_render import render_markdown_template


class _Symbol:
    """Minimal stand-in for the symbol fields the module template reads."""

    def __init__(self, name: str, *, summary: str = "", stale: bool = False) -> None:
        self.id = f"symbol_{name}"
        self.name = name
        self.docstring = ""
        self.generatedSummary = summary
        self.summaryIsStale = stale
        self.parentClass = None
        self.parameters = ()
        self.returnType = None


def _render(module_summary: str, *, stale: bool) -> str:
    module = _Symbol("app", summary=module_summary, stale=stale)
    module.filePath = "app.py"
    markdown_text = render_markdown_template(
        "module.md.jinja",
        is_prose=False,
        module=module,
        classes=(),
        functions=(),
        related_links=(),
        diagram_link=None,
        section_link=None,
        entry_point_links={},
    )
    return render_page_html(
        title="app", content_markdown=markdown_text, output_path_html="modules/app.html"
    )


def test_a_fresh_summary_carries_the_generated_badge_and_no_warning():
    html = _render("Builds the index.", stale=False)
    assert '<p class="ai-generated">Builds the index.</p>' in html
    assert "summary-stale" not in html
    # The annotation must never survive as visible text.
    assert "{: .ai-generated }" not in html


def test_a_stale_summary_keeps_its_badge_and_adds_the_warning():
    html = _render("Builds the index.", stale=True)
    assert '<p class="ai-generated">Builds the index.</p>' in html
    assert '<p class="summary-stale">' in html
    assert "describes an earlier version" in html
    assert "{: .ai-generated }" not in html
    assert "{: .summary-stale }" not in html
