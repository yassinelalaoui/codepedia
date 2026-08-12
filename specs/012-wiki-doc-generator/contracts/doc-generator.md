# Documentation Generator Contract

## Purpose

Define the public local-only generator used to assemble, render, and write
the wiki-style documentation pages for an indexed repository, and to
regenerate only the pages impacted by an incremental re-index.

## Core type

### `DocGenerator`

Constructor inputs:

- `metadataStore` (`RepositoryMetadataStore`)
- `dependencyGraph` (`DependencyGraph`)
- `manifestStore` (page manifest store backed by the same local SQLite
  database)
- `outputRoot` (path to the documentation folder inside the analyzed
  repository, separate from its source folders)

Required methods:

- `generateOverviewPage(repository: Repository) -> DocPage`
- `generateModulePage(moduleSymbol: ModuleSymbol) -> DocPage`
- `generateDependencyDiagramPage(diagram: DiagramExport) -> DocPage`
- `generateRepositoryDocumentation(repositoryRoot, *, incremental=True, changedPaths=(), changedSymbolIds=()) -> DocumentationSet`

Expected behavior:

- `generateOverviewPage` reflects the real module list and dependency
  structure from `RepositoryMetadataStore`/`DependencyGraph`; it never
  invents modules or edges not present in the loaded repository.
- `generateModulePage` lists the module's classes/functions, shows each
  symbol's `generatedSummary` when present, and clearly marks a symbol as
  not yet summarized when it is missing, rather than omitting it or failing.
- `generateDependencyDiagramPage` presents the modules and edges from the
  given `DiagramExport` and links each module to its own module page.
- Every produced `DocPage` has `relatedSymbols` resolved into working
  `PageLink`s to other pages in the same `DocumentationSet`; links that
  cannot be resolved are dropped rather than emitted as broken.
- `generateRepositoryDocumentation` with `incremental=False`, or on the first
  run for a repository, produces the full page set (home + one page per
  module + one page per module's dependency diagram).
- `generateRepositoryDocumentation` with `incremental=True` computes a
  `RegenerationImpactSet` from `changedPaths`/`changedSymbolIds` and
  regenerates only the impacted pages, leaving the rest of the previously
  written `DocumentationSet` untouched.
- Every generated page is written as both a Markdown file and an HTML file
  under `outputRoot`; no file outside `outputRoot` is ever created, modified,
  or deleted.
- Writing to `outputRoot` only creates, overwrites, or removes files tracked
  in the page manifest; unrelated files already present in `outputRoot` are
  left untouched.

## Rendering expectations

- `DocPage.contentMarkdown` is produced first, from a Jinja2 Markdown
  template; `DocPage.renderedHtml` is derived from that same Markdown, not
  authored independently.
- Rendering does not require network access; both the Markdown and HTML
  renders are produced entirely from local repository metadata and local
  Jinja2 templates.

## Incremental expectations

- A `RegenerationImpactSet` includes every page whose source symbols/modules
  changed, every diagram page whose module has a changed dependency edge
  (added or removed, even if neither endpoint symbol's own content changed),
  every page reachable through `DependencyGraph.dependents(...)` from a
  changed symbol, and every page whose `PageLink`s target an impacted page.
- The home page is only included in the impact set when the change affects
  the module list or the top-level architecture it presents.
- Regenerating an impacted subset of pages must not leave any remaining page
  with a link to a page that no longer exists.

## Failure expectations

- If `metadataStore` cannot load the requested repository, the caller
  receives a clear error before any page is written.
- If `outputRoot` is not writable, the caller receives a clear error before
  any existing file in the documentation folder is touched.
- If a module has no generated summary yet, generation still succeeds; the
  page explicitly indicates the summary is pending instead of failing or
  silently omitting the symbol.
