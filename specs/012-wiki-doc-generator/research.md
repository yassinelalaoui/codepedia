# Research: Local Wiki Documentation Generator

## Decision 1: Use Jinja2 for page templating, not Handlebars

Decision: Render every generated page (Markdown and HTML) through Jinja2
templates.

Rationale: The project is a pure Python, offline-first tool with no other
JavaScript/Node runtime dependency anywhere in the stack. Jinja2 is already
the templating engine used internally by MkDocs, the exact "MkDocs-style"
output the feature targets, and it ships as a pure-Python dependency with no
extra runtime to install or sandbox locally.

Alternatives considered: Handlebars was considered because it is named in the
feature request and is Docusaurus's conceptual sibling in the JS ecosystem,
but using it from Python would require either shelling out to Node or adding
a less-maintained Python port (`pybars3`). Neither keeps the offline,
minimal-infrastructure footprint required by the constitution, so Handlebars
is rejected in favor of Jinja2 for both Markdown and HTML rendering.

## Decision 2: Markdown as the canonical content, HTML as a derived render

Decision: Every `DocPage.contentMarkdown` is produced first, from a Jinja2
Markdown template. The HTML export is then produced by converting that same
Markdown to HTML and wrapping it in a shared Jinja2 HTML layout (nav, header,
footer), rather than authoring Markdown and HTML as two independent template
sets.

Rationale: This mirrors how MkDocs/Docusaurus work: Markdown is the
versionable source of truth committed to the repository, and HTML is a
convenience rendering for browsing without a Markdown viewer. Deriving HTML
from the already-generated Markdown guarantees the two outputs never drift
from each other and halves the number of templates that must stay in sync
per page kind.

Alternatives considered: Maintaining separate Markdown and HTML template
sets was rejected because it doubles template maintenance and creates a risk
that the two formats disagree about a module's symbols or links.

## Decision 3: Build page content from existing repository metadata only

Decision: `DocGenerator.generateOverviewPage(Repository)` builds its content
from the existing `RepositoryMetadataStore.load_repository(...)`
(`RepositoryBundle`: modules, classes, functions, dependency graph), and
`DocGenerator.generateModulePage(ModuleSymbol)` builds its content from the
matching `SourceFileBundle` (its classes/functions and their
`generatedSummary` fields) plus the existing `DependencyGraph` for related
modules/symbols. No new static analysis or summarization logic is added by
this feature.

Rationale: The spec explicitly scopes this feature to assembling already
extracted metadata and already generated summaries, not producing new ones.
Reusing `repository_metadata`, `parser_engine`, and `dependency_graph` keeps
the documentation generator a pure consumer, consistent with how
`CodeSummaryPipeline` (010) and `chat` (011) reuse the same packages instead
of re-deriving repository facts.

Alternatives considered: Re-walking source files directly from the doc
generator was rejected because it would duplicate parsing already done by
`parser_engine` and could disagree with the stored inventory.

## Decision 4: One dependency diagram page per module, built from `DiagramExport`

Decision: Build one `DiagramExport` per module (its direct dependency
neighborhood) using the existing `dependency_graph.queries`
(`filter_edges`, `ordered_nodes`) and `dependency_graph.export`
(`build_diagram_export`) helpers, and render one `DocPage` per
`DiagramExport` via `DocGenerator.generateDependencyDiagramPage`.

Rationale: `dependency_graph` already exposes the query and export
primitives needed to select a bounded, per-module neighborhood, matching the
existing `GraphQuery`/`DiagramExport` model instead of inventing a new
diagram concept. A per-module diagram keeps each page's content directly
traceable to one module, so module pages and diagram pages can link to each
other one-to-one.

Alternatives considered: A single repository-wide diagram page was rejected
because it would not scale visually or textually beyond a small repository,
and it would not localize regeneration to the modules actually affected by a
change (Non-Goal: no new analysis, but also FR: incremental regeneration).

## Decision 5: Track a page manifest to compute incremental regeneration impact

Decision: Persist a page manifest (page id, kind, source symbol/module ids,
content hash, output paths) in a new table in the existing local SQLite
metadata store, and compute a `RegenerationImpactSet` the same way
`CodeSummaryPipeline._compute_impacted_symbols` computes `ImpactedSymbolSet`:
from changed file/symbol ids plus `DependencyGraph.dependents(...)`, then
resolving which manifest entries reference those ids (as a source or as a
related-page link).

Rationale: The project already has a proven, constitution-compliant pattern
(SQLite-only local storage, symbol-level impact sets) for exactly this kind
of "what needs to be redone" computation. Reusing it keeps the incremental
behavior consistent across the summary pipeline and the documentation
generator, and avoids adding a new storage engine.

Alternatives considered: Recomputing impact by hashing the entire generated
documentation folder on every run was rejected because it would require a
full regeneration pass to detect what changed, defeating the incremental
goal. A manifest file inside the documentation folder itself was also
considered, but keeping it in the tool's own local SQLite store (outside the
analyzed repository) keeps the documentation folder limited to the
committable pages a reader actually wants to see, matching the "repository
analysis read-only outside the doc folder" principle.

## Decision 6: The writer only touches files it manages

Decision: The manifest also records the previous output paths written by
each page. Regeneration (full or incremental) only creates, overwrites, or
removes files present in this managed set; any other file already in the
documentation folder is left untouched.

Rationale: The spec's edge case requires that manually added or unrelated
files in the documentation folder must not be deleted by the generator. A
manifest-backed managed-file set is the simplest local mechanism to
distinguish "files this tool generated" from "files someone else put there."

Alternatives considered: Clearing and fully rewriting the documentation
folder on every run was rejected because it conflicts with that edge case
and would also defeat incremental regeneration.
