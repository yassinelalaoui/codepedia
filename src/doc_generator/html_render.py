from __future__ import annotations

import hashlib
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
    FAVICON_OUTPUT_PATH,
    MERMAID_ASSET_OUTPUT_PATH,
    SEARCH_INDEX_OUTPUT_PATH,
    WIKI_UI_CSS_OUTPUT_PATH,
    WIKI_UI_JS_OUTPUT_PATH,
)

_MARKDOWN_EXTENSIONS = ("tables", "fenced_code", "toc", "attr_list")


def wiki_id(repository_id: str) -> str:
    """A short, stable id for one generated wiki (036 data-model.md, WikiIdentity).

    The theme preference is stored per wiki, and that is only possible because
    of this value. Chrome reports `location.origin` as `file://` for *every*
    local document regardless of directory, so every wiki opened from the
    filesystem shares one `localStorage` (measured - 036 research.md §2). An
    unscoped key would let any two wikis silently overwrite each other's theme,
    which is spec FR-007's explicit prohibition.

    Hashed rather than used raw: `repositoryId` is `repo::/abs/posix/path`, and
    embedding an absolute filesystem path into every page would leak the
    author's directory layout into an artifact meant to be shared. Same
    construction as `cli.paths.state_id`, kept separate only because
    `doc_generator` does not depend on `cli`.

    Derived from the repository id rather than the output location, so moving or
    renaming a generated wiki does not reset the reader's theme.
    """
    return hashlib.sha256(repository_id.encode("utf-8")).hexdigest()[:16]

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


# The sidebar's navigation list, as `doc_generator` hands it over: every entry
# carries the target page's *own* output path, and `render_page_html` turns each
# into a link relative to whatever page is currently being rendered.
#
# Flat, and with no members. The sidebar used to render a section/module tree;
# it now lists features only, which is what lets it stay readable on a
# repository with more modules than fit on a screen. A module's doors are its
# feature page, which lists every member without truncation, and the search
# index, which carries one entry per module.
NavFeature = tuple[str, str, str]  # (title, its page's output_path_html, its stable key)


def render_page_html(
    *,
    title: str,
    content_markdown: str,
    output_path_html: str,
    nav_features: Sequence[NavFeature] = (),
    active_feature_key: str = "",
    symbol_lookup: SymbolLookup | None = None,
    current_file_path: str = "",
    commit_sha: str = "",
    repository_id: str = "",
    reference_sink: set[str] | None = None,
) -> str:
    # `reference_sink` is an out-parameter rather than a second return value:
    # every one of the eight call sites reads `html = render_page_html(...)`,
    # and only the pages that record links care about the answer.
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
                reference_sink=reference_sink,
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
    # Page-relative like every other asset href above, so the tab icon still
    # resolves from a diagram page one directory deeper (036 spec FR-016). The
    # .ico is copied into the wiki's own assets/ rather than referenced from
    # docs/brand/, so a wiki moved away from this repository keeps its icon
    # (FR-020, FR-021).
    favicon_href = relative_output_link(
        from_output_path=output_path_html, to_output_path=FAVICON_OUTPUT_PATH
    )
    # The persistent sidebar's navigation list (contracts/wiki-ui-shell.md) -
    # every page passes its own `output_path_html` so each link is relative to
    # wherever this particular page ends up on disk (diagram pages sit one
    # directory deeper than module pages, etc.), mirroring how home_href/
    # diagrams_href are already computed above.
    nav_entries = [
        {
            "title": feature_title,
            "href": relative_output_link(from_output_path=output_path_html, to_output_path=feature_html) or ".",
            "active": feature_key == active_feature_key,
        }
        for feature_title, feature_html, feature_key in nav_features
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
        favicon_href=favicon_href,
        # Scopes the reader's stored theme to this wiki (036 contracts/
        # wiki-theme-shell.md §1). Read by the pre-paint script in <head>.
        wiki_id=wiki_id(repository_id),
        nav_features=nav_entries,
        page_toc=page_toc,
        is_diagrams_page=output_path_html == DIAGRAMS_INDEX_OUTPUT_HTML,
        generated_at=datetime.now(timezone.utc).isoformat(),
        # Empty whenever the commit is unknown (not a git checkout, unborn
        # branch); the template then omits the provenance entirely rather than
        # printing a blank one.
        commit_sha=commit_sha,
        commit_sha_short=short_commit_sha(commit_sha),
    )