# Diagrams Navigation Hub Contract

## Purpose

Define the new `doc_generator` function and shared-layout change that turn
already-existing diagram page identities (021 class diagram, 022 sequence
diagrams, 023 use-case diagram, 013 per-module dependency diagrams) into one
always-reachable "Diagrams" page and nav link — the same role
`023-repository-use-case-diagram`'s `use-case-diagram.md` contract plays for
that feature. Unlike 021/022/023, there is no selection+rendering pair here:
one aggregation function, plus one shared-template edit.

## Core function (`doc_generator/generator.py`, method on `DocGenerator`)

### `generateDiagramsIndexPage(*, classDiagramPage: DocPage | None, useCaseDiagramPage: DocPage | None, entryPointPages: tuple[DocPage, ...], modules: tuple[ModuleSymbol, ...]) -> DocPage`

Expected behavior:

- **Never returns `None`.** Even when every input is empty/`None`, returns a
  valid `DocPage` whose rendered content explicitly states there are no
  diagrams yet (spec Edge Case: "zero diagrams... still opens and shows an
  empty list, never a broken page").
- Fixed identity: `id = links.diagrams_index_page_id()`
  (`"diagrams-index"`), `outputPathMarkdown`/`outputPathHtml =
  links.diagrams_index_output_paths()` (`"diagrams-index.md"`/
  `"diagrams-index.html"`) — same fixed-constant pattern as
  `HOME_PAGE_ID`/`HOME_OUTPUT_MARKDOWN`.
- Includes exactly:
  - One entry for `classDiagramPage`, only when it is not `None` (FR-003,
    FR-006).
  - One entry for `useCaseDiagramPage`, only when it is not `None` (FR-003,
    FR-006).
  - One entry per page in `entryPointPages`, in the same order
    `generateEntryPointSequenceDiagramPages()` already returns them (FR-003).
  - One entry per module in `modules`, computed as a dependency-diagram
    identity link (`links.page_slug`/`links.diagram_output_paths`/
    `links.diagram_page_id`, Research Decision 4) — **not** a link to that
    module's own `"module"`-kind documentation page (FR-004: this page MUST
    NOT include any module's text-documentation page).
- Grouped into up to four labeled sections in fixed order — class diagram,
  use-case diagram, sequence diagrams, dependency diagrams — each present
  only when non-empty (FR-006, Research Decisions 2/5).
- Every entry's label clearly identifies its target per FR-008 (exact label
  text: Research Decision 5) — a caller must be able to choose the right
  diagram without opening it first.
- Deterministic: the same inputs always produce byte-identical
  `contentMarkdown` (same ordering guarantee 021/022/023 hold themselves
  to).
- `page.links` contains one `PageLink` per rendered entry, built via the
  existing `links.build_page_link()` — required so `impact.py`'s
  referrer-propagation (`_add_referrers_of`) correctly re-targets this page
  if one of its linked pages is later removed.

## Shared-layout change (`doc_generator/html_render.py`, `doc_generator/templates/layout.html.jinja`)

### `render_page_html(...)`

- Gains one new computed value, `diagrams_href`, via the same
  `relative_output_link(from_output_path=output_path_html, to_output_path=
  links.diagrams_index_output_paths()[1])` pattern already used for
  `home_href` — computed for *every* page, unconditionally (not gated on
  whether that page's own generation targeted the diagrams-index page this
  run; the diagrams-index page always exists once generated at all, per
  Decision 2, so the link target is always valid).
- Passes `diagrams_href` to `layout.html.jinja` alongside the existing
  `home_href`.

### `layout.html.jinja`

- The existing `<nav>` element gains one more `<a href="{{ diagrams_href
  }}">Diagrams</a>`, next to the existing Home link — present on literally
  every generated page (home, module, diagram, class-diagram,
  sequence-diagram, use-case-diagram, diagrams-index itself), satisfying
  FR-002 ("reachable... with exactly one user action, regardless of which
  page the user is currently viewing").

## Incremental regeneration expectations

- `compute_regeneration_impact` (extended per Research Decision 6): returns
  `requiresDiagramsIndexRegeneration = True` whenever the current set of
  module pages, sequence-diagram pages, class-diagram existence, or
  use-case-diagram existence differs from the previous manifest snapshot.
- `generateRepositoryDocumentation` adds `links.diagrams_index_page_id()` to
  `target_page_ids` whenever `target_page_ids is None` (full run) or
  `impact.requiresDiagramsIndexRegeneration` is true — mirroring exactly how
  `HOME_PAGE_ID` is added via `impact.requiresHomePageRegeneration` today.
- A full, from-scratch run (`incremental=False`, or no previous manifest
  entries) regenerates the diagrams-index page unconditionally, same as
  every existing page kind.
- The diagrams-index page's own `PageManifestEntry` is never a member of
  `removedPageIds` — it is not conditionally present like the class/
  use-case diagram pages (Decision 2), so it is never removed, only
  rewritten.

## Failure expectations

- A repository with zero classes, zero entry points, and zero modules: the
  diagrams-index page is still written, with content stating there are no
  diagrams yet — not a missing file, not a template rendering error.
- A repository with no classes and no entry points but at least one module:
  the page includes only the dependency-diagram section — no empty "Class
  diagram" or "Use-case diagram" headings (FR-006, Acceptance Scenario 5).
- The page must never contain a link whose target is a `"module"`-kind
  `DocPage` — asserted directly in tests against a fixture module with a
  non-empty docstring (to rule out the module's own documentation entry
  leaking in), not just trusted to not occur in practice (same standard
  021/022/023 held themselves to for their own invariants).
- The "Diagrams" nav link must resolve to a valid, existing file from every
  page kind this feature's tests generate, including from the
  diagrams-index page itself (spec Edge Case: reached from a diagram page,
  the page still lists every diagram, including the one currently open).
