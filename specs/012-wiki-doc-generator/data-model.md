# Data Model: Local Wiki Documentation Generator

## DocPage

Represents one generated documentation page: the home page, a module page, or
a dependency diagram page.

Fields:
- `id`
- `title`
- `contentMarkdown`
- `relatedSymbols`
- `kind` (`"home"`, `"module"`, or `"diagram"`)
- `sourceEntityId` (the `Repository`, `ModuleSymbol`, or `DiagramExport` id
  this page was generated from)
- `renderedHtml`
- `outputPathMarkdown`
- `outputPathHtml`

Relationships:
- Produced by `DocGenerator`
- `relatedSymbols` reference other symbol/module ids resolved into `PageLink`
  entries by the link resolver
- Written to disk by the documentation writer, and recorded as a
  `PageManifestEntry`

Validation:
- `id` must be stable and unique within a `DocumentationSet` (derived
  deterministically from `kind` + `sourceEntityId`, not regenerated per run)
- `title` must be non-empty
- `contentMarkdown` must be non-empty, even when a summary is missing (it
  must still describe the page's structure)
- `relatedSymbols` must only reference ids that exist in the repository
  metadata or dependency graph at generation time

## PageLink

Represents a navigable link from one generated page to another related
module or symbol page.

Fields:
- `fromPageId`
- `toPageId`
- `label`
- `relativePath`

Relationships:
- Derived from a `DocPage.relatedSymbols` entry once the target symbol/module
  is resolved to its own `DocPage`
- Rendered into `contentMarkdown` and `renderedHtml` as an actual link, not
  prose

Validation:
- `toPageId` must resolve to an existing page in the current
  `DocumentationSet` for the link to be considered valid
- A `PageLink` whose target page no longer exists must not be emitted (the
  referencing page is regenerated without it instead of producing a broken
  link)

## DocumentationSet

Represents the full collection of generated pages written to the
documentation folder for one repository, plus enough manifest metadata to
support future incremental regeneration.

Fields:
- `repositoryId`
- `outputRoot`
- `pages` (the generated `DocPage` collection for this run)
- `generatedAt`

Relationships:
- Produced by `DocGenerator.generateRepositoryDocumentation(...)`
- Composed of the home page, one page per module, and one page per
  dependency diagram
- Persisted as `PageManifestEntry` rows for the next incremental run

Validation:
- Must contain exactly one home page
- Must contain exactly one module page per in-scope module
- Must contain exactly one dependency diagram page per in-scope module, even
  when that module currently has zero dependency edges; the page is
  regenerated to show an empty diagram rather than removed (see spec.md Edge
  Cases: a diagram that loses all its dependencies must still be regenerated
  consistently rather than left stale)

## PageManifestEntry

Represents the persisted record of one previously generated page, used to
detect what must change on the next run.

Fields:
- `pageId`
- `kind`
- `sourceSymbolIds` (symbol/module ids this page's content depends on)
- `contentHash`
- `outputPathMarkdown`
- `outputPathHtml`
- `lastGeneratedAt`

Relationships:
- One entry per `DocPage` ever written by this tool for a repository
- Used together with `DependencyGraph.dependents(...)` to compute a
  `RegenerationImpactSet`
- Defines the "managed files" set the writer is allowed to create, overwrite,
  or remove

Validation:
- `pageId` must match the corresponding `DocPage.id`
- `contentHash` must reflect the exact `contentMarkdown` last written
- `sourceSymbolIds` must not be empty for module and diagram pages (the home
  page may depend on the full module list instead of a single symbol)

## RegenerationImpactSet

Represents the set of pages that must be regenerated in response to a given
incremental re-index.

Fields:
- `changedFileIds`
- `changedSymbolIds`
- `changedDependencyEdgeIds` (edges added or removed since the last run,
  independent of whether either endpoint symbol's own content changed)
- `impactedPageIds`
- `requiresHomePageRegeneration` (true when the change affects the module
  list or top-level architecture the home page presents)

Relationships:
- Derived from the changed files/symbols/dependency edges reported by
  re-indexing, the existing `DependencyGraph`, and the stored
  `PageManifestEntry` set
- Consumed by `DocGenerator` to limit a run to only the impacted pages

Validation:
- `impactedPageIds` must include every page whose `sourceSymbolIds` intersect
  the changed/dependent symbol ids
- `impactedPageIds` must include every diagram page whose module is an
  endpoint of a `changedDependencyEdgeIds` entry, even if neither endpoint
  symbol's own content changed
- `impactedPageIds` must include every page containing a `PageLink` that
  targets an impacted page, so links stay consistent after a partial run
- An empty changed set (no files, symbols, or edges) must produce an empty
  impact set (no unnecessary regeneration)
