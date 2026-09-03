from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

PageKind = Literal[
    "home",
    "module",
    "feature",
    "diagram",
    "class-diagram",
    "sequence-diagram",
    "use-case-diagram",
    "diagrams-index",
]


@dataclass(frozen=True, slots=True)
class PageLink:
    fromPageId: str
    toPageId: str
    label: str
    relativePath: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PageAlias:
    """An address this wiki once published, and where it now leads.

    Recorded whenever a page's identity moves under a reader's feet - most often
    a feature whose anchor module changed. The old files stay on disk as
    redirect stubs, which is why `DocumentationWriter.remove_page` has to consult
    these before unlinking: without that, the first incremental run after a move
    deletes the very file the redirect points at.
    """

    oldPageId: str
    newPageId: str
    oldOutputPathMarkdown: str = ""
    oldOutputPathHtml: str = ""
    recordedAt: str = ""

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
    #: Pages this one links to through an inline symbol mention resolved while
    #: rendering, as opposed to `links`, which the generator builds itself.
    #: Both feed `PageManifestEntry.linkedPageIds`; only together do they
    #: describe every outgoing link the page actually carries.
    referencedPageIds: tuple[str, ...] = ()

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
            "referencedPageIds": list(self.referencedPageIds),
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
    requiresDiagramsIndexRegeneration: bool = False
    # The sidebar's section/module tree is rendered into *every* page, so a
    # change to its shape leaves every already-written page showing stale
    # navigation. Unlike the flags above, this one is not a request to
    # regenerate one more page - it invalidates the whole set.
    requiresNavigationRegeneration: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "changedFileIds": list(self.changedFileIds),
            "changedSymbolIds": list(self.changedSymbolIds),
            "changedDependencyEdgeIds": [list(edge) for edge in self.changedDependencyEdgeIds],
            "impactedPageIds": list(self.impactedPageIds),
            "removedPageIds": list(self.removedPageIds),
            "requiresHomePageRegeneration": self.requiresHomePageRegeneration,
            "requiresDiagramsIndexRegeneration": self.requiresDiagramsIndexRegeneration,
            "requiresNavigationRegeneration": self.requiresNavigationRegeneration,
        }