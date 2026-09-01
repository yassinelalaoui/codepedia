# Phase 0 Research: Zoomable, Navigable Diagrams

**Feature**: 034-zoomable-diagrams | **Date**: 2026-09-01

All findings below were verified against the code and the vendored artifacts in
this repository, not recalled. The probe used for each is named so it can be
re-run.

---

## Decision 1: Hand-rolled pan/zoom, not a library

**Decision**: Write the pan/zoom in `frontend/src/lib/diagramViewport.ts`
(~150 lines, no dependency).

**Rationale**:

- Constitution 2.2 forbids a runtime network fetch, so any library would have to
  be vendored into `src/doc_generator/assets/` with a `VENDORED.md` entry, the
  way `mermaid.min.js` (3.3 MB) already is. `svg-pan-zoom` is ~30 KB minified for
  behaviour this feature needs a few hundred lines of.
- More decisive: `svg-pan-zoom` installs its own `mousedown`/`mouseup` handling
  on the SVG and has its own notion of what a click is. FR-010 and FR-011 require
  exact control of that boundary, and Mermaid puts real `<a>` elements inside the
  SVG (Decision 3). Two libraries arbitrating the same click is the defect this
  feature exists to avoid.
- `frontend/package.json` shows Mermaid is **not** an npm dependency of the
  frontend at all — it is a raw vendored file exposing `window.mermaid`. So the
  enhancer cannot import Mermaid types and must work off the rendered DOM
  regardless. That removes the main argument for an SVG-aware library.

**Alternatives considered**:

- `svg-pan-zoom`: rejected above.
- `panzoom` (anvaka): smaller, but same click-arbitration problem, plus it
  animates by default, which FR-020 would then have to unpick.
- Native CSS `overflow: auto` scrolling with a CSS `zoom` property: gives panning
  free but no cursor-anchored zoom (FR-002), and `zoom` is not animatable or
  reliably composited.

---

## Decision 2: `startOnLoad: false` + awaited `mermaid.run()`, not a MutationObserver

**Decision**: `templates/layout.html.jinja` changes to
`mermaid.initialize({ startOnLoad: false })` and then calls
`mermaid.run({ suppressErrors: true })`, dispatching a `wiki:mermaid-rendered`
event from a `.finally()`.

**Verified**: `mermaid.run` exists in the vendored 10.9.8 build and accepts both
options — `grep -o "suppressErrors" src/doc_generator/assets/mermaid.min.js`
returns matches, and the default selector is present as
`querySelector:".mermaid"`. Mermaid marks handled elements with
`data-processed`, confirmed by `grep -o "data-processed"`.

**Rationale**:

- `mermaid.run()` returns a promise. That *is* the completion signal FR-014 needs;
  a MutationObserver would have to infer completion from the absence of further
  mutations, which is a guess with a timeout attached.
- The call stays in the page's own inline script rather than moving into
  `wiki-ui.js`, so a failure to load the interface bundle costs the zoom but not
  the diagram (FR-024).
- `suppressErrors: true` plus dispatching from `.finally()` means one unparseable
  diagram cannot leave the rest of the page blank (FR-016). With
  `startOnLoad: true` today, Mermaid already renders each diagram independently;
  the switch must not regress that.
- `startOnLoad` must go to `false`, not stay `true`: leaving it true renders on
  `DOMContentLoaded` and a later `run()` would find every element already carrying
  `data-processed` and skip it, so no completion signal would arrive.

**Alternatives considered**:

- `MutationObserver` on `pre.mermaid`: no completion signal, needs a debounce,
  and fires once per diagram rather than once per page.
- Keeping `startOnLoad: true` and polling for `svg` children: a busy-wait with a
  timeout, strictly worse than an available promise.
- Moving the whole Mermaid invocation into `wiki-ui.js`: breaks FR-024.

**Security level note**: `mermaid.initialize` is left at its default
`securityLevel: "strict"`. Verified relevant because the build contains a
`securityLevel === "sandbox"` branch that renders into an iframe and rewrites the
link target to `_top` — that would break both the click targets and the
enhancer's DOM access. `strict` permits `click … href` (this repository emits
only `href`, never `call`), so nothing needs to change.

---

