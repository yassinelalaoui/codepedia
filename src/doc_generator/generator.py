from __future__ import annotations

from pathlib import Path
from typing import Iterable

from dependency_graph import DependencyGraph, DiagramExport
from repository_metadata import ModuleSymbol, Repository, RepositoryMetadataStore
from repository_metadata.models import RepositoryBundle, SourceFileBundle
from repository_metadata.sqlite_store import stable_repository_id

from . import links
from .diagrams import build_module_diagram
from .html_render import render_page_html
from .impact import compute_regeneration_impact
from .manifest_store import DocPageManifestStore
from .markdown_render import render_markdown_template
from .mermaid_diagram import build_mermaid_source
from .models import DocPage, DocumentationSet, EdgeId, PageLink
from .writer import DocumentationWriter


class DocGenerator:
    """Assembles wiki-style documentation pages from repository metadata.

    Pages are identified by each module's ``sourceFileId`` rather than its
    ``ModuleSymbol.id``: the latter is a content hash over the whole file
    (including its line range) and shifts on every edit, which would make
    "the same module's page" look like a different page on every run and
    defeat incremental regeneration. ``sourceFileId`` is derived only from
    the repository id and file path, so it stays stable across edits and
    only changes when a file is actually moved or renamed.
    """

    def __init__(
        self,
        *,
        metadataStore: RepositoryMetadataStore,
        dependencyGraph: DependencyGraph,
        manifestStore: DocPageManifestStore,
        outputRoot: str | Path,
        repositoryRoot: str | Path,
    ) -> None:
        self.metadataStore = metadataStore
        self.dependencyGraph = dependencyGraph
        self.manifestStore = manifestStore
        self.outputRoot = Path(outputRoot)
        self.repositoryRoot = repositoryRoot
        self.repositoryId = stable_repository_id(repositoryRoot)
        self._writer = DocumentationWriter(
            outputRoot=self.outputRoot,
            manifestStore=manifestStore,
            repositoryId=self.repositoryId,
        )
        self._bundle: RepositoryBundle | None = None
        self._bundle_by_module_id: dict[str, SourceFileBundle] = {}
        self._bundle_by_file_path: dict[str, SourceFileBundle] = {}

    def generateOverviewPage(self, repository: Repository) -> DocPage:
        bundle = self._ensure_bundle()
        modules = sorted((file_bundle.module for file_bundle in bundle.files), key=lambda module: module.name)

        page_links: list[PageLink] = []
        module_entries = []
        for module in modules:
            module_key = module.sourceFileId
            slug = links.page_slug(module.name, module_key)
            module_md, _ = links.module_output_paths(slug)
            diagram_md, _ = links.diagram_output_paths(slug)
            module_link = links.build_page_link(
                from_page_id=links.HOME_PAGE_ID,
                from_output_path_markdown=links.HOME_OUTPUT_MARKDOWN,
                to_page_id=links.module_page_id(module_key),
                to_output_path_markdown=module_md,
                label=module.name,
            )
            diagram_link = links.build_page_link(
                from_page_id=links.HOME_PAGE_ID,
                from_output_path_markdown=links.HOME_OUTPUT_MARKDOWN,
                to_page_id=links.diagram_page_id(module_key),
                to_output_path_markdown=diagram_md,
                label=f"{module.name} dependencies",
            )
            if module_link:
                page_links.append(module_link)
            if diagram_link:
                page_links.append(diagram_link)
            module_entries.append({"module": module, "moduleLink": module_link, "diagramLink": diagram_link})

        repository_name = Path(repository.rootPath).name or repository.rootPath
        title = f"{repository_name} — Documentation"
        content = render_markdown_template(
            "home.md.jinja",
            repository=repository,
            repository_name=repository_name,
            module_entries=module_entries,
        )
        html = render_page_html(title=title, content_markdown=content, output_path_html=links.HOME_OUTPUT_HTML)

        return DocPage(
            id=links.HOME_PAGE_ID,
            title=title,
            contentMarkdown=content,
            relatedSymbols=tuple(module.id for module in modules),
            kind="home",
            sourceEntityId=repository.id,
            contentSymbolIds=tuple(module.sourceFileId for module in modules),
            renderedHtml=html,
            outputPathMarkdown=links.HOME_OUTPUT_MARKDOWN,
            outputPathHtml=links.HOME_OUTPUT_HTML,
            links=tuple(page_links),
        )

    def generateModulePage(self, moduleSymbol: ModuleSymbol) -> DocPage:
        file_bundle = self._module_bundle(moduleSymbol)
        module_key = moduleSymbol.sourceFileId
        slug = links.page_slug(moduleSymbol.name, module_key)
        module_md, module_html = links.module_output_paths(slug)
        page_id = links.module_page_id(module_key)

        related_modules = self._related_modules(moduleSymbol)
        page_links: list[PageLink] = []
        for related_key, related_name in related_modules:
            related_slug = links.page_slug(related_name, related_key)
            related_md, _ = links.module_output_paths(related_slug)
            link = links.build_page_link(
                from_page_id=page_id,
                from_output_path_markdown=module_md,
                to_page_id=links.module_page_id(related_key),
                to_output_path_markdown=related_md,
                label=related_name,
            )
            if link:
                page_links.append(link)

        diagram_md, _ = links.diagram_output_paths(slug)
        diagram_link = links.build_page_link(
            from_page_id=page_id,
            from_output_path_markdown=module_md,
            to_page_id=links.diagram_page_id(module_key),
            to_output_path_markdown=diagram_md,
            label=f"{moduleSymbol.name} dependency diagram",
        )
        if diagram_link:
            page_links.append(diagram_link)

        classes = self._classes_with_methods(file_bundle) if file_bundle else ()
        functions = self._documented_functions(file_bundle) if file_bundle else ()
        content_symbol_ids = (
            moduleSymbol.id,
            *(symbol.id for symbol, _methods in classes),
            *(method.id for _symbol, methods in classes for method in methods),
            *(symbol.id for symbol in functions),
        )

        content = render_markdown_template(
            "module.md.jinja",
            module=moduleSymbol,
            classes=classes,
            functions=functions,
            related_links=[link for link in page_links if link is not diagram_link],
            diagram_link=diagram_link,
        )
        html = render_page_html(title=moduleSymbol.name, content_markdown=content, output_path_html=module_html)

        return DocPage(
            id=page_id,
            title=moduleSymbol.name,
            contentMarkdown=content,
            relatedSymbols=tuple(related_key for related_key, _ in related_modules),
            kind="module",
            sourceEntityId=moduleSymbol.id,
            contentSymbolIds=content_symbol_ids,
            renderedHtml=html,
            outputPathMarkdown=module_md,
            outputPathHtml=module_html,
            links=tuple(page_links),
        )

    def generateDependencyDiagramPage(self, diagram: DiagramExport) -> DocPage:
        root_node = next((node for node in diagram.nodes if node.id == diagram.rootId), None)
        resolved_root = self._resolve_module_key_by_path(root_node.sourceFile if root_node else None)
        module_key = resolved_root[0] if resolved_root else diagram.rootId
        module_name = resolved_root[1] if resolved_root else (root_node.name if root_node else diagram.rootId)

        slug = links.page_slug(module_name, module_key)
        diagram_md, diagram_html = links.diagram_output_paths(slug)
        page_id = links.diagram_page_id(module_key)
        module_md, _ = links.module_output_paths(slug)

        page_links: list[PageLink] = []
        neighbor_keys: list[str] = []
        for node in diagram.nodes:
            if node.id == diagram.rootId or node.kind != "file":
                continue
            resolved_neighbor = self._resolve_module_key_by_path(node.sourceFile)
            if not resolved_neighbor:
                continue
            neighbor_key, neighbor_name = resolved_neighbor
            neighbor_keys.append(neighbor_key)
            neighbor_slug = links.page_slug(neighbor_name, neighbor_key)
            neighbor_md, _ = links.module_output_paths(neighbor_slug)
            link = links.build_page_link(
                from_page_id=page_id,
                from_output_path_markdown=diagram_md,
                to_page_id=links.module_page_id(neighbor_key),
                to_output_path_markdown=neighbor_md,
                label=node.name,
            )
            if link:
                page_links.append(link)

        owner_link = links.build_page_link(
            from_page_id=page_id,
            from_output_path_markdown=diagram_md,
            to_page_id=links.module_page_id(module_key),
            to_output_path_markdown=module_md,
            label=module_name,
        )
        if owner_link:
            page_links.append(owner_link)

        mermaid_source = build_mermaid_source(
            diagram,
            diagram_page_id=page_id,
            diagram_output_path_html=diagram_html,
            resolve_module=self._resolve_module_key_by_path,
        )

        title = f"{module_name} — Dependency diagram"
        content = render_markdown_template(
            "diagram.md.jinja",
            module_name=module_name,
            diagram=diagram,
            owner_link=owner_link,
            neighbor_links=[link for link in page_links if link is not owner_link],
            mermaid_source=mermaid_source.sourceText,
        )
        html = render_page_html(title=title, content_markdown=content, output_path_html=diagram_html)

        related_symbols = tuple(dict.fromkeys(neighbor_keys))
        return DocPage(
            id=page_id,
            title=title,
            contentMarkdown=content,
            relatedSymbols=related_symbols,
            kind="diagram",
            sourceEntityId=module_key,
            contentSymbolIds=(module_key, *related_symbols),
            renderedHtml=html,
            outputPathMarkdown=diagram_md,
            outputPathHtml=diagram_html,
            links=tuple(page_links),
        )

    def generateRepositoryDocumentation(
        self,
        repositoryRoot: str | Path,
        *,
        incremental: bool = True,
        changedPaths: Iterable[str | Path] = (),
        changedSymbolIds: Iterable[str] = (),
        changedDependencyEdgeIds: Iterable[EdgeId] = (),
    ) -> DocumentationSet:
        self.repositoryRoot = repositoryRoot
        self.repositoryId = stable_repository_id(repositoryRoot)
        self._writer.repositoryId = self.repositoryId
        self._bundle = None
        bundle = self._ensure_bundle()
        _ensure_output_root_is_separate(self.outputRoot, repository_root=Path(repositoryRoot), bundle=bundle)

        previous_entries = self.manifestStore.list_entries(self.repositoryId)
        run_incremental = incremental and len(previous_entries) > 0

        target_page_ids: set[str] | None = None
        if run_incremental:
            impact = compute_regeneration_impact(
                bundle=bundle,
                dependency_graph=self.dependencyGraph,
                previous_entries=previous_entries,
                changed_paths=changedPaths,
                changed_symbol_ids=changedSymbolIds,
                changed_dependency_edge_ids=changedDependencyEdgeIds,
            )
            target_page_ids = set(impact.impactedPageIds)
            if impact.requiresHomePageRegeneration:
                target_page_ids.add(links.HOME_PAGE_ID)
            for removed_page_id in impact.removedPageIds:
                self._writer.remove_page(removed_page_id)

        pages: list[DocPage] = []

        if target_page_ids is None or links.HOME_PAGE_ID in target_page_ids:
            home_page = self.generateOverviewPage(bundle.repository)
            self._writer.write_page(home_page)
            pages.append(home_page)

        for file_bundle in bundle.files:
            module = file_bundle.module
            module_key = module.sourceFileId
            module_page_id = links.module_page_id(module_key)
            diagram_page_id = links.diagram_page_id(module_key)

            if target_page_ids is None or module_page_id in target_page_ids:
                module_page = self.generateModulePage(module)
                self._writer.write_page(module_page)
                pages.append(module_page)

            if target_page_ids is None or diagram_page_id in target_page_ids:
                diagram = build_module_diagram(self.dependencyGraph, module)
                diagram_page = self.generateDependencyDiagramPage(diagram)
                self._writer.write_page(diagram_page)
                pages.append(diagram_page)

        if pages:
            # Every page's shared HTML layout references the vendored Mermaid
            # script (research.md Decision 7), not just diagram pages, so the
            # asset must be ensured whenever any page is written this run.
            self._writer.ensure_mermaid_asset()

        return DocumentationSet(repositoryId=self.repositoryId, outputRoot=str(self.outputRoot), pages=tuple(pages))

    def _ensure_bundle(self) -> RepositoryBundle:
        if self._bundle is None:
            self._bundle = self.metadataStore.load_repository(self.repositoryRoot)
            self._bundle_by_module_id = {
                file_bundle.module.id: file_bundle for file_bundle in self._bundle.files
            }
            self._bundle_by_file_path = {
                _normalize_path(file_bundle.file.path): file_bundle for file_bundle in self._bundle.files
            }
        return self._bundle

    def _module_bundle(self, moduleSymbol: ModuleSymbol) -> SourceFileBundle | None:
        self._ensure_bundle()
        return self._bundle_by_module_id.get(moduleSymbol.id)

    def _resolve_module_key_by_path(self, file_path: str | None) -> tuple[str, str] | None:
        """Resolve a dependency-graph node's file path to the owning module's stable key/name.

        Resolving by path (always fresh on the node) rather than the node's cached
        ``metadata["moduleId"]`` avoids staleness: an already-known file node's metadata
        is not refreshed when the graph re-ingests an updated inventory for that file.
        """
        if not file_path:
            return None
        self._ensure_bundle()
        file_bundle = self._bundle_by_file_path.get(_normalize_path(file_path))
        return (file_bundle.module.sourceFileId, file_bundle.module.name) if file_bundle else None

    def _related_modules(self, moduleSymbol: ModuleSymbol) -> list[tuple[str, str]]:
        neighbors = self.dependencyGraph.dependencies(
            moduleSymbol.filePath, relation_type="import"
        ) + self.dependencyGraph.dependents(moduleSymbol.filePath, relation_type="import")
        related: dict[str, str] = {}
        for node in neighbors:
            if node.kind != "file":
                continue
            resolved = self._resolve_module_key_by_path(node.sourceFile)
            if not resolved or resolved[0] == moduleSymbol.sourceFileId:
                continue
            related_key, related_name = resolved
            related[related_key] = related_name
        return sorted(related.items(), key=lambda item: item[1])

    def _classes_with_methods(self, file_bundle: SourceFileBundle) -> list[tuple[object, tuple]]:
        functions_by_id = {function.id: function for function in file_bundle.functions}
        return [
            (class_symbol, tuple(functions_by_id[method_id] for method_id in class_symbol.methods if method_id in functions_by_id))
            for class_symbol in file_bundle.classes
        ]

    def _documented_functions(self, file_bundle: SourceFileBundle) -> list:
        nested_ids = {nested_id for function in file_bundle.functions for nested_id in function.nestedSymbols}
        return [
            function
            for function in file_bundle.functions
            if function.owner == "module" and function.id not in nested_ids
        ]


def _normalize_path(path: str) -> str:
    return Path(path).as_posix().replace("\\", "/")


def _ensure_output_root_is_separate(output_root: Path, *, repository_root: Path, bundle: RepositoryBundle) -> None:
    resolved_output = output_root.resolve()
    resolved_repo_root = repository_root.resolve()
    if resolved_output == resolved_repo_root:
        raise ValueError("documentation outputRoot must not be the analyzed repository root itself")
    for file_bundle in bundle.files:
        source_path = Path(file_bundle.file.path)
        if not source_path.is_absolute():
            source_path = resolved_repo_root / source_path
        resolved_source = source_path.resolve()
        if resolved_source == resolved_output or resolved_output in resolved_source.parents:
            raise ValueError(f"documentation outputRoot overlaps an analyzed source path: {file_bundle.file.path}")
        if resolved_source.is_relative_to(resolved_output):
            raise ValueError(f"documentation outputRoot contains an analyzed source file: {file_bundle.file.path}")
