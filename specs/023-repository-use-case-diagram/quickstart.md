# Quickstart: Validating the Repository Use Case Diagram

## Prerequisites

- A local checkout of this repository with its dev dependencies installed
  (`pip install -e ".[test]"`).
- No local LLM/embedding service is required — this feature only reads
  022's already-identified entry points; it performs no summarization or
  embedding.

## Scenario A — Distinct CLI and API actors (spec SC-001, the primary success criterion)

1. Create a small fixture repository (or reuse an existing
   `tests/integration` fixture) with:
   - `cli.py`: a function decorated `@app.command()` (or `@app.callback()`).
   - `api.py`: a function decorated `@app.get("/sessions")` (or `.post`/
     `.put`/`.delete`/`.patch`).
2. Run the indexing/documentation pipeline against the fixture repo (or call
   `DocGenerator.generateRepositoryDocumentation` directly in a test, as
   021/022's own integration tests do).
3. Open `docs/diagrams/use-case-overview.md` (or its rendered `.html`).
4. **Expected**: a `flowchart` block with two distinct actor nodes (labeled
   `CLI` and `API`), each connected by its own arrow to its own use-case
   node (the CLI command, the API route), and the wiki's home page links to
   this diagram page.

## Scenario B — Generic fallback actor for a plain function entry point (spec FR-004)

1. Add a function to the fixture that is never called by anything and is
   not decorated as a CLI command or API route.
2. Regenerate.
3. **Expected**: a third use-case node for that function, connected to a
   single actor node labeled `External Caller` — not to the `CLI` or `API`
   actor.

## Scenario C — Multiple entry points of the same kind share one actor (spec Acceptance Scenario 3)

1. Add a second `@app.command()`-decorated function to the fixture.
2. Regenerate.
3. **Expected**: two use-case nodes (one per CLI command), both connected to
   the *same* single `CLI` actor node — not two separate CLI actors.

## Scenario D — No entry points at all (spec FR-005, Edge Case)

1. Use a fixture repository where every function is called by at least one
   other function and none is CLI/route-decorated (e.g. the fixture built
   for 022's own "zero entry points" test).
2. Regenerate.
3. **Expected**: no `diagrams/use-case-overview.md`/`.html` files are
   produced, and the wiki's home page contains no link to a missing
   use-case-diagram page.

## Scenario E — Incremental update after an entry point is added/removed (spec SC-005)

1. Starting from Scenario A's fixture (already generated once), add a new
   `@app.get(...)`-decorated function to `api.py`.
2. Re-run generation **incrementally** (`incremental=True`, matching how
   `repo-scanner serve`'s watcher-driven reindex already works).
3. **Expected**: the use-case-diagram page regenerates and now shows a third
   use-case node connected to the existing `API` actor, without a full
   from-scratch reindex of the fixture repository (assert via the same
   "only impacted pages regenerate" mechanism `018`'s incremental-reindex
   tests already use).

## What "done" looks like

All five scenarios pass without manual inspection of raw Mermaid text
beyond what the assertions above check; the generated `.html` page opens and
renders in a real browser with zero console errors and zero network
requests, consistent with every other diagram this project already
generates (spec SC-004).