## Decision 3: Mermaid renders `click … href` as a real `<a>` element

**Finding**: For `click <node> href "<url>" "_self"`, the vendored build wraps the
node shape in an SVG anchor. Extracted verbatim from `mermaid.min.js`:

```js
if (a.link) {
  let v;
  qt().securityLevel === "sandbox" ? v = "_top" : a.linkTarget && (v = a.linkTarget || "_blank"),
  d = i.insert("svg:a").attr("xlink:href", a.link).attr("target", v),
  ...
```

**Consequence — this is the load-bearing detail of the whole feature**:
navigation is the browser's *default action on an anchor*, not a JavaScript
handler. Therefore:

- `stopPropagation()` alone does **not** suppress it. The default action fires at
  the target regardless of whether the event continues to bubble.
- The drag-suppression listener MUST call `preventDefault()`, and must be
  registered in the **capture** phase on the viewport so it runs before the event
  reaches the anchor.

Both are required: `preventDefault()` to kill the navigation, capture phase to
be certain of ordering. A plan that relied on `stopPropagation()` would appear to
work in a unit test that asserts on a spy and fail on a real page.

`class_diagram` nodes use the same `append("svg:a")` path, so the rule holds for
every diagram surface in FR-013.

---

## Decision 4: Transform a wrapper `<div>`, never the SVG

**Decision**: The enhancer wraps the rendered `<svg>` in a canvas `<div>` and
applies `transform: translate(Xpx, Ypx) scale(K)` to that div.

**Rationale**:

- Hit-testing, `<a>` targets and Mermaid's own coordinate system are all
  preserved under a CSS transform on an ancestor: the browser maps pointer
  coordinates back through the transform itself.
- Rewriting the SVG's own `viewBox` or root `transform` attribute puts the
  enhancer in competition with Mermaid's layout, and is where anchor hit areas
  drift away from the shapes they wrap — the exact failure FR-005 and acceptance
  scenario 2.3 forbid.
- A transform on a div is compositor-friendly, so panning stays smooth on a large
  diagram without repainting the SVG.

**Alternatives considered**: mutating `viewBox` (rejected: fights Mermaid's
layout, and anchors drift); `svg.currentScale`/`currentTranslate` (rejected:
only defined on a standalone SVG document, not an inline one).

---

## Decision 5: Neutralise Mermaid's inline `max-width` at enhancement time

**Finding**: Mermaid's sizing helper, verbatim:

```js
$t = function(i, a, u) {
  let d = new Map;
  return u
    ? (d.set("width", "100%"), d.set("style", `max-width: ${a}px;`))
    : (d.set("height", i), d.set("width", a)),
  d
}
```

With `useMaxWidth` true (the default), the SVG gets `width="100%"` and an inline
`style="max-width: {N}px;"`. That inline style is what pins the diagram to the
column and defeats a bounded viewport.

**Decision**: The enhancer clears the inline `max-width` at the moment it
installs the viewport, reading the intrinsic size from the SVG's `viewBox` first.

**Rationale**: Doing it at enhancement time — rather than configuring Mermaid to
stop emitting it — means the pre-enhancement render is byte-for-byte what ships
today, so there is no flash and no regression when the enhancer never runs
(FR-024).

**Alternative considered**: setting `flowchart: { useMaxWidth: false }` (and the
same for `class`, `sequence`, `use-case`) in `mermaid.initialize`. Rejected: it
changes the *unenhanced* render for every reader whose bundle fails to load,
turning a column-fitted diagram into one that overflows the page — a regression
against FR-024 and FR-001 taken together.

---

## Decision 6: jsdom constrains the test design (four concrete gaps)

**Probed** with `node -e` against `jsdom@25` as installed:

| API | jsdom 25 | Consequence |
| --- | --- | --- |
| `PointerEvent` | `undefined` | Tests cannot construct one. |
| `Element.setPointerCapture` | `undefined` | Cannot be called unguarded. |
| `window.matchMedia` | `undefined` | Cannot be called unguarded. |
| `ResizeObserver` | `undefined` | Cannot be called unguarded. |
| `getBoundingClientRect()` | all zeros | Zoom/fit math needs stubbed rects. |

**Decisions that follow**:

