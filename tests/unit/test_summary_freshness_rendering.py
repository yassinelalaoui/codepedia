"""How a summary's freshness reaches the page.

The staleness note is an `attr_list` annotation on its own Markdown paragraph,
and `attr_list` only binds `{: .class }` to the block it terminates. Written
without a blank line after the summary, the two would form a *single*
paragraph and the summary itself would take the note's class. These pin the
rendered HTML rather than the template's source.
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


def test_a_fresh_summary_is_a_plain_paragraph_with_no_warning():
    html = _render("Builds the index.", stale=False)
    assert "<p>Builds the index.</p>" in html
    assert "summary-stale" not in html
    assert "ai-generated" not in html


def test_a_stale_summary_stays_plain_and_adds_the_warning():
    html = _render("Builds the index.", stale=True)
    assert "<p>Builds the index.</p>" in html
    assert '<p class="summary-stale">' in html
    assert "describes an earlier version" in html
    # The annotation must never survive as visible text.
    assert "{: .summary-stale }" not in html
