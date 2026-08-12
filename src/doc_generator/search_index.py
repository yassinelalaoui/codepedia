from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from repository_metadata.models import RepositoryBundle, SourceFileBundle

from . import links


@dataclass(frozen=True, slots=True)
class SearchIndexEntry:
    name: str
    kind: str
    symbolId: str
    filePath: str
    pageUrl: str

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


def build_search_index(bundle: RepositoryBundle) -> SearchIndexDocument:
    entries: list[SearchIndexEntry] = []
    for file_bundle in bundle.files:
        entries.extend(_entries_for_file(file_bundle))
    entries.sort(key=lambda entry: (entry.name.lower(), entry.symbolId))
    return SearchIndexDocument(generatedAt=datetime.now(timezone.utc).isoformat(), entries=tuple(entries))


def _entries_for_file(file_bundle: SourceFileBundle) -> list[SearchIndexEntry]:
    module = file_bundle.module
    module_key = module.sourceFileId
    slug = links.page_slug(module.name, module_key)
    _, module_html = links.module_output_paths(slug)

    entries = [
        SearchIndexEntry(
            name=module.name,
            kind="module",
            symbolId=module_key,
            filePath=module.filePath,
            pageUrl=module_html,
        )
    ]

    functions_by_id = {function.id: function for function in file_bundle.functions}
    for class_symbol in file_bundle.classes:
        entries.append(
            SearchIndexEntry(
                name=class_symbol.name,
                kind="class",
                symbolId=class_symbol.id,
                filePath=module.filePath,
                pageUrl=f"{module_html}#{class_symbol.id}",
            )
        )
        for method_id in class_symbol.methods:
            method = functions_by_id.get(method_id)
            if method is None:
                continue
            entries.append(
                SearchIndexEntry(
                    name=f"{class_symbol.name}.{method.name}",
                    kind="method",
                    symbolId=method.id,
                    filePath=module.filePath,
                    pageUrl=f"{module_html}#{method.id}",
                )
            )

    nested_ids = {nested_id for function in file_bundle.functions for nested_id in function.nestedSymbols}
    for function in file_bundle.functions:
        if function.owner != "module" or function.id in nested_ids:
            continue
        entries.append(
            SearchIndexEntry(
                name=function.name,
                kind="function",
                symbolId=function.id,
                filePath=module.filePath,
                pageUrl=f"{module_html}#{function.id}",
            )
        )

    return entries
