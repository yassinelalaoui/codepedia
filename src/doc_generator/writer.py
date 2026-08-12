from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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
            linkedPageIds=tuple(dict.fromkeys(link.toPageId for link in page.links)),
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

    def remove_page(self, page_id: str) -> None:
        entry = self.manifestStore.load_entry(page_id)
        if entry is None:
            return
        for relative in (entry.outputPathMarkdown, entry.outputPathHtml):
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