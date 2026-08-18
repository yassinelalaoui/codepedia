# Data Model: Diagrams Navigation Hub

This feature introduces no selection/rendering split like
021/022/023 — it aggregates page identities those features' generators
already compute. Entities below map onto `spec.md`'s Key Entities
(`DiagramsIndexPage`, `DiagramCatalogEntry`).

## New entity: `DiagramsIndexPage`

A specialization of the existing `DocPage` (`doc_generator.models`), not a
new dataclass:

- `id`: fixed constant, `links.diagrams_index_page_id()` →
  `"diagrams-index"` (new `links.DIAGRAMS_INDEX_PAGE_ID`). Not prefixed
  `"diagram:"` like `CLASS_DIAGRAM_PAGE_ID`/`USE_CASE_DIAGRAM_PAGE_ID`/
  per-module diagram pages — this page is a navigation/index page, not a
  diagram, mirroring how `HOME_PAGE_ID` ("home") is also unprefixed.
- `kind`: new `PageKind` literal, `"diagrams-index"`.
- `outputPathMarkdown` / `outputPathHtml`: fixed constants,
  `links.diagrams_index_output_paths()` → `"diagrams-index.md"` /
  `"diagrams-index.html"` (new `links.DIAGRAMS_INDEX_OUTPUT_MARKDOWN`/
  `_OUTPUT_HTML`), sibling to `index.md`/`index.html` (the Home page) at the
  output root — not inside `diagrams/`, which holds actual diagram pages.
- `contentMarkdown`/`renderedHtml`: rendered from the new
  `diagrams_index.md.jinja` template (Research Decision 5), grouped into up
  to four sections.
- `links`: one `PageLink` per `DiagramCatalogEntry` below (never a link to
  any `"module"`-kind page — FR-004).
- `relatedSymbols` / `contentSymbolIds` / `sourceEntityId`: unused by this
  page kind (empty/`""`), same as `generateClassDiagramPage`'s
  `sourceEntityId=""` precedent — this page is repository-wide and has no
  single owning symbol.
- Always generated (never `None`) — Research Decision 2.

## New entity: `DiagramCatalogEntry`

A transient grouping assembled inside `generateDiagramsIndexPage()` and
passed to the template — not a new persisted dataclass (nothing beyond the
page's own `PageManifestEntry` needs to survive across runs):

- `category`: one of `"class-diagram" | "use-case-diagram" |
  "sequence-diagram" | "dependency-diagram"` — determines which of the four
  template sections (Research Decision 5) the entry renders under.
- `label: str` — human-readable identification of what the entry links to,
  per FR-008 (Research Decision 5): `"Repository class diagram"`,
  `"Repository use-case diagram"`, the sequence-diagram entry's own
  `DocPage.title` (`f"{entry_point.name} — Call sequence"`), or
  `f"{module.name} dependencies"`.
- `link: PageLink` — built via the existing `links.build_page_link()`, same
  as every other page-to-page link in this codebase; `relativePath` is what
  the template renders as the entry's href.

Represented in code as a small `list[dict]` (or a lightweight local
`NamedTuple`) grouped by `category` before being passed to
`diagrams_index.md.jinja` — the concrete Python shape is an implementation
detail left to `/speckit-tasks`; the fields above are the contract the
template consumes.

## Existing entities this feature reads but does not modify

- `generateClassDiagramPage()` / `generateUseCaseDiagramPage()` return
  values (`DocPage | None`, 021/023) — read only to learn whether each
  exists this run and, if so, its `id`/`outputPathMarkdown`.
- `generateEntryPointSequenceDiagramPages()` return value (`tuple[DocPage,
  ...]`, 022) — read only for each page's `id`/`title`/`outputPathMarkdown`.
- `RepositoryBundle.files` (`repository_metadata`) — read only to enumerate
  modules for the dependency-diagram category, the same input
  `generateOverviewPage` already reads for its own module list.
- `links.page_slug`, `links.diagram_output_paths`, `links.diagram_page_id`
  (013) — reused unmodified to compute each module's dependency-diagram
  identity (Research Decision 4).

## Existing entities this feature extends

### `PageKind` (`doc_generator.models`)

Add `"diagrams-index"` to the existing `Literal["home", "module", "diagram",
"class-diagram", "sequence-diagram", "use-case-diagram"]`.

### `RegenerationImpactSet` (`doc_generator.models`) / `compute_regeneration_impact` (`doc_generator.impact`)

Add one new field:

- `requiresDiagramsIndexRegeneration: bool` (default `False`) — true
  whenever the current diagram-page set (module pages, sequence-diagram
  pages, class-diagram existence, use-case-diagram existence) differs from
  the previous manifest snapshot (Research Decision 6). Additive: existing
  `requiresHomePageRegeneration` semantics and existing tests against it are
  unchanged.

### `DocGenerator` (`doc_generator.generator`)

Add one new method, `generateDiagramsIndexPage(...) -> DocPage` (never
`None`), and wire it into `generateRepositoryDocumentation` alongside the
Home page: computed and written whenever `target_page_ids is None or
impact.requiresDiagramsIndexRegeneration or links.diagrams_index_page_id()
in target_page_ids`.

### `layout.html.jinja` / `html_render.render_page_html` (`doc_generator`)

`render_page_html` gains one new computed template variable,
`diagrams_href`, alongside the existing `home_href` (Research Decision 3).
`layout.html.jinja`'s `<nav>` gains one more `<a>` for it, present on every
generated page unconditionally.

## Relationships

```
DiagramsIndexPage 1 ── * DiagramCatalogEntry ── 1 PageLink ── targets exactly one of:
                                                    ├─ the class-diagram DocPage (0 or 1, repository-wide)
                                                    ├─ the use-case-diagram DocPage (0 or 1, repository-wide)
                                                    ├─ a sequence-diagram DocPage (0..N, one per entry point)
                                                    └─ a per-module dependency-diagram DocPage (0..N, one per module)

Every generated page (home, module, diagram, class-diagram, sequence-diagram,
use-case-diagram, diagrams-index) ── renders via ── layout.html.jinja
                                                        └─ <nav> links to: home_href, diagrams_href (always both)
```

`DiagramsIndexPage` never links to a `"module"`-kind `DocPage` (FR-004) —
the only `DocPage` kinds it may link to are `"class-diagram"`,
`"use-case-diagram"`, `"sequence-diagram"`, and `"diagram"` (the per-module
dependency diagram; note this existing kind name refers to the *diagram*
page, distinct from `"diagrams-index"`, the new aggregation page).

## State transitions

On each `generateRepositoryDocumentation` run:

1. The current diagram-page set is recomputed fresh from
   `RepositoryBundle`/`DependencyGraph` (same "recompute cheaply every run,
   never incrementally diffed" rule 021/022/023 already established for
   their own selections).
2. `compute_regeneration_impact` compares that set's identity against the
   previous manifest snapshot to produce
   `requiresDiagramsIndexRegeneration`.
3. If true (or on a full/non-incremental run, or the page is otherwise
   targeted), `DiagramsIndexPage` is rebuilt and written; its
   `PageManifestEntry.contentHash` changes only if the rendered markdown
   actually differs (unchanged if e.g. a module's dependency-diagram
   *content* changed but the module set itself did not — this page's
   entries reference other pages by stable id/path, not by their content).
4. Otherwise the page is left untouched on disk, consistent with the
   incremental-regeneration principle (Constitution 2.5).
