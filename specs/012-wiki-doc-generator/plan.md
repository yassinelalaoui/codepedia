# Implementation Plan: Local Wiki Documentation Generator

Branch: `012-wiki-doc-generator` | Date: 2026-08-12 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/012-wiki-doc-generator/spec.md`

## Summary

Build a local documentation generator that assembles a wiki-style page set
from already extracted repository metadata and already generated local
summaries: one home page presenting the project's real architecture, one
page per module listing its role, classes/functions, and their summaries,
and one page per dependency diagram. Every page links to the related
module/symbol pages it references.

The design reuses the existing `RepositoryMetadataStore` and
`DependencyGraph` for all structural content and generates no new analysis.
Pages are authored as Jinja2 Markdown templates (`DocPage.contentMarkdown`)
and then rendered to HTML via a shared Jinja2 site layout, MkDocs/Docusaurus
style. `DocGenerator` exposes `generateOverviewPage(Repository)` and
`generateModulePage(ModuleSymbol)`, plus `generateDependencyDiagramPage` and
an orchestrating `generateRepositoryDocumentation`. A page manifest persisted
in the existing local SQLite store tracks each page's source symbols, content
hash, and output paths so incremental re-indexing can regenerate only the
impacted pages instead of the entire wiki.

## Technical Context

Language/Version: Python 3.11+

Primary Dependencies: `Jinja2` (Markdown and HTML page templating), `markdown`
(Markdown-to-HTML conversion for the derived HTML export), Python standard
library, and the existing `repository_metadata`, `dependency_graph`, and
`parser_engine` packages, plus the existing pytest-based test stack

Storage: Existing SQLite-backed repository metadata store, extended with a
new page-manifest table for incremental impact tracking; generated
Markdown/HTML pages themselves are written as plain files to a dedicated
documentation folder inside the analyzed repository, not into any database

Testing: pytest with unit, contract, and integration coverage

Target Platform: Local CLI/library usage on Windows, macOS, and Linux

Project Type: Internal pipeline/library invoked after indexing and
summarization, producing exportable, committable static documentation

Performance Goals: Full generation completes without manual intervention for
a repository-scale module/diagram page set; incremental regeneration work is
bounded by the size of the change (impacted pages only), not the size of the
repository

Constraints: Local-only execution with no network access during rendering,
the analyzed repository's source stays read-only (only the dedicated
documentation folder is written), incremental regeneration only touches
impacted pages, no heavy infrastructure beyond the existing SQLite store and
plain files, and the writer never touches files outside its own managed set

Scale/Scope: Repository-wide documentation generation: one home page, one
page per module, and one page per module's dependency diagram, each rendered
as both Markdown and HTML

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentiality absolute: pass; rendering uses only local metadata, local
  summaries, and local Jinja2/Markdown libraries, with no network calls
- Zero exposure network by default: pass; the generator writes local files
  only and does not open any network service
- Never reply silently with a cloud service: pass; not applicable, this
  feature performs no generation/inference of its own, only assembly of
  existing local summaries
- Traceability of AI responses: pass; every module page keeps each symbol's
  summary attached to that symbol and links back to it, and a missing
  summary is shown explicitly rather than fabricated
- Incremental local operation: pass; a page manifest and
  `RegenerationImpactSet` limit regeneration to pages impacted by a change
- Minimal infrastructure and local storage: pass; reuses the existing SQLite
  metadata store plus plain Markdown/HTML files, no new infrastructure
- Repository analysis read-only: pass; the generator only ever writes inside
  the dedicated documentation folder and never touches the analyzed
  repository's source files

## Project Structure

### Documentation for this feature

`specs/012-wiki-doc-generator/`
- `spec.md`
- `research.md`
- `data-model.md`
- `quickstart.md`
- `contracts/`
  - `doc-generator.md`

### Source Code

`src/`
- `doc_generator/`
  - `__init__.py`
  - `models.py`
  - `generator.py`
  - `diagrams.py`
  - `markdown_render.py`
  - `html_render.py`
  - `links.py`
  - `manifest_store.py`
  - `impact.py`
  - `writer.py`
  - `templates/`
    - `home.md.jinja`
    - `module.md.jinja`
    - `diagram.md.jinja`
    - `layout.html.jinja`
- `repository_metadata/`
  - `store.py`
- `dependency_graph/`
  - `graph.py`
  - `queries.py`
  - `export.py`

Structure Decision: keep documentation assembly in a dedicated
`doc_generator` package that composes the existing `repository_metadata` and
`dependency_graph` packages, the same way `chat` (011) composed embedding,
retrieval, and generation without mixing session state into the index
implementation. `doc_generator` owns page modeling, templating, link
resolution, the manifest/impact computation, and file writing; it never
performs its own static analysis or summarization.

## Phase 0: Research

### Decision 1

Use Jinja2 for both Markdown and HTML page templates, rejecting Handlebars
because it would require a JavaScript runtime or a less-maintained Python
port, while Jinja2 is already the templating engine MkDocs itself uses and
stays pure Python.

### Decision 2

Render Markdown first as the canonical, versionable `DocPage.contentMarkdown`,
then derive `DocPage.renderedHtml` from that same Markdown via a shared
Jinja2 HTML layout, so Markdown and HTML never drift apart.

### Decision 3

Build `generateOverviewPage`/`generateModulePage` content exclusively from
`RepositoryMetadataStore` (`RepositoryBundle`, `SourceFileBundle`,
`generatedSummary`) and `DependencyGraph`, so the generator remains a pure
consumer of already extracted metadata and already generated summaries.

### Decision 4

Build one `DiagramExport` per module (its direct dependency neighborhood)
using the existing `dependency_graph.queries`/`export` helpers, and render
one diagram `DocPage` per `DiagramExport`.

### Decision 5

Persist a page manifest in the existing local SQLite store and compute a
`RegenerationImpactSet` the same way `CodeSummaryPipeline` computes
`ImpactedSymbolSet`, from changed file/symbol ids plus
`DependencyGraph.dependents(...)`.

### Decision 6

Restrict the writer to files tracked in the page manifest's managed-file set,
so manually added or unrelated files already present in the documentation
folder are never deleted or overwritten.

## Phase 1: Design

### Data model

Define `DocPage`, `PageLink`, `DocumentationSet`, `PageManifestEntry`, and
`RegenerationImpactSet`, including validation rules for stable page ids,
resolvable links, and impact propagation through the dependency graph and
existing page links.

### Contracts

Document the public `DocGenerator` interface
(`generateOverviewPage`, `generateModulePage`,
`generateDependencyDiagramPage`, `generateRepositoryDocumentation`), the
Markdown-then-HTML rendering expectation, the incremental impact
expectations, and the failure modes for an unloadable repository or an
unwritable documentation folder.

### Quickstart

Provide validation steps that prove a full run produces an accurate home
page, module pages with symbols/summaries/links, and diagram pages with zero
broken links, and that an incremental re-run regenerates only the impacted
pages while leaving the rest of the documentation folder untouched.

## Constitution Check After Design

No violations introduced by the chosen design.