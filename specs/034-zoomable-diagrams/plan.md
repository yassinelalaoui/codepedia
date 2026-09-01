# Implementation Plan: Zoomable, Navigable Diagrams in the Generated Wiki

**Branch**: `034-zoomable-diagrams` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/034-zoomable-diagrams/spec.md`

## Summary

Every Mermaid diagram in the generated wiki is currently pinned to the content
column by an inline `max-width` and is unreadable past a handful of nodes. This
adds a bounded, pan-and-zoom viewport around each drawn diagram, with visible
and keyboard-driven controls, without breaking the node-click navigation the
wiki already relies on and without adding a single byte of network dependency.

The approach is a ~150-line hand-written enhancer in the existing wiki interface
bundle, plus a four-line change to the shared layout's Mermaid bootstrap. It runs
entirely client-side: Mermaid draws the SVG in the browser, so the enhancement
must happen there anyway, and keeping it there is what leaves the generated
Markdown byte-identical.

Two findings from Phase 0 shape everything else:

1. Mermaid realises `click <node> href "..."` as a real `<svg:a xlink:href>`, so
   navigation is an anchor's **default action**. Suppressing a drag therefore
   requires `preventDefault()` in the **capture** phase — `stopPropagation()`
   alone would let every drag navigate while still passing a naive unit test.
2. jsdom 25 defines neither `PointerEvent`, `setPointerCapture`, `matchMedia` nor
   `ResizeObserver`, and returns all-zero rects. That is not merely a testing
   inconvenience: it pushes `prefers-reduced-motion` into CSS (where it belongs),
   removes `ResizeObserver` from the design, and forces a `window`-level pointer
   fallback that independently fixes the "drag released outside the viewport"
   edge case.

## Technical Context

**Language/Version**: TypeScript 5.6 (frontend); Python 3.11-3.13 (generator —
one Jinja template edit only). Python 3.14 is unusable in this project: Pydantic
schema generation hangs.

**Primary Dependencies**: None added. Mermaid 10.9.8 is already vendored at
`src/doc_generator/assets/mermaid.min.js` and consumed as the `window.mermaid`
global — it is deliberately *not* an npm dependency of `frontend/`, so the
enhancer works off rendered DOM rather than a Mermaid API.

**Storage**: N/A. This feature persists nothing — no manifest table, no generated
file, no browser storage. All state is in-memory per rendered diagram.

**Testing**: Vitest 2.1 + jsdom 25 (`frontend/tests/`); pytest (`tests/`).

**Target Platform**: Desktop browsers, including pages opened directly over
`file://` with no network.

**Project Type**: Web — a Python documentation generator that emits a static
wiki, plus a Vite-built IIFE interface bundle vendored into the generator's
assets.

**Performance Goals**: Panning and zooming stay smooth on the largest diagram
this repository generates (the class diagram, capped at its existing selection
size). Achieved by transforming a wrapper `<div>` — compositor work — rather than
mutating SVG internals, which would force a repaint per frame.

**Constraints**: Zero network requests at read time (constitution 2.2). Generated
Markdown byte-identical (FR-022). Node-click navigation preserved exactly
(FR-010). Diagrams must still render and navigate when the interface bundle fails
to load (FR-024).

**Scale/Scope**: 4 files touched, 1 new. ~150 lines of TypeScript, ~60 lines of
CSS, 4 lines of Jinja. 5 diagram surfaces covered through one shared mechanism.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Assessed against constitution v3.0.0.

| Principle | Applies? | Assessment |
| --- | --- | --- |
| **2.1** Remote engine by default, local mode explicit | No | This feature consumes no AI model. It touches neither embeddings, summarization, nor chat. |
| **2.2** Zero network exposure by default | **Yes — the binding gate** | No CDN, no webfont, no new vendored asset, no runtime fetch. The pan/zoom is written for this project precisely so nothing new has to be fetched or vendored (research Decision 1). FR-023 and SC-007 make this testable, and quickstart step 8 verifies it with DevTools on a `file://` page. |
| **2.3** Automatic fallback only within a configured chain | No | No provider involved. |
| **2.4** Traceability of AI answers | No | No AI-generated content is added or altered. Diagram content is unchanged. |
| **2.5** Incremental re-indexing | **Yes — neutral** | No page's content hash changes, so the impact set is unaffected and no page is needlessly regenerated. The one template edit changes rendered HTML but not `contentMarkdown`, which is what the hash is computed from. |
| **2.6** Minimal infrastructure, local storage | **Yes — neutral** | No new storage of any kind. `data-model.md` records that the feature is entirely in-memory. |
| **2.7** Analysed repository read-only | **Yes — neutral** | No new writes. The only new output bytes are the rebuilt `wiki-ui.{js,css}`, already-existing managed assets in the documentation output directory. |

**Initial gate: PASS.** No violations, so the Complexity Tracking section is
removed rather than left empty.

### Post-Design Re-check (after Phase 1)

Re-evaluated against the produced `research.md`, `data-model.md`, `contracts/`
and `quickstart.md`:

- **2.2 still holds, and is now stronger.** Research Decision 1 rejected
  `svg-pan-zoom` and `panzoom` on this ground among others; Decision 5 rejected
  the `useMaxWidth: false` alternative partly because it would degrade the
  no-bundle path. The contract's § 4 "Unchanged surfaces" states that nothing is
  added to `src/doc_generator/assets/` beyond the rebuilt bundle.
- **2.5 confirmed neutral.** `data-model.md` § "What this feature does not touch"
  enumerates the manifest tables, `PageKind`, the search index and the impact set
  as unchanged.
- **No new gate triggered by the design.** The design added no provider call, no
  table, no persisted artifact, and no network path.

**Post-design gate: PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/034-zoomable-diagrams/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — 9 decisions, all verified against the code
├── data-model.md        # Phase 1 output — in-memory entities and DOM shape
├── quickstart.md        # Phase 1 output — automated + required manual validation
├── checklists/
│   └── requirements.md  # Spec quality checklist (16/16)
├── contracts/
│   └── diagram-viewport.md   # Phase 1 output — enhancer + bootstrap contract
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── lib/
│   │   └── diagramViewport.ts     # NEW — enhanceDiagrams(root), pan/zoom, gesture classification
│   ├── main.tsx                   # MODIFIED — wire the enhancer to wiki:mermaid-rendered + load
│   └── styles.css                 # MODIFIED — viewport, controls, .is-expanded, reduced-motion
└── tests/
    └── diagramViewport.test.ts    # NEW — click-vs-drag threshold first, then zoom/reset/idempotence

src/doc_generator/
├── templates/
│   └── layout.html.jinja          # MODIFIED — lines 67-71: startOnLoad:false + mermaid.run()
└── assets/
    ├── wiki-ui.js                 # REBUILT + COMMITTED (npm run build)
    └── wiki-ui.css                # REBUILT + COMMITTED

tests/integration/                 # MODIFIED — one added assertion each, existing ones untouched
├── test_mermaid_diagram.py
├── test_class_diagram.py
├── test_entry_point_diagram.py
├── test_diagrams_index.py
└── test_prose_wiki_surface.py
```

**Structure Decision**: The repository is already split between a Python
generator (`src/`) and a Vite-built browser bundle (`frontend/`), with the built
artifacts vendored into `src/doc_generator/assets/` and committed. This feature
lives almost entirely on the frontend side of that existing split. The single
Python-side edit is the Mermaid bootstrap in the shared layout template, which
must stay in the page's own inline script so a failed bundle load costs the zoom
and not the diagram (contract § 2, FR-024).

No new directory is introduced: `frontend/src/lib/` already holds the non-React
helpers (`searchIndex.ts`, `apiToken.ts`, `chatApiClient.ts`), which is exactly
what the enhancer is — it owns no React state, mirroring how `TocHighlighter`
deliberately renders `null` and only touches server-rendered DOM.

## Implementation Order

Superseded in detail by [tasks.md](./tasks.md); the shape is:

1. **The viewport install** — `diagramViewport.ts`'s DOM wrapping and idempotent
   sweep, the base CSS, the `layout.html.jinja` bootstrap, and the `main.tsx`
   wiring. All four together, because a viewport that is never installed cannot
   be hand-checked, and the bootstrap is what makes the timing reliable.
2. **Zoom and pan** (US1), then **click-vs-drag** (US2). In that order: there is
   no drag to suppress until panning exists.
3. **Expand** (US3), then **keyboard** (US4).
4. **`npm run build`**, stage the regenerated assets, run both test suites.
5. **The manual pass in `quickstart.md` § 3.** SC-003 and SC-004 are not
   satisfied without it.

An earlier draft of this section put the `layout.html.jinja` bootstrap last. That
was wrong: it would have left every intermediate state un-eyeballable in a
browser for no benefit, since a dispatched event with no listener is harmless.
The bootstrap now lands in the foundational phase.

**US1 alone is not a shippable increment.** Once panning exists, a drag ending
over a node navigates — so shipping zoom without click-suppression actively
breaks behaviour that works today. The two P1 stories are one release boundary.

## Risks

| Risk | Mitigation |
| --- | --- |
| A drag that ends over a node navigates anyway | `preventDefault()` in capture phase, not `stopPropagation()` (research Decision 3). Tested at 2px and 10px, and verified by hand — a spy-based test would pass against a broken implementation. |
| A drag out-and-back navigates on release | `exceededThreshold` latches for the whole gesture; distance is measured from the origin, not the previous position (data-model `GestureState`). |
| `startOnLoad: false` leaves a page with no diagrams | `suppressErrors: true` and dispatch from `.finally()`; the bootstrap stays inline so it does not depend on the bundle. Manual step 9 verifies the no-bundle path. |
| Double enhancement from event + load sweep | `data-viewport-enhanced` marker makes the sweep a no-op (research Decision 8); tested directly. |
| Cleared `max-width` breaks the unenhanced render | It is cleared only at the moment the viewport is installed, so a page whose bundle never loads renders exactly as it does today (research Decision 5). |
| jsdom gaps push unguarded API calls into production | Contract § 1 lists the four forbidden unguarded globals explicitly. |
| Stale committed bundle | Quickstart § 4 checks `git status` on the assets before commit. |
