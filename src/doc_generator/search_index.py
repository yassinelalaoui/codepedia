from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repository_metadata.models import RepositoryBundle, SourceFileBundle

from . import links
from .prose import display_label, is_prose_file


@dataclass(frozen=True, slots=True)
class SearchIndexEntry:
    name: str
    kind: str
    symbolId: str
    filePath: str
    pageUrl: str
    #: The wiki page this entry lives on. Not serialized - the browser has the
    #: URL and needs nothing else - but `cross_references` reports it back to
    #: the generator so a page that links here is regenerated when this one is
    #: removed.
    pageId: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "symbolId": self.symbolId,
            "filePath": self.filePath,
            "pageUrl": self.pageUrl,
        }


@dataclass(frozen=True, slots=True)
class SearchIndexDocument:
    generatedAt: str
    entries: tuple[SearchIndexEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generatedAt": self.generatedAt,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def build_search_index(bundle: RepositoryBundle, repository_root: str | Path | None = None) -> SearchIndexDocument:
    entries: list[SearchIndexEntry] = []
    root = repository_root if repository_root is not None else bundle.repository.rootPath
    for file_bundle in bundle.files:
        entries.extend(_entries_for_file(file_bundle, root))
    entries.sort(key=lambda entry: (entry.name.lower(), entry.symbolId))
    return SearchIndexDocument(generatedAt=datetime.now(timezone.utc).isoformat(), entries=tuple(entries))


def _entries_for_file(file_bundle: SourceFileBundle, repository_root: str | Path) -> list[SearchIndexEntry]:
    module = file_bundle.module
    module_key = module.sourceFileId
    slug = links.page_slug(module.name, module_key)
    _, module_html = links.module_output_paths(slug)
    module_page_id = links.module_page_id(module_key)
    # The same table the module template writes its headings from, so a
    # `pageUrl` here can never name a fragment the page does not carry.
    anchors = links.build_symbol_anchors(file_bundle)
    # Documentation reuses the class/function symbol types so it can reuse the
    # whole pipeline, but the search box and the chat's citations print `kind`
    # verbatim - so a README heading published as "class" is a wrong answer
    # shown to a reader, not an internal detail.
    prose = is_prose_file(module.filePath)
    module_kind = "document" if prose else "module"
    class_kind = "section" if prose else "class"
    method_kind = "section" if prose else "method"
    function_kind = "section" if prose else "function"

    entries = [
        SearchIndexEntry(
            name=display_label(module.name, module.filePath, repository_root),
            kind=module_kind,
            symbolId=module_key,
            filePath=module.filePath,
            pageUrl=module_html,
            pageId=module_page_id,
        )
    ]

    functions_by_id = {function.id: function for function in file_bundle.functions}
    for class_symbol in file_bundle.classes:
        entries.append(
            SearchIndexEntry(
                name=class_symbol.name,
                kind=class_kind,
                symbolId=class_symbol.id,
                filePath=module.filePath,
                pageUrl=f"{module_html}#{anchors[class_symbol.id]}",
                pageId=module_page_id,
            )
        )
        for method_id in class_symbol.methods:
            method = functions_by_id.get(method_id)
            if method is None:
                continue
            entries.append(
                SearchIndexEntry(
                    name=f"{class_symbol.name}.{method.name}" if not prose else f"{class_symbol.name} › {method.name}",
                    kind=method_kind,
                    symbolId=method.id,
                    filePath=module.filePath,
                    pageUrl=f"{module_html}#{anchors[method.id]}",
                    pageId=module_page_id,
                )
            )

    nested_ids = {nested_id for function in file_bundle.functions for nested_id in function.nestedSymbols}
    for function in file_bundle.functions:
        if function.owner != "module" or function.id in nested_ids:
            continue
        entries.append(
            SearchIndexEntry(
                name=function.name,
                kind=function_kind,
                symbolId=function.id,
                filePath=module.filePath,
                pageUrl=f"{module_html}#{anchors[function.id]}",
                pageId=module_page_id,
            )
        )

    return entries
