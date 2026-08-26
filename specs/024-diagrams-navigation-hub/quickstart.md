# Quickstart: Validating the Diagrams Navigation Hub

## Prerequisites

- A local checkout of this repository with its dev dependencies installed
  (`pip install -e ".[test]"`).
- No local LLM/embedding service is required — this feature only reads page
  identities 013/021/022/023 already compute; it performs no summarization
  or embedding.

## Scenario A — Full catalog, every category present (spec Acceptance Scenario 2, SC-001)

1. Use (or build) a fixture repository with at least one module, one class,
   and one identifiable entry point (e.g. one `@app.command()`-decorated
   CLI function) — the same shape 023's Scenario A fixture already uses,
   extended with at least two modules so a dependency-diagram entry is also
   present.
2. Run the documentation pipeline against the fixture (or call
   `DocGenerator.generateRepositoryDocumentation` directly in a test, as
   013/021/022/023's own integration tests do).
3. Open `diagrams-index.html`.
4. **Expected**: the page lists, grouped by category: one class-diagram
   entry, one use-case-diagram entry, one sequence-diagram entry per
   identified entry point, and one dependency-diagram entry per module — and
   no entry for any module's own documentation page. Selecting any entry
   opens that diagram's page directly.

## Scenario B — Reachable in one click from any page (spec FR-002, SC-002)

1. Using Scenario A's already-generated wiki, open `index.html` (Home),
   then any module page, then the class-diagram page, then a sequence-
   diagram page.
2. **Expected**: every one of those pages' shared `<nav>` shows a
   "Diagrams" link. Clicking it from any of them opens
   `diagrams-index.html` directly, with no intermediate page.

## Scenario C — Missing categories are omitted, not shown empty (spec Acceptance Scenario 5)

1. Use a fixture repository with modules but zero classes and zero
   identifiable entry points (e.g. 022's own "zero entry points" fixture,
   extended to also have no classes).
2. Regenerate.
3. **Expected**: `diagrams-index.html` shows only the "Module dependency
   diagrams" section (one entry per module) — no "Class diagram" or
   "Use-case diagram" heading, empty or otherwise.

## Scenario D — Zero diagrams of any kind (spec Edge Case)

1. Use a fixture repository with zero modules (or otherwise zero of every
   diagram kind).
2. Regenerate.
3. **Expected**: `diagrams-index.html` still exists and opens successfully,
   showing an explicit "no diagrams yet" message rather than an empty or
   broken page. The Home page's "Diagrams" nav link still resolves to it.

## Scenario E — Incremental update after the diagram set changes (spec FR-007, SC-003)

1. Starting from Scenario A's fixture (already generated once), add a new
   module, then re-run generation **incrementally**
   (`incremental=True`, matching how `codepedia serve`'s watcher-driven
   reindex already works).
2. **Expected**: `diagrams-index.html` regenerates and now includes a
   dependency-diagram entry for the new module, without a full
   from-scratch reindex of the fixture repository (assert via the same
   "only impacted pages regenerate" mechanism 018's incremental-reindex
   tests already use).
3. Repeat, instead removing the fixture's only class (so the repository has
   zero classes remaining).
4. **Expected**: `diagrams-index.html` regenerates and the "Class diagram"
   section disappears from it, without a full from-scratch reindex.

## What "done" looks like

All five scenarios pass without manual inspection of raw HTML beyond what
the assertions above check; the generated `diagrams-index.html` page opens
and renders in a real browser with zero console errors and zero network
requests, and the "Diagrams" nav link is present and correct on every other
generated page, consistent with every other page this project already
generates (spec SC-004).