1. **The enhancer listens for `pointerdown` / `pointermove` / `pointerup`** (right
   behaviour in a real browser: unifies mouse, pen and trackpad). Tests dispatch
   `new MouseEvent("pointerdown", { clientX, clientY, bubbles: true })` — listeners
   key on the type string, and `MouseEvent` carries the coordinates the handler
   reads. No polyfill, no production compromise.
2. **`setPointerCapture` is feature-guarded**, with a `window`-level
   `pointermove`/`pointerup` fallback. That fallback is not test scaffolding: it
   is also what makes the "drag released outside the viewport" edge case end
   cleanly.
3. **`prefers-reduced-motion` is handled in CSS only** (`@media (prefers-reduced-motion: reduce)`),
   never through `matchMedia` in JS. Satisfies FR-020 with no JS branch and
   nothing to stub.
4. **No `ResizeObserver`.** Fit-to-width is computed on demand, when the control
   is activated, from `getBoundingClientRect()` at that moment — not continuously
   observed. Simpler, and one less unguarded global.
5. **`getBoundingClientRect` is stubbed per test** for the cursor-anchored zoom
   and fit-to-width cases. The click-vs-drag tests need no rect at all, which is
   fortunate: those are the ones that matter most and they stay the simplest.

---

## Decision 7: Expansion as a CSS state, not the Fullscreen API

**Decision**: An `.is-expanded` class on the viewport (`position: fixed; inset: 0`),
dismissed by Escape or by re-activating the control.

**Rationale**: `requestFullscreen()` returns a rejected promise without a user
gesture, behaves inconsistently for pages opened over `file://` — which is a
first-class way this wiki is read — and takes the element out of the page's
stacking context in ways that vary by browser. A class costs nothing and always
works. Escape is wired explicitly because it comes free with the Fullscreen API
but not with a CSS class.

---

## Decision 8: One idempotent sweep, keyed on a marker attribute

**Decision**: `enhanceDiagrams(root)` selects `pre.mermaid` elements that contain
an `<svg>` and do not already carry `data-viewport-enhanced`, enhances each, and
stamps the marker. It is invoked on the `wiki:mermaid-rendered` event and once on
load.

**Rationale**: FR-015 requires that re-invocation neither duplicates controls nor
resets a reader's current zoom. A marker attribute makes the sweep a no-op for
anything already handled, so the "event plus load sweep" belt-and-braces from
Decision 2 cannot double-enhance. Selecting only elements that already contain an
`<svg>` is what enforces FR-014 — an undrawn or failed diagram is simply skipped,
and a later sweep picks it up if it is drawn later.

---

## Decision 9: Zoom bounds and step sizes

**Decision**: scale clamped to `[0.2, 8]`; wheel zoom multiplies by
`exp(-deltaY * 0.0015)` per event; button zoom steps by `1.25×`; arrow-key pan
moves 40 px per press.

**Rationale**: FR-004 requires bounds at both ends. An exponential wheel response
makes zoom feel linear in perceived magnification and behaves correctly for both
mouse wheels (large discrete `deltaY`) and trackpads (many small ones). 0.2 keeps
a very large diagram recoverable at a glance; 8 is past the point where a Mermaid
label is legible, so it never feels clipped. These are constants in one place, so
they are cheap to retune after the hand-verification pass.

---

## Resolved unknowns

No `NEEDS CLARIFICATION` markers remain. Every open question from the Technical
Context was answered by direct inspection:

| Question | Answer | How |
| --- | --- | --- |
| Does the vendored Mermaid expose `run()` with `suppressErrors`? | Yes | grep of `mermaid.min.js` |
| How does Mermaid realise `click … href`? | `<svg:a xlink:href target>` | source extract, Decision 3 |
| Is `stopPropagation()` enough to suppress it? | **No** — `preventDefault()` required | follows from Decision 3 |
| What exactly pins the diagram to the column? | inline `style="max-width: Npx"` | source extract, Decision 5 |
| Is Mermaid an npm dependency of the frontend? | No — vendored global only | `frontend/package.json` |
| Can jsdom drive PointerEvents? | No | `node -e` probe, Decision 6 |
| Which securityLevel is in effect? | default `strict`; `sandbox` would break this | source extract, Decision 2 |
