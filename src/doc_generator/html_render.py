from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any, Sequence

import markdown as markdown_lib
from repository_metadata.git_provenance import short_commit_sha

from .cross_references import SymbolLookup, SymbolReferenceExtension
from .html_sanitizer import SanitizeRawHtmlExtension
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


def _toc_label(token: dict[str, Any]) -> str:
    """Plain text for one rail entry.

    The `toc` extension leaves HTML entities in its `name` (a signature heading
    arrives as `f(x) -&gt; int`). The layout template autoescapes, so handing that
    over verbatim would double-escape it and print the entity itself.
    """
    return html.unescape(token.get("name", ""))


def _build_page_toc(toc_tokens: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten python-markdown's `toc_tokens` into this page's section rail.

    Only H2 and H3 are kept. H1 is the page title, already rendered as the page
    heading, and H4 is the per-method level, which would swamp the rail on a
    large module. The walk descends through levels above H2 because the `toc`
    extension nests tokens under the page's H1 rather than emitting H2 at the
    top level. Anchors are the extension's own heading ids - the same ids
    `attr_list` pins on symbol headings - so a rail link always resolves.
    """
    sections: list[dict[str, Any]] = []

    def walk(tokens: Sequence[dict[str, Any]]) -> None:
        for token in tokens:
            level = token.get("level")
            children = token.get("children") or ()
            if level == 2:
                sections.append(
                    {
                        "id": token.get("id", ""),
                        "name": _toc_label(token),
                        "children": [
                            {"id": child.get("id", ""), "name": _toc_label(child)}
                            for child in children
                            if child.get("level") == 3
                        ],
                    }
                )
            elif level is not None and level < 2:
                walk(children)

    walk(toc_tokens)
    return sections


# The sidebar's navigation tree, as `doc_generator` hands it over: every entry
# carries the target page's *own* output path, and `render_page_html` turns each
# into a link relative to whatever page is currently being rendered.
NavModule = tuple[str, str, str]  # (module name, its page's output_path_html, its stable key)
NavSection = tuple[str, str, str, Sequence[NavModule]]  # (title, output_path_html, key, modules)


def render_page_html(
    *,
    title: str,
    content_markdown: str,
    output_path_html: str,
    nav_sections: Sequence[NavSection] = (),
    active_module_key: str = "",
    active_section_key: str = "",
    symbol_lookup: SymbolLookup | None = None,
    current_file_path: str = "",
    commit_sha: str = "",
) -> str:
    # A fresh Markdown instance per page, rather than the module-level
    # convenience function, is what makes `toc_tokens` reachable. Building a
    # new one each call also keeps the `toc` extension's used-id set scoped to
    # one page, so a heading repeated on the next page never inherits a `_1`
    # dedup suffix from this one.
    # Always registered, whatever else this page enables: the Markdown reaching
    # here carries docstrings from the documented repository and LLM-written
    # summaries, and `layout.html.jinja` inserts the result with `| safe`.
    extensions: list[Any] = [*_MARKDOWN_EXTENSIONS, SanitizeRawHtmlExtension()]
    if symbol_lookup is not None:
        # Appended last so it registers after the built-ins; it only rewrites
        # inline <code> elements, leaving fenced blocks (Mermaid included)
        # untouched.
        extensions.append(
            SymbolReferenceExtension(
                lookup=symbol_lookup,
                output_path_html=output_path_html,
                current_file_path=current_file_path,
            )
        )
    md = markdown_lib.Markdown(extensions=extensions)
    content_html = md.convert(content_markdown)
    page_toc = _build_page_toc(getattr(md, "toc_tokens", ()))
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
    # The persistent sidebar's navigation tree (contracts/wiki-ui-shell.md) -
    # every page passes its own `output_path_html` so each link is relative to
    # wherever this particular page ends up on disk (diagram pages sit one
    # directory deeper than module pages, etc.), mirroring how home_href/
    # diagrams_href are already computed above.
    #
    # A section is marked `expanded` when the page being rendered belongs to it,
    # which the template turns into `<details open>`. Collapsing the rest keeps a
    # large repository's sidebar navigable, and `<details>` does it with no
    # JavaScript at all - the same degradation rule the section rail follows.
    nav_entries = []
    for section_title, section_html, section_key, modules in nav_sections:
        module_entries = [
            {
                "name": name,
                "href": relative_output_link(from_output_path=output_path_html, to_output_path=module_html) or ".",
                "active": module_key == active_module_key,
            }
            for name, module_html, module_key in modules
        ]
        nav_entries.append(
            {
                "title": section_title,
                "href": relative_output_link(from_output_path=output_path_html, to_output_path=section_html) or ".",
                "active": section_key == active_section_key,
                "expanded": section_key == active_section_key
                or any(entry["active"] for entry in module_entries),
                "modules": module_entries,
            }
        )
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
        nav_sections=nav_entries,
        page_toc=page_toc,
        is_diagrams_page=output_path_html == DIAGRAMS_INDEX_OUTPUT_HTML,
        generated_at=datetime.now(timezone.utc).isoformat(),
        # Empty whenever the commit is unknown (not a git checkout, unborn
        # branch); the template then omits the provenance entirely rather than
        # printing a blank one.
        commit_sha=commit_sha,
        commit_sha_short=short_commit_sha(commit_sha),
    )