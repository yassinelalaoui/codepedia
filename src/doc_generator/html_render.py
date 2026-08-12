from __future__ import annotations

import re
from datetime import datetime, timezone

import markdown as markdown_lib

from .links import HOME_OUTPUT_HTML, relative_output_link
from .markdown_render import render_html_template
from .writer import MERMAID_ASSET_OUTPUT_PATH

_MARKDOWN_EXTENSIONS = ("tables", "fenced_code", "toc")

# python-markdown's fenced_code extension renders a ```mermaid fence as
# <pre><code class="language-mermaid">...</code></pre>. Mermaid's default
# startOnLoad auto-discovery scans for <pre class="mermaid"> elements, so this
# rewrites just that one block shape without touching any other fenced block.
_MERMAID_FENCE_PATTERN = re.compile(
    r'<pre><code class="language-mermaid">(.*?)</code></pre>', re.DOTALL
)


def render_page_html(*, title: str, content_markdown: str, output_path_html: str) -> str:
    content_html = markdown_lib.markdown(content_markdown, extensions=list(_MARKDOWN_EXTENSIONS))
    content_html = _MERMAID_FENCE_PATTERN.sub(r'<pre class="mermaid">\1</pre>', content_html)
    home_href = relative_output_link(from_output_path=output_path_html, to_output_path=HOME_OUTPUT_HTML)
    mermaid_script_href = relative_output_link(
        from_output_path=output_path_html, to_output_path=MERMAID_ASSET_OUTPUT_PATH
    )
    return render_html_template(
        "layout.html.jinja",
        title=title,
        content_html=content_html,
        home_href=home_href or HOME_OUTPUT_HTML,
        mermaid_script_href=mermaid_script_href,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )