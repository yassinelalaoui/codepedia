# Quickstart: Validating Entry Point Sequence Diagrams

## Prerequisites

- A local checkout of this repository with its dev dependencies installed
  (`pip install -e ".[test]"`).
- No local LLM/embedding service is required — this feature only reads
  already-extracted symbols and the in-memory dependency graph; it performs
  no summarization or embedding.

## Scenario A — Multi-module call chain (spec SC-001, the primary success criterion)

1. Create a small fixture repository (or reuse an existing
   `tests/integration` fixture) with:
   - `cli.py`: a function `main()` decorated `@app.command()` (or simply
     never called by any other function in the fixture) that calls
     `service.process()`.
   - `service.py`: `process()` calls `repository.save()`.
   - `repository.py`: `save()` — a plain function with no further calls.
2. Run the indexing/documentation pipeline against the fixture repo (or call
   `DocGenerator.generateRepositoryDocumentation` directly in a test, as
   `021`'s own integration tests do).
3. Open `docs/diagrams/main-<slug>.md` (or its rendered `.html`).
4. **Expected**: a `sequenceDiagram` block with three participants
   (`cli.main`, `service.process`, `repository.save`) and two `->>` messages
   in that exact order, each callee's participant label showing its correct
   originating module.

## Scenario B — Entry point with no outgoing calls (spec FR-006 / SC-004)

1. Add a function `noop()` to the fixture that is never called by anything
   and calls nothing itself.
2. Regenerate.
3. **Expected**: a sequence-diagram page exists for `noop`, containing a
   `sequenceDiagram` block with exactly one `participant` line and zero
   `->>` messages — no fabricated interaction.

## Scenario C — Recursion / cycle bounded by depth (spec FR-005 / SC-003)

1. Add `recursive_fn()` that calls itself.
2. Add `a()` calling `b()`, and `b()` calling `a()` (a two-function cycle),
   with `a()` otherwise unreached (qualifies as an entry point).
3. Regenerate.
4. **Expected**: both diagrams render fully and terminate — the recursive
   entry point's diagram has exactly `MAX_CALL_DEPTH` (6) steps, all
   `recursive_fn -> recursive_fn`; the cycle's diagram alternates
   `a -> b -> a -> b -> ...` for 6 steps, neither hangs nor errors.

## Scenario D — No entry points at all (spec Edge Case 5)

1. Use a fixture repository where every function is called by at least one
   other function and none is CLI/route-decorated.
2. Regenerate.
3. **Expected**: zero files under `docs/diagrams/` attributable to entry
   points (only whatever per-module dependency diagrams already exist), and
   no module page contains a link to a missing sequence-diagram page.

## Scenario E — Incremental update after a repository change (spec FR-010 / SC-005)

1. Starting from Scenario A's fixture (already generated once), edit
   `service.py` so `process()` calls `repository.save()` twice more, in a
   different order relative to another call it already makes.
2. Re-run generation **incrementally** (`incremental=True`, matching how
   `codepedia serve`'s watcher-driven reindex already works).
3. **Expected**: `cli.main`'s sequence diagram is regenerated and reflects
   the new order, without a full from-scratch reindex of the fixture
   repository (assert via the same "only impacted pages regenerate"
   mechanism `018`'s incremental-reindex tests already use).

## What "done" looks like

All five scenarios pass without manual inspection of raw Mermaid text
beyond what the assertions above check; the generated `.html` pages open and
render in a real browser with zero console errors and zero network
requests, consistent with every other diagram this project already
generates (spec SC-006).
