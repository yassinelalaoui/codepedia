from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from dependency_graph import DependencyGraph, DiagramExport
from repository_metadata import ModuleSymbol, Repository, RepositoryMetadataStore
from repository_metadata.models import RepositoryBundle, SourceFileBundle
from repository_metadata.sqlite_store import stable_repository_id

from . import links
from .class_diagram import select_major_classes
from .cross_references import SymbolLookup, build_symbol_lookup
from .diagrams import build_module_diagram
from .entry_point_diagram import build_entry_point_call_sequence, build_method_class_index, identify_entry_points
from .html_render import render_page_html
from .impact import compute_regeneration_impact
from .manifest_store import DocPageManifestStore
from .markdown_render import render_markdown_template
from .mermaid_diagram import (
    ClassDiagramSource,
    build_class_diagram_mermaid_source,
    build_mermaid_source,
    build_section_diagram_mermaid_source,
    build_sequence_diagram_mermaid_source,
    build_use_case_diagram_mermaid_source,
)
from .models import DocPage, DocumentationSet, EdgeId, PageLink
from .prose import is_prose_file
from .search_index import SearchIndexDocument, build_search_index
from .section_narrator import SectionNarrator, apply_section_narrations
from .sections import Section, SectionSelection, build_sections
from .use_case_diagram import select_use_cases
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
        sectionNarrator: SectionNarrator | None = None,
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
        self.sectionNarrator = sectionNarrator
        self._bundle: RepositoryBundle | None = None
        self._bundle_by_module_id: dict[str, SourceFileBundle] = {}
        self._bundle_by_file_path: dict[str, SourceFileBundle] = {}
        self._search_index: SearchIndexDocument | None = None
        self._symbol_lookup: SymbolLookup | None = None
        self._sections: SectionSelection | None = None

    def generateOverviewPage(
        self,
        repository: Repository,
        *,
        classDiagramPage: DocPage | None = None,
        useCaseDiagramPage: DocPage | None = None,
        classDiagramSource: ClassDiagramSource | None = None,
    ) -> DocPage:
        bundle = self._ensure_bundle()
        modules = sorted((file_bundle.module for file_bundle in bundle.files), key=lambda module: module.name)
        architecture_summary = self._build_architecture_summary(bundle.files)
        selection = self._ensure_sections()

        page_links: list[PageLink] = []
        section_entries: list[dict[str, object]] = []
        for section in selection.sections:
            section_page_id, section_md, _section_html = self._section_identity(section)
            section_link = links.build_page_link(
                from_page_id=links.HOME_PAGE_ID,
                from_output_path_markdown=links.HOME_OUTPUT_MARKDOWN,
                to_page_id=section_page_id,
                to_output_path_markdown=section_md,
                label=section.title,
            )
            if section_link:
                page_links.append(section_link)
            section_entries.append({"section": section, "sectionLink": section_link})
        class_diagram_link: PageLink | None = None
        if classDiagramPage is not None:
            class_diagram_link = links.build_page_link(
                from_page_id=links.HOME_PAGE_ID,
                from_output_path_markdown=links.HOME_OUTPUT_MARKDOWN,
                to_page_id=classDiagramPage.id,
                to_output_path_markdown=classDiagramPage.outputPathMarkdown,
                label="Repository class diagram",
            )
            if class_diagram_link:
                page_links.append(class_diagram_link)

        use_case_diagram_link: PageLink | None = None
        if useCaseDiagramPage is not None:
            use_case_diagram_link = links.build_page_link(
                from_page_id=links.HOME_PAGE_ID,
                from_output_path_markdown=links.HOME_OUTPUT_MARKDOWN,
                to_page_id=useCaseDiagramPage.id,
                to_output_path_markdown=useCaseDiagramPage.outputPathMarkdown,
                label="Repository use-case diagram",
            )
            if use_case_diagram_link:
                page_links.append(use_case_diagram_link)

        module_entries = []
        for module in modules:
            module_key = module.sourceFileId
            slug = links.page_slug(module.name, module_key)
            module_md, _ = links.module_output_paths(slug)
            diagram_page_id, diagram_md, _ = self._dependency_diagram_identity(module)
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
                to_page_id=diagram_page_id,
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
            section_entries=section_entries,
            architecture_summary=architecture_summary,
            class_diagram_link=class_diagram_link,
            use_case_diagram_link=use_case_diagram_link,
            class_diagram_source=classDiagramSource,
        )
        html = self._render_page(
            title=title, content_markdown=content, output_path_html=links.HOME_OUTPUT_HTML, nav_sections=self._nav_sections(), symbol_lookup=self._symbol_lookup
        )

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

    def generateModulePage(
        self, moduleSymbol: ModuleSymbol, *, entryPointPages: dict[str, DocPage] | None = None
    ) -> DocPage:
        file_bundle = self._module_bundle(moduleSymbol)
        module_key = moduleSymbol.sourceFileId
        slug = links.page_slug(moduleSymbol.name, module_key)
        module_md, module_html = links.module_output_paths(slug)
        page_id = links.module_page_id(module_key)

        owning_section = self._ensure_sections().by_module_key().get(module_key)
        section_link: PageLink | None = None
        if owning_section is not None:
            owning_page_id, owning_md, _owning_html = self._section_identity(owning_section)
            section_link = links.build_page_link(
                from_page_id=page_id,
                from_output_path_markdown=module_md,
                to_page_id=owning_page_id,
                to_output_path_markdown=owning_md,
                label=owning_section.title,
            )

        related_modules = self._related_modules(moduleSymbol)
        related_links: list[PageLink] = []
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
                related_links.append(link)
        page_links: list[PageLink] = list(related_links)
        if section_link:
            page_links.append(section_link)

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

        entry_point_links: dict[str, PageLink] = {}
        own_function_ids = {function.id for function in file_bundle.functions} if file_bundle else set()
        for symbol_id in own_function_ids & (entryPointPages or {}).keys():
            entry_page = entryPointPages[symbol_id]
            entry_link = links.build_page_link(
                from_page_id=page_id,
                from_output_path_markdown=module_md,
                to_page_id=entry_page.id,
                to_output_path_markdown=entry_page.outputPathMarkdown,
                label="View call sequence",
            )
            if entry_link:
                entry_point_links[symbol_id] = entry_link
                page_links.append(entry_link)

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
            is_prose=is_prose_file(moduleSymbol.filePath),
            module=moduleSymbol,
            classes=classes,
            functions=functions,
            related_links=related_links,
            diagram_link=diagram_link,
            section_link=section_link,
            entry_point_links=entry_point_links,
        )
        html = self._render_page(
            title=moduleSymbol.name,
            content_markdown=content,
            output_path_html=module_html,
            nav_sections=self._nav_sections(), symbol_lookup=self._symbol_lookup,
            active_module_key=module_key,
            active_section_key=owning_section.key if owning_section else "",
            current_file_path=moduleSymbol.filePath,
        )

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

    def generateSectionPage(self, section: Section, *, sectionsByKey: Mapping[str, Section]) -> DocPage:
        """One page per section: what the area is, what it contains, how it hangs together.

        The page is assembled entirely from already-derived structure - the
        section's members, its internal import edges, and its neighbouring
        sections - so it costs no source re-parse and, narration aside, no model
        call.
        """
        page_id, section_md, section_html = self._section_identity(section)

        page_links: list[PageLink] = []
        member_entries: list[dict[str, object]] = []
        for member in section.members:
            slug = links.page_slug(member.name, member.moduleKey)
            module_md, _ = links.module_output_paths(slug)
            member_link = links.build_page_link(
                from_page_id=page_id,
                from_output_path_markdown=section_md,
                to_page_id=links.module_page_id(member.moduleKey),
                to_output_path_markdown=module_md,
                label=member.name,
            )
            if member_link:
                page_links.append(member_link)
            member_entries.append({"member": member, "moduleLink": member_link})

        neighbor_links: list[PageLink] = []
        for neighbor_key in section.neighborKeys:
            neighbor = sectionsByKey.get(neighbor_key)
            if neighbor is None:
                continue
            neighbor_page_id, neighbor_md, _ = self._section_identity(neighbor)
            neighbor_link = links.build_page_link(
                from_page_id=page_id,
                from_output_path_markdown=section_md,
                to_page_id=neighbor_page_id,
                to_output_path_markdown=neighbor_md,
                label=neighbor.title,
            )
            if neighbor_link:
                neighbor_links.append(neighbor_link)
                page_links.append(neighbor_link)

        section_diagram_source = build_section_diagram_mermaid_source(
            section, section_output_path_html=section_html
        )

        content = render_markdown_template(
            "section.md.jinja",
            section=section,
            member_entries=member_entries,
            neighbor_links=neighbor_links,
            section_diagram_source=section_diagram_source,
        )
        html = self._render_page(
            title=section.title,
            content_markdown=content,
            output_path_html=section_html,
            nav_sections=self._nav_sections(),
            active_section_key=section.key,
            symbol_lookup=self._symbol_lookup,
        )

        return DocPage(
            id=page_id,
            title=section.title,
            contentMarkdown=content,
            relatedSymbols=section.moduleKeys,
            kind="section",
            sourceEntityId=section.key,
            contentSymbolIds=section.moduleKeys,
            renderedHtml=html,
            outputPathMarkdown=section_md,
            outputPathHtml=section_html,
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
        html = self._render_page(
            title=title, content_markdown=content, output_path_html=diagram_html, nav_sections=self._nav_sections(), symbol_lookup=self._symbol_lookup
        )

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

    def _class_diagram_source(self) -> ClassDiagramSource | None:
        """The repository class diagram, or None when no class qualifies.

        Shared by the standalone diagram page and the overview page, which
        embeds the same diagram inline rather than only linking to it.
        """
        bundle = self._ensure_bundle()
        selection = select_major_classes(bundle, self.dependencyGraph)
        if not selection.includedClasses:
            return None
        return build_class_diagram_mermaid_source(selection)

    def generateClassDiagramPage(self) -> DocPage | None:
        class_diagram_source = self._class_diagram_source()
        if class_diagram_source is None:
            return None

        output_md, output_html = links.class_diagram_output_paths()
        page_id = links.class_diagram_page_id()
        title = "Repository Class Diagram"

        content = render_markdown_template(
            "class_diagram.md.jinja",
            class_diagram_source=class_diagram_source,
        )
        html = self._render_page(
            title=title, content_markdown=content, output_path_html=output_html, nav_sections=self._nav_sections(), symbol_lookup=self._symbol_lookup
        )

        return DocPage(
            id=page_id,
            title=title,
            contentMarkdown=content,
            relatedSymbols=class_diagram_source.includedClassIds,
            kind="class-diagram",
            sourceEntityId="",
            contentSymbolIds=class_diagram_source.includedClassIds,
            renderedHtml=html,
            outputPathMarkdown=output_md,
            outputPathHtml=output_html,
            links=(),
        )

    def generateUseCaseDiagramPage(self) -> DocPage | None:
        bundle = self._ensure_bundle()
        selection = select_use_cases(bundle, self.dependencyGraph)
        if not selection.useCases:
            return None

        use_case_diagram_source = build_use_case_diagram_mermaid_source(selection)
        output_md, output_html = links.use_case_diagram_output_paths()
        page_id = links.use_case_diagram_page_id()
        title = "Repository Use Case Diagram"

        content = render_markdown_template(
            "use_case_diagram.md.jinja",
            use_case_diagram_source=use_case_diagram_source,
        )
        html = self._render_page(
            title=title, content_markdown=content, output_path_html=output_html, nav_sections=self._nav_sections(), symbol_lookup=self._symbol_lookup
        )

        related_symbols = tuple(use_case.entryPointStableKey for use_case in selection.useCases)
        return DocPage(
            id=page_id,
            title=title,
            contentMarkdown=content,
            relatedSymbols=related_symbols,
            kind="use-case-diagram",
            sourceEntityId="",
            contentSymbolIds=related_symbols,
            renderedHtml=html,
            outputPathMarkdown=output_md,
            outputPathHtml=output_html,
            links=(),
        )

    def generateEntryPointSequenceDiagramPages(self) -> tuple[DocPage, ...]:
        bundle = self._ensure_bundle()
        entry_points = identify_entry_points(bundle, self.dependencyGraph)
        if not entry_points:
            return ()

        method_class_index = build_method_class_index(bundle)
        pages: list[DocPage] = []
        for entry_point in entry_points:
            selection = build_entry_point_call_sequence(
                self.dependencyGraph,
                entry_point,
                resolve_module=self._resolve_module_key_by_path,
                resolve_class_name=method_class_index.get,
            )
            sequence_diagram_source = build_sequence_diagram_mermaid_source(selection)

            slug = links.page_slug(entry_point.name, entry_point.stableKey)
            output_md, output_html = links.diagram_output_paths(slug)
            page_id = links.sequence_diagram_page_id(entry_point.stableKey)
            title = f"{entry_point.name} — Call sequence"

            content = render_markdown_template(
                "sequence_diagram.md.jinja",
                entry_point=entry_point,
                selection=selection,
                sequence_diagram_source=sequence_diagram_source,
            )
            html = self._render_page(
            title=title, content_markdown=content, output_path_html=output_html, nav_sections=self._nav_sections(), symbol_lookup=self._symbol_lookup
        )

            related_symbols = tuple(dict.fromkeys(step.calleeSymbolId for step in selection.steps))
            pages.append(
                DocPage(
                    id=page_id,
                    title=title,
                    contentMarkdown=content,
                    relatedSymbols=related_symbols,
                    kind="sequence-diagram",
                    sourceEntityId=entry_point.symbolId,
                    contentSymbolIds=(entry_point.symbolId, *related_symbols),
                    renderedHtml=html,
                    outputPathMarkdown=output_md,
                    outputPathHtml=output_html,
                    links=(),
                )
            )
        return tuple(pages)

    def generateDiagramsIndexPage(
        self,
        *,
        classDiagramPage: DocPage | None,
        useCaseDiagramPage: DocPage | None,
        entryPointPages: tuple[DocPage, ...],
        modules: tuple[ModuleSymbol, ...],
    ) -> DocPage:
        page_id = links.diagrams_index_page_id()
        output_md, output_html = links.diagrams_index_output_paths()
        title = "Diagrams"

        page_links: list[PageLink] = []

        class_diagram_link: PageLink | None = None
        if classDiagramPage is not None:
            class_diagram_link = links.build_page_link(
                from_page_id=page_id,
                from_output_path_markdown=output_md,
                to_page_id=classDiagramPage.id,
                to_output_path_markdown=classDiagramPage.outputPathMarkdown,
                label="Repository class diagram",
            )
            if class_diagram_link:
                page_links.append(class_diagram_link)

        use_case_diagram_link: PageLink | None = None
        if useCaseDiagramPage is not None:
            use_case_diagram_link = links.build_page_link(
                from_page_id=page_id,
                from_output_path_markdown=output_md,
                to_page_id=useCaseDiagramPage.id,
                to_output_path_markdown=useCaseDiagramPage.outputPathMarkdown,
                label="Repository use-case diagram",
            )
            if use_case_diagram_link:
                page_links.append(use_case_diagram_link)

        sequence_diagram_links: list[PageLink] = []
        for entry_point_page in entryPointPages:
            link = links.build_page_link(
                from_page_id=page_id,
                from_output_path_markdown=output_md,
                to_page_id=entry_point_page.id,
                to_output_path_markdown=entry_point_page.outputPathMarkdown,
                label=entry_point_page.title,
            )
            if link:
                sequence_diagram_links.append(link)
                page_links.append(link)

        dependency_diagram_links: list[PageLink] = []
        for module in sorted(modules, key=lambda module: module.name):
            diagram_page_id, diagram_md, _ = self._dependency_diagram_identity(module)
            link = links.build_page_link(
                from_page_id=page_id,
                from_output_path_markdown=output_md,
                to_page_id=diagram_page_id,
                to_output_path_markdown=diagram_md,
                label=f"{module.name} dependencies",
            )
            if link:
                dependency_diagram_links.append(link)
                page_links.append(link)

        content = render_markdown_template(
            "diagrams_index.md.jinja",
            class_diagram_link=class_diagram_link,
            use_case_diagram_link=use_case_diagram_link,
            sequence_diagram_links=sequence_diagram_links,
            dependency_diagram_links=dependency_diagram_links,
        )
        html = self._render_page(
            title=title, content_markdown=content, output_path_html=output_html, nav_sections=self._nav_sections(), symbol_lookup=self._symbol_lookup
        )

        return DocPage(
            id=page_id,
            title=title,
            contentMarkdown=content,
            relatedSymbols=(),
            kind="diagrams-index",
            sourceEntityId="",
            contentSymbolIds=(),
            renderedHtml=html,
            outputPathMarkdown=output_md,
            outputPathHtml=output_html,
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
        """Generate the wiki, under one manifest connection for the whole pass.

        `_writer.write_page` saves a manifest row per page, and the narrator
        reads and writes its cache per section. Each of those used to open the
        database, replay its schema, commit and close - once per page of the
        wiki.
        """
        with self.manifestStore.session():
            return self._generate_repository_documentation(
                repositoryRoot,
                incremental=incremental,
                changedPaths=changedPaths,
                changedSymbolIds=changedSymbolIds,
                changedDependencyEdgeIds=changedDependencyEdgeIds,
            )

    def _generate_repository_documentation(
        self,
        repositoryRoot: str | Path,
        *,
        incremental: bool,
        changedPaths: Iterable[str | Path],
        changedSymbolIds: Iterable[str],
        changedDependencyEdgeIds: Iterable[EdgeId],
    ) -> DocumentationSet:
        self.repositoryRoot = repositoryRoot
        self.repositoryId = stable_repository_id(repositoryRoot)
        self._writer.repositoryId = self.repositoryId
        self._bundle = None
        self._sections = None
        bundle = self._ensure_bundle()
        _ensure_output_root_is_separate(self.outputRoot, repository_root=Path(repositoryRoot), bundle=bundle)

        # Read before the narrator runs. `apply_section_narrations` saves each
        # section's new title over the old one in the same cache row, so after
        # `_ensure_sections` the previous names exist nowhere - and they are what
        # tells us whether every already-written page's sidebar went stale.
        previous_section_titles = self.manifestStore.list_section_titles(self.repositoryId)
        selection = self._ensure_sections()

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
                sections=selection.sections,
                previous_section_titles=previous_section_titles,
            )
            target_page_ids = set(impact.impactedPageIds)
            if impact.requiresHomePageRegeneration:
                target_page_ids.add(links.HOME_PAGE_ID)
            for removed_page_id in impact.removedPageIds:
                self._writer.remove_page(removed_page_id)
            if impact.requiresNavigationRegeneration:
                # The section/module tree is rendered into every page's sidebar,
                # so a change to its shape makes every already-written page stale
                # in a way no per-page impact set can express. Regenerating
                # everything is the only correct answer here - and it stays rare,
                # because the tree only reshapes when files are added, removed or
                # moved, not when their contents change.
                target_page_ids = None

        pages: list[DocPage] = []

        # Computed once per run regardless of which pages actually regenerate:
        # the home page needs to know whether a class-diagram page currently
        # exists to decide whether to link it, and this is a cheap in-memory
        # graph scan (not a source re-parse), per research.md Decision 3.
        class_diagram_page = self.generateClassDiagramPage()

        # Same reasoning: the home page needs to know whether a use-case-
        # diagram page currently exists to decide whether to link it.
        use_case_diagram_page = self.generateUseCaseDiagramPage()

        # Same reasoning: module pages need to know each of their functions'
        # sequence-diagram page identity/output path to link to it, even on an
        # incremental run where that particular sequence-diagram page itself
        # doesn't regenerate this run (entry-point membership is recomputed
        # fresh every run - research.md Decision 8).
        entry_point_pages = self.generateEntryPointSequenceDiagramPages()
        entry_point_pages_by_symbol = {page.sourceEntityId: page for page in entry_point_pages}

        # Always computed and always written when targeted (research.md
        # Decision 2 of 024): unlike the class/use-case diagram pages, the
        # diagrams-index page always exists once generated, so its nav link
        # (html_render.py) is never dangling.
        modules = sorted((file_bundle.module for file_bundle in bundle.files), key=lambda module: module.name)
        diagrams_index_page = self.generateDiagramsIndexPage(
            classDiagramPage=class_diagram_page,
            useCaseDiagramPage=use_case_diagram_page,
            entryPointPages=entry_point_pages,
            modules=tuple(modules),
        )

        if target_page_ids is None or links.HOME_PAGE_ID in target_page_ids:
            home_page = self.generateOverviewPage(
                bundle.repository,
                classDiagramPage=class_diagram_page,
                useCaseDiagramPage=use_case_diagram_page,
                classDiagramSource=self._class_diagram_source(),
            )
            self._writer.write_page(home_page)
            pages.append(home_page)

        class_diagram_page_id = links.class_diagram_page_id()
        if class_diagram_page is not None and (target_page_ids is None or class_diagram_page_id in target_page_ids):
            self._writer.write_page(class_diagram_page)
            pages.append(class_diagram_page)

        use_case_diagram_page_id = links.use_case_diagram_page_id()
        if use_case_diagram_page is not None and (
            target_page_ids is None or use_case_diagram_page_id in target_page_ids
        ):
            self._writer.write_page(use_case_diagram_page)
            pages.append(use_case_diagram_page)

        for entry_point_page in entry_point_pages:
            if target_page_ids is None or entry_point_page.id in target_page_ids:
                self._writer.write_page(entry_point_page)
                pages.append(entry_point_page)

        diagrams_index_page_id = links.diagrams_index_page_id()
        if target_page_ids is None or impact.requiresDiagramsIndexRegeneration or diagrams_index_page_id in target_page_ids:
            self._writer.write_page(diagrams_index_page)
            pages.append(diagrams_index_page)

        sections_by_key = {section.key: section for section in selection.sections}
        for section in selection.sections:
            section_page_id = links.section_page_id(section.key)
            if target_page_ids is None or section_page_id in target_page_ids:
                section_page = self.generateSectionPage(section, sectionsByKey=sections_by_key)
                self._writer.write_page(section_page)
                pages.append(section_page)

        for file_bundle in bundle.files:
            module = file_bundle.module
            module_key = module.sourceFileId
            module_page_id = links.module_page_id(module_key)
            diagram_page_id = links.diagram_page_id(module_key)

            if target_page_ids is None or module_page_id in target_page_ids:
                module_page = self.generateModulePage(module, entryPointPages=entry_point_pages_by_symbol)
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
            # Same reasoning for the wiki UI bundle (016 research.md Decision 8)
            # and the search index it and the chat panel both depend on.
            self._writer.ensure_wiki_ui_assets()
            self._writer.write_search_index(self._search_index or build_search_index(bundle))

        return DocumentationSet(repositoryId=self.repositoryId, outputRoot=str(self.outputRoot), pages=tuple(pages))

    def _nav_sections(self) -> list[tuple[str, str, str, list[tuple[str, str, str]]]]:
        """The persistent sidebar's navigation tree, present on every page.

        One entry per section - (title, its page's own output_path_html, its
        stable key, its member modules) - with each module carried as (name, its
        page's own output_path_html, its stable key). `render_page_html` turns
        every path into a link relative to whatever page is actually being
        rendered, so nothing here depends on where the current page sits on
        disk. Modules are grouped rather than listed flat, which is what makes
        the sidebar readable once a repository has more modules than fit on a
        screen.
        """
        selection = self._ensure_sections()
        entries: list[tuple[str, str, str, list[tuple[str, str, str]]]] = []
        for section in selection.sections:
            _page_id, _section_md, section_html = self._section_identity(section)
            modules = []
            for member in section.members:
                slug = links.page_slug(member.name, member.moduleKey)
                _, module_html = links.module_output_paths(slug)
                modules.append((member.name, module_html, member.moduleKey))
            entries.append((section.title, section_html, section.key, modules))
        return entries

    def _section_identity(self, section: Section) -> tuple[str, str, str]:
        """Return (page_id, output_path_markdown, output_path_html) for a section page.

        The slug is built from the section's *directory path*, never its title:
        a title can be rewritten by the narrator between runs, and keying the
        output file on it would orphan the previous file and break every link
        pointing at it. The directory path only moves when the code does.
        """
        slug = links.section_slug(section.directoryPath, section.key)
        section_md, section_html = links.section_output_paths(slug)
        return links.section_page_id(section.key), section_md, section_html

    def _ensure_sections(self) -> SectionSelection:
        """The repository's sections for this run, derived once and reused.

        Derivation is deterministic (`sections.build_sections`); the narrator
        only fills in each section's title and description, and is skipped
        entirely when no LLM engine was supplied. Both happen once per run, so
        every page rendered in a run shows the same sidebar.
        """
        if self._sections is None:
            bundle = self._ensure_bundle()
            selection = build_sections(bundle, self.dependencyGraph, repository_root=self.repositoryRoot)
            if self.sectionNarrator is not None:
                self.sectionNarrator.repositoryId = self.repositoryId
            self._sections = apply_section_narrations(selection, self.sectionNarrator)
        return self._sections

    def _render_page(self, **kwargs) -> str:
        """`render_page_html` with this run's provenance filled in.

        Every page kind goes through here so the commit a page describes is
        stamped once rather than at each of the eight call sites - and so a page
        kind added later inherits it without anyone remembering to.
        """
        kwargs.setdefault("commit_sha", self._commit_sha())
        return render_page_html(**kwargs)

    def _commit_sha(self) -> str:
        """HEAD as recorded for the pass these pages belong to.

        Read from the stored `Repository` rather than from `.git` directly: the
        wiki describes the commit it was *built from*, so a checkout that moved
        after the pass must not make already-generated pages claim the new one.
        Keeping the read here also means this class never touches the working
        tree.

        Under `serve` the recorded value is refreshed at the top of each
        incremental pass (`RepositoryMetadataStore.refresh_commit_sha`), so a
        watcher living across commits stamps the commit each page actually
        describes rather than the one the process started on. The bundle is
        re-loaded at the start of every `generateRepositoryDocumentation`, so
        this picks that up with no cache to invalidate.
        """
        try:
            return self._ensure_bundle().repository.commitSha
        except Exception:  # noqa: BLE001 - provenance is decoration, never a reason to fail a build
            return ""

    def _ensure_bundle(self) -> RepositoryBundle:
        if self._bundle is None:
            self._bundle = self.metadataStore.load_repository(self.repositoryRoot)
            self._bundle_by_module_id = {
                file_bundle.module.id: file_bundle for file_bundle in self._bundle.files
            }
            self._bundle_by_file_path = {
                _normalize_path(file_bundle.file.path): file_bundle for file_bundle in self._bundle.files
            }
            # Built here rather than at the end of the run: page rendering needs
            # it to resolve inline symbol mentions, and it is a pure function of
            # the bundle, so the same document is reused for the manifest write.
            self._search_index = build_search_index(self._bundle)
            self._symbol_lookup = build_symbol_lookup(self._search_index)
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

    def _dependency_diagram_identity(self, module: ModuleSymbol) -> tuple[str, str, str]:
        """Return (page_id, output_path_markdown, output_path_html) for a module's dependency-diagram page."""
        module_key = module.sourceFileId
        slug = links.page_slug(module.name, module_key)
        diagram_md, diagram_html = links.diagram_output_paths(slug)
        return links.diagram_page_id(module_key), diagram_md, diagram_html

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

    def _build_architecture_summary(self, files: tuple[SourceFileBundle, ...]) -> dict:
        class_count = sum(len(file_bundle.classes) for file_bundle in files)
        function_count = sum(len(self._documented_functions(file_bundle)) for file_bundle in files)

        groups: dict[str, int] = {}
        for file_bundle in files:
            group_name = Path(file_bundle.module.filePath).parent.name or "."
            groups[group_name] = groups.get(group_name, 0) + 1

        return {
            "moduleCount": len(files),
            "classCount": class_count,
            "functionCount": function_count,
            "groups": sorted(
                ({"name": name, "moduleCount": count} for name, count in groups.items()),
                key=lambda entry: entry["name"],
            ),
        }

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
