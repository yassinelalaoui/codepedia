from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Sequence

import markdown as markdown_lib

from .links import DIAGRAMS_INDEX_OUTPUT_HTML, HOME_OUTPUT_HTML, relative_output_link
from .markdown_render import render_html_template
from .writer import (
    MERMAID_ASSET_OUTPUT_PATH,
    SEARCH_INDEX_OUTPUT_PATH,
    WIKI_UI_CSS_OUTPUT_PATH,
    WIKI_UI_JS_OUTPUT_PATH,
)

_MARKDOWN_EXTENSIONS = ("tables", "fenced_code", "toc", "attr_list")

# python-markdown's fenced_code extension renders a ```mermaid fence as
# <pre><code class="language-mermaid">...</code></pre>. Mermaid's default
# startOnLoad auto-discovery scans for <pre class="mermaid"> elements, so this
# rewrites just that one block shape without touching any other fenced block.
_MERMAID_FENCE_PATTERN = re.compile(
    r'<pre><code class="language-mermaid">(.*?)</code></pre>', re.DOTALL
)

# `content_markdown` is shared with the .md output and so links to other wiki
# pages the normal way a markdown reader expects: relative-path.md (built by
# links.py's build_page_link/relative_markdown_link). Readers of *this* HTML
# page instead need relative-path.html - otherwise StaticFiles serves the raw
# markdown source for every cross-link (no styling, no mermaid rendering, no
# chat/search widgets), which only the top nav's Home link and the mermaid
# diagram's own click targets were ever built to avoid. Excludes absolute
# URLs so an external ...*.md link (e.g. from a docstring) isn't rewritten.
_INTERNAL_MD_LINK_PATTERN = re.compile(r'href="(?!https?://|mailto:)([^"#]+)\.md(#[^"]*)?"')


def _rewrite_internal_links_to_html(content_html: str) -> str:
    return _INTERNAL_MD_LINK_PATTERN.sub(lambda match: f'href="{match.group(1)}.html{match.group(2) or ""}"', content_html)


def render_page_html(
    *,
    title: str,
    content_markdown: str,
    output_path_html: str,
    nav_modules: Sequence[tuple[str, str, str]] = (),
    active_module_key: str = "",
) -> str:
    content_html = markdown_lib.markdown(content_markdown, extensions=list(_MARKDOWN_EXTENSIONS))
    content_html = _MERMAID_FENCE_PATTERN.sub(r'<pre class="mermaid">\1</pre>', content_html)
    content_html = _rewrite_internal_links_to_html(content_html)
    home_href = relative_output_link(from_output_path=output_path_html, to_output_path=HOME_OUTPUT_HTML)
    diagrams_href = relative_output_link(from_output_path=output_path_html, to_output_path=DIAGRAMS_INDEX_OUTPUT_HTML)
    mermaid_script_href = relative_output_link(
        from_output_path=output_path_html, to_output_path=MERMAID_ASSET_OUTPUT_PATH
    )
    ui_script_href = relative_output_link(from_output_path=output_path_html, to_output_path=WIKI_UI_JS_OUTPUT_PATH)
    ui_style_href = relative_output_link(from_output_path=output_path_html, to_output_path=WIKI_UI_CSS_OUTPUT_PATH)
    search_index_href = relative_output_link(
        from_output_path=output_path_html, to_output_path=SEARCH_INDEX_OUTPUT_PATH
    )
    # The persistent sidebar's module list (contracts/wiki-ui-shell.md) - every
    # page passes its own `output_path_html` so each link is relative to
    # wherever this particular page ends up on disk (diagram pages sit one
    # directory deeper than module pages, etc.), mirroring how home_href/
    # diagrams_href are already computed above.
    nav_entries = [
        {
            "name": name,
            "href": relative_output_link(from_output_path=output_path_html, to_output_path=module_html) or ".",
            "active": module_key == active_module_key,
        }
        for name, module_html, module_key in nav_modules
    ]
    return render_html_template(
        "layout.html.jinja",
        title=title,
        content_html=content_html,
        home_href=home_href or HOME_OUTPUT_HTML,
        diagrams_href=diagrams_href or DIAGRAMS_INDEX_OUTPUT_HTML,
        mermaid_script_href=mermaid_script_href,
        ui_script_href=ui_script_href,
        ui_style_href=ui_style_href,
        search_index_href=search_index_href,
        nav_modules=nav_entries,
        is_diagrams_page=output_path_html == DIAGRAMS_INDEX_OUTPUT_HTML,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )