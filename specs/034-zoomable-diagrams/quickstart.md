# Quickstart: Validating Zoomable Diagrams

**Feature**: 034-zoomable-diagrams | **Date**: 2026-09-01

How to prove this feature works end to end. Two of the acceptance criteria
(SC-003, SC-004) cannot be settled in a headless DOM, so the real-browser pass
in section 3a is part of the validation, not an optional extra. It is automated
against headless Chrome; section 3b lists what still needs human eyes.

## Prerequisites

- Python virtualenv active. **Must be Python 3.11-3.13** — 3.14 hangs during
  Pydantic schema generation in this project.
- Node 25 / npm 11, already present.
- `cd frontend && npm install` if `node_modules` is absent.

---

## 1. Automated: frontend

```bash
cd frontend
npm test
```

Expected: all existing suites still green, plus the new
`tests/diagramViewport.test.ts`.

The cases that carry the weight, in priority order:

| Case | Asserts |
| --- | --- |
| 2px movement then click | `preventDefault()` NOT called — the link navigates (FR-010) |
| 10px movement then click | `preventDefault()` called (FR-011) |
| drag out and back to origin, then click | `preventDefault()` called — the flag latches (data-model `GestureState`) |
| second click, unmoved, after a drag | `preventDefault()` NOT called — the flag cleared |
| wheel with pointer at a known offset | the point under the pointer is invariant (FR-002) |
| repeated wheel to the limits | `scale` stays within `[0.2, 8]` (FR-004) |
| reset after zoom + pan | transform is exactly `translate(0px, 0px) scale(1)` (FR-007) |
| `enhanceDiagrams()` twice | second call returns `0`, one control bar, view preserved (FR-015) |
| `pre.mermaid` with no `<svg>` | not enhanced, **not** marked, enhanced by a later sweep (FR-014) |
| one diagram missing `viewBox`, one valid | the valid one is still enhanced (FR-016) |

Test-environment notes, from research Decision 6 — these are constraints, not
preferences:

- Dispatch `new MouseEvent("pointerdown", { clientX, clientY, bubbles: true })`.
  jsdom 25 has **no** `PointerEvent` constructor.
- Stub `getBoundingClientRect` for the zoom-anchor and fit-to-width cases; jsdom
  returns all zeros. The click-vs-drag cases need no rect.
- Never assert on `matchMedia` or `ResizeObserver`; the implementation must not
  use them.

**Watch for the false pass**: asserting only that a click handler spy went
uncalled proves nothing here. Mermaid's link is a real `<svg:a>`, so the
assertion that matters is on `preventDefault()`.

---

## 2. Automated: Python

```bash
pytest --basetemp="$SCRATCH/pytest" -p no:cacheprovider
```

(`--basetemp` into the scratchpad and `-p no:cacheprovider` avoid ~17 spurious
`PermissionError`s on this machine.)

Expected: 667 green plus one known flake.
`tests/integration/test_cli.py::test_config_before_any_provider_reachable_still_reports_without_failing`
performs a **live Groq availability check**, so it passes when Groq is
unreachable and fails when Groq answers. Both outcomes were observed on
2026-09-01 with no code change between runs. Identify it by the failure text
naming `groq:...: available`; any other failure is real. It is the only
non-deterministic test in the suite.

Specifically:

- `tests/integration/test_mermaid_diagram.py`, `test_class_diagram.py`,
  `test_entry_point_diagram.py`, `test_diagrams_index.py`,
  `test_prose_wiki_surface.py` pass **with no changes to their existing
  assertions**. That is the evidence the viewport stayed client-side (FR-022).
- Each gains one new assertion that `click … href` directives still reach the
  rendered page.
- A new assertion pins `startOnLoad: false` and the `mermaid.run(` call in the
  rendered layout.

---

## 3a. Automated: real browser (Chrome via DevTools Protocol)

jsdom cannot run Mermaid, so the interactions that matter most are unverifiable
in the unit suite. They are verified instead by driving headless Chrome over CDP
against a generated wiki loaded from `file://` - the real deployment mode.

```bash
# generate a wiki, then:
chrome --headless=new --disable-gpu --remote-debugging-port=9333        --user-data-dir=<tmp> about:blank &
node final.mjs "file:///<abs-path>/demo-wiki/diagrams/<a-dependency-diagram>.html"
```

The harness lives in the session scratchpad rather than the repo (it is a
verification aid, not a shipped test). Three lessons from building it, each of
which produced a *false* result before being fixed:

1. **Do not append a cache-busting query to a `file://` URL** - it changes how
   the page's own scripts resolve and reports the bundle as absent.
2. **Start a drag inside the viewport.** A `pointerdown` outside it never reaches
   the handler, so the drag silently no-ops - and still "passes" a
   does-not-navigate check, for entirely the wrong reason.
3. **Scroll the diagram into view first.** CDP dispatches at window coordinates;
   on a section page the diagram sits below the fold, so every synthetic mouse
   event lands somewhere else and four checks fail for no product reason.

Also: `python -m http.server` truncates the 3.3 MB Mermaid bundle on Windows
(456 KB of 491 KB after ~19 s). Use `file://`, or a threaded server.

**Result, 2026-09-01: 17/17 on both click-target surfaces** - a module dependency
diagram and a section internal-dependency diagram. Measured cursor-anchor drift
under wheel zoom: 0.44 px and 0.57 px.

---

## 3b. Manual: on a real generated wiki

Automated tests cannot answer whether Mermaid's own anchor still navigates under
a transformed ancestor. This section is required.

```bash
cd frontend && npm run build && cd ..
# regenerate a wiki, then serve it
codepedia index <some-repo> && codepedia serve <some-repo>
```

Open the repository class diagram (`diagrams/class-overview.html`) — the densest
page — and walk these:

1. **Read it** (US1). Wheel-zoom onto a node; confirm that node stays under the
   cursor rather than sliding away. Drag the canvas. Read a label that was
   illegible at load.
2. **Click through** (US2, **SC-003**). Click a node without moving the pointer →
   the module page opens. Go back. Press on the same node, drag well clear,
   release → nothing navigates. Zoom in 3×, click a node → the *correct* page
   opens, not a neighbour's.
3. **Controls** (US1, US3). Reset returns the exact load-time view. Fit-to-width
   shows the whole diagram width. Expand fills the window and stays zoomable;
   Escape returns to the page at the same scroll position.
4. **Keyboard** (US4). Tab to the diagram; focus is visible. `+`, `-`, `0`, then
   arrows. Confirm the page itself does not scroll while arrows pan the diagram.
5. **Every surface** (FR-013, SC-002). Repeat step 1 briefly on: a module
   dependency diagram, an entry-point sequence diagram, the use-case diagram, a
   feature page's internal-dependency diagram, and the home page's embedded class
   diagram. The two carrying click targets — module dependency and feature
   internal-dependency — also need step 2.
6. **Dark mode** (FR-021). Switch the OS to dark; the viewport frame and controls
   follow the wiki's palette.
7. **Reduced motion** (FR-020). Enable it in the OS; controls still work, with no
   transition.
8. **Offline / file://** (FR-023, SC-007). Open a page directly from disk with
   the network disabled. Everything above still works. Confirm in DevTools that
   the Network tab shows no external request.
9. **Degradation** (FR-024). Rename `assets/wiki-ui.js` in the generated output
   and reload: diagrams still render and node links still navigate — only the
   zoom is gone. Restore it.
10. **Markdown untouched** (FR-022, SC-006). Diff the generated `.md` tree
    against one produced before the change:

    ```bash
    diff -r docs-before/ docs-after/ --exclude='*.html' --exclude=assets
    ```

    Expected: no differences. **Both builds must index the same repository at the
    same absolute path.** Generated pages embed absolute source paths, so
    indexing a copy of the repo into two different directories makes half the
    `.md` files differ for that reason alone — which is exactly what the first
    attempt at this check during implementation reported before the flaw was
    found. Re-run with one shared root: **0 of 14 files differ**, verified
    2026-09-01.

---

## 4. Shipping

The interface bundle is a committed build artifact, so `npm run build` must run
before the commit and the regenerated
`src/doc_generator/assets/wiki-ui.js` / `wiki-ui.css` must be staged alongside
the `frontend/src` changes. A commit that changes `frontend/src` without them
ships a stale wiki that the Python tests will serve.

```bash
git status --short src/doc_generator/assets/
# expect: M wiki-ui.js, M wiki-ui.css
```
