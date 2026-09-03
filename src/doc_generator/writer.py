from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .links import relative_output_link
from .manifest_store import DocPageManifestStore
from .models import DocPage, PageManifestEntry
from .search_index import SearchIndexDocument


class OutputRootEscapeError(ValueError):
    pass


MERMAID_ASSET_SOURCE_PATH = Path(__file__).resolve().parent / "assets" / "mermaid.min.js"
MERMAID_ASSET_OUTPUT_PATH = "assets/mermaid.min.js"

WIKI_UI_JS_SOURCE_PATH = Path(__file__).resolve().parent / "assets" / "wiki-ui.js"
WIKI_UI_JS_OUTPUT_PATH = "assets/wiki-ui.js"
WIKI_UI_CSS_SOURCE_PATH = Path(__file__).resolve().parent / "assets" / "wiki-ui.css"
WIKI_UI_CSS_OUTPUT_PATH = "assets/wiki-ui.css"
SEARCH_INDEX_OUTPUT_PATH = "assets/search-index.json"


@dataclass(slots=True)
class DocumentationWriter:
    outputRoot: Path
    manifestStore: DocPageManifestStore
    repositoryId: str

    def __post_init__(self) -> None:
        self.outputRoot = Path(self.outputRoot).resolve()
        self.outputRoot.mkdir(parents=True, exist_ok=True)

    def write_page(self, page: DocPage) -> DocPage:
        markdown_path = self._resolve_managed_path(page.outputPathMarkdown)
        html_path = self._resolve_managed_path(page.outputPathHtml)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(page.contentMarkdown, encoding="utf-8")
        html_path.write_text(page.renderedHtml, encoding="utf-8")

        source_symbol_ids = tuple(
            dict.fromkeys(
                (*page.contentSymbolIds, *page.relatedSymbols, *((page.sourceEntityId,) if page.sourceEntityId else ()))
            )
        )
        entry = PageManifestEntry(
            pageId=page.id,
            kind=page.kind,
            sourceSymbolIds=source_symbol_ids,
            contentHash=_content_hash(page.contentMarkdown),
            outputPathMarkdown=page.outputPathMarkdown,
            outputPathHtml=page.outputPathHtml,
            lastGeneratedAt=datetime.now(timezone.utc).isoformat(),
            # Both kinds of outgoing link: the ones the generator built, and
            # the ones the markdown treeprocessor resolved out of an inline
            # symbol mention. A page removed from under either one has to
            # regenerate whoever pointed at it (`impact._add_referrers_of`).
            linkedPageIds=tuple(
                dict.fromkeys((*(link.toPageId for link in page.links), *page.referencedPageIds))
            ),
        )
        self.manifestStore.save_entry(self.repositoryId, entry)
        return page

    def ensure_mermaid_asset(self) -> Path:
        destination = self._resolve_managed_path(MERMAID_ASSET_OUTPUT_PATH)
        source_bytes = MERMAID_ASSET_SOURCE_PATH.read_bytes()
        if destination.exists() and destination.read_bytes() == source_bytes:
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_bytes)
        return destination

    def ensure_wiki_ui_assets(self) -> tuple[Path, Path]:
        js_destination = self._copy_if_changed(WIKI_UI_JS_SOURCE_PATH, WIKI_UI_JS_OUTPUT_PATH)
        css_destination = self._copy_if_changed(WIKI_UI_CSS_SOURCE_PATH, WIKI_UI_CSS_OUTPUT_PATH)
        return js_destination, css_destination

    def _copy_if_changed(self, source_path: Path, output_relative: str) -> Path:
        destination = self._resolve_managed_path(output_relative)
        source_bytes = source_path.read_bytes()
        if destination.exists() and destination.read_bytes() == source_bytes:
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_bytes)
        return destination

    def write_search_index(self, document: SearchIndexDocument) -> Path:
        destination = self._resolve_managed_path(SEARCH_INDEX_OUTPUT_PATH)
        new_entries = [entry.to_dict() for entry in document.entries]
        if destination.exists():
            try:
                existing = json.loads(destination.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                existing = None
            if existing is not None and existing.get("entries") == new_entries:
                return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(document.to_dict(), indent=2), encoding="utf-8")
        return destination

    def write_redirect_stub(
        self, *, old_paths: tuple[str, str], new_paths: tuple[str, str], title: str
    ) -> tuple[Path, Path]:
        """Leave something useful at an address that has moved.

        Both halves matter. The `<meta http-equiv="refresh">` does the work for
        most readers; the visible link is what a reader gets when the refresh is
        blocked - by a browser setting, or by a viewer that renders the HTML
        without executing it - and it is also the only part that tells them
        *where* they were sent, which is a requirement rather than a nicety.

        The target is a relative path, so the stub works over `file://` and makes
        no network request of any kind (constitution 2.2).
        """
        old_markdown, old_html = old_paths
        new_markdown, new_html = new_paths

        html_target = relative_output_link(from_output_path=old_html, to_output_path=new_html)
        markdown_target = relative_output_link(
            from_output_path=old_markdown, to_output_path=new_markdown
        )
        safe_title = html.escape(title)

        html_path = self._resolve_managed_path(old_html)
        markdown_path = self._resolve_managed_path(old_markdown)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)

        html_path.write_text(
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '  <meta charset="utf-8">\n'
            f'  <meta http-equiv="refresh" content="0; url={html.escape(html_target)}">\n'
            f'  <link rel="canonical" href="{html.escape(html_target)}">\n'
            f"  <title>Moved to {safe_title}</title>\n"
            "</head>\n"
            "<body>\n"
            f'  <p>This page has moved to <a href="{html.escape(html_target)}">{safe_title}</a>.</p>\n'
            "</body>\n"
            "</html>\n",
            encoding="utf-8",
        )
        markdown_path.write_text(
            f"This page has moved to [{title}]({markdown_target}).\n", encoding="utf-8"
        )
        return markdown_path, html_path

    def remove_page(self, page_id: str) -> None:
        """Delete a page that no longer exists - unless it is now a redirect.

        The alias check is not defensive. A feature's page id is its anchor
        module's key, and an anchor moves whenever the most internally connected
        member changes - measured, six of eleven groups on this repository are
        one import edge away from that. So "the anchor moved, then an incremental
        run computed removals" is the ordinary sequence, and without this guard
        that run unlinks the exact file the freshly written redirect points at,
        turning the alias table into a record of broken links.

        The guard lives here rather than in the generator's removal loop so that
        every caller of `remove_page` inherits it, including any added later.
        """
        entry = self.manifestStore.load_entry(page_id)
        if entry is None:
            return
        aliased_paths = self.manifestStore.aliased_output_paths(self.repositoryId)
        for relative in (entry.outputPathMarkdown, entry.outputPathHtml):
            if relative in aliased_paths:
                continue
            path = self._resolve_managed_path(relative)
            if path.exists():
                path.unlink()
        self.manifestStore.delete_entry(page_id)

    def _resolve_managed_path(self, relative: str) -> Path:
        candidate = (self.outputRoot / relative).resolve()
        if candidate != self.outputRoot and self.outputRoot not in candidate.parents:
            raise OutputRootEscapeError(f"refusing to write outside outputRoot: {relative!r}")
        return candidate


def _content_hash(content_markdown: str) -> str:
    return hashlib.sha1(content_markdown.encode("utf-8")).hexdigest()