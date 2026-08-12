from __future__ import annotations

from datetime import datetime, timezone

import markdown as markdown_lib

from .links import HOME_OUTPUT_HTML, relative_output_link
from .markdown_render import render_html_template

_MARKDOWN_EXTENSIONS = ("tables", "fenced_code", "toc")


def render_page_html(*, title: str, content_markdown: str, output_path_html: str) -> str:
    content_html = markdown_lib.markdown(content_markdown, extensions=list(_MARKDOWN_EXTENSIONS))
    home_href = relative_output_link(from_output_path=output_path_html, to_output_path=HOME_OUTPUT_HTML)
    return render_html_template(
        "layout.html.jinja",
        title=title,
        content_html=content_html,
        home_href=home_href or HOME_OUTPUT_HTML,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )