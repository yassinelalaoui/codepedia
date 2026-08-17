from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

PageKind = Literal["home", "module", "diagram", "class-diagram"]


@dataclass(frozen=True, slots=True)
class PageLink:
    fromPageId: str
    toPageId: str
    label: str
    relativePath: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DocPage:
    id: str
    title: str
    contentMarkdown: str
    relatedSymbols: tuple[str, ...] = ()
    kind: PageKind = "module"
    sourceEntityId: str = ""
    contentSymbolIds: tuple[str, ...] = ()
    renderedHtml: str = ""
    outputPathMarkdown: str = ""
    outputPathHtml: str = ""
    links: tuple[PageLink, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "contentMarkdown": self.contentMarkdown,
            "relatedSymbols": list(self.relatedSymbols),
            "kind": self.kind,
            "sourceEntityId": self.sourceEntityId,
            "contentSymbolIds": list(self.contentSymbolIds),
            "renderedHtml": self.renderedHtml,
            "outputPathMarkdown": self.outputPathMarkdown,
            "outputPathHtml": self.outputPathHtml,
            "links": [link.to_dict() for link in self.links],
        }


@dataclass(frozen=True, slots=True)
class DocumentationSet:
    repositoryId: str
    outputRoot: str
    pages: tuple[DocPage, ...] = ()
    generatedAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "repositoryId": self.repositoryId,
            "outputRoot": self.outputRoot,
            "generatedAt": self.generatedAt,
            "pages": [page.to_dict() for page in self.pages],
        }


@dataclass(frozen=True, slots=True)
class PageManifestEntry:
    pageId: str
    kind: PageKind
    sourceSymbolIds: tuple[str, ...]
    contentHash: str
    outputPathMarkdown: str
    outputPathHtml: str
    lastGeneratedAt: str
    linkedPageIds: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "pageId": self.pageId,
            "kind": self.kind,
            "sourceSymbolIds": list(self.sourceSymbolIds),
            "contentHash": self.contentHash,
            "outputPathMarkdown": self.outputPathMarkdown,
            "outputPathHtml": self.outputPathHtml,
            "lastGeneratedAt": self.lastGeneratedAt,
            "linkedPageIds": list(self.linkedPageIds),
        }


EdgeId = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class RegenerationImpactSet:
    changedFileIds: tuple[str, ...] = ()
    changedSymbolIds: tuple[str, ...] = ()
    changedDependencyEdgeIds: tuple[EdgeId, ...] = ()
    impactedPageIds: tuple[str, ...] = ()
    removedPageIds: tuple[str, ...] = ()
    requiresHomePageRegeneration: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "changedFileIds": list(self.changedFileIds),
            "changedSymbolIds": list(self.changedSymbolIds),
            "changedDependencyEdgeIds": [list(edge) for edge in self.changedDependencyEdgeIds],
            "impactedPageIds": list(self.impactedPageIds),
            "removedPageIds": list(self.removedPageIds),
            "requiresHomePageRegeneration": self.requiresHomePageRegeneration,
        }