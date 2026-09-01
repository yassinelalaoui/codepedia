# Diagram Viewport Contract

## Purpose

Define the two interfaces this feature changes: the client-side enhancer module
that installs a pan/zoom viewport around every drawn diagram, and the shared HTML
layout's Mermaid bootstrap that tells it when to run. Unlike most contracts in
this repository, neither side is Python — the only Python edit is four lines of
an inline `<script>` in a Jinja template, and it is specified here because the
enhancer's correctness depends on it exactly.

Nothing in `mermaid_diagram.py`, `html_render.py`, `writer.py`, `links.py` or
`models.py` changes. That is a contract in itself: see "Unchanged surfaces".

---

## 1. Enhancer module (`frontend/src/lib/diagramViewport.ts`)

### `enhanceDiagrams(root: ParentNode = document): number`

Installs a viewport around every drawn, not-yet-enhanced diagram under `root`.
Returns how many diagrams it enhanced on this call.

Expected behavior:

- **Selects** `pre.mermaid` elements under `root` that both (a) contain an `<svg>`
  child and (b) do not carry `data-viewport-enhanced`.
  - A `pre.mermaid` with no `<svg>` is skipped **and left unmarked**, so a
    diagram drawn later is picked up by a later call (FR-014, FR-016).
- **Idempotent.** Calling it twice over the same DOM enhances nothing the second
  time, returns `0`, and leaves any existing `ViewportState` untouched — no
  duplicated controls, no reset view (FR-015). This is what makes the
  event-plus-load-sweep in section 2 safe.
- **Never throws.** A diagram that cannot be enhanced (missing `viewBox`,
  detached node) is skipped; the remaining diagrams are still enhanced
  (FR-016).
- **Returns `0` and does nothing** when `root` contains no matching element.

Per enhanced diagram it MUST:

1. Build the DOM shape defined in `data-model.md` § `EnhancedDiagram`.
2. Move the existing `<svg>` into `div.diagram-canvas` **without modifying its
   internals** — every `<svg:a>` Mermaid emitted survives byte-identical
   (FR-005, FR-010).
3. Clear the inline `max-width` Mermaid stamped on the `<svg>`
   (research Decision 5). Read the intrinsic size from the SVG's `viewBox`
   first; if there is no parseable `viewBox`, skip this diagram entirely rather
   than install a viewport that cannot fit-to-width.
4. Stamp `data-viewport-enhanced="true"` on the `pre.mermaid`.
5. Initialise `ViewportState` to `{ scale: 1, offsetX: 0, offsetY: 0, isExpanded: false }`.

### Interactions each enhanced viewport MUST support

| Input | Behavior | Requirement |
| --- | --- | --- |
| `wheel` over the viewport | Multiply `scale` by `exp(-deltaY * WHEEL_ZOOM_RATE)`, clamped; adjust `offsetX/Y` so the point under the pointer is invariant. Calls `preventDefault()` so the page does not scroll. | FR-002 |
| `pointerdown` + `pointermove` | Pan by the frame-to-frame delta. | FR-003 |
| `click`, **capture phase**, after a gesture that exceeded the threshold | `preventDefault()` **and** `stopPropagation()`. | FR-011 |
| `click`, capture phase, after a gesture below the threshold | Do nothing — the `<a>` navigates natively. | FR-010 |
| `keydown` `+` / `=` | Zoom in by `BUTTON_ZOOM_STEP`, about the viewport centre. | FR-018 |
| `keydown` `-` | Zoom out by `BUTTON_ZOOM_STEP`. | FR-018 |
| `keydown` `0` | Reset to the initial state. | FR-007, FR-018 |
| `keydown` arrow keys | Pan by `KEYBOARD_PAN_PX`; `preventDefault()` so the page does not scroll. | FR-018 |
| `keydown` `Escape` while expanded | Collapse, preserving `scale`/`offsetX`/`offsetY`. | FR-009 |

**The `preventDefault()` requirement on the suppressing click listener is not
interchangeable with `stopPropagation()`.** Mermaid realises `click … href` as a
real `<svg:a xlink:href>` (research Decision 3), so navigation is the anchor's
default action. `stopPropagation()` alone stops the event travelling and lets the
navigation happen anyway. A test that asserts only "a handler was not called"
would pass against an implementation that still navigates.

### Control buttons

Five `<button type="button">` elements, each with the exact `aria-label` in
`data-model.md` § `EnhancedDiagram` (FR-006, FR-019). The expand control's label
swaps between `"Expand diagram"` and `"Collapse diagram"` to match its current
action.

- **Reset** restores exactly `{ scale: 1, offsetX: 0, offsetY: 0 }` (FR-007,
  SC-009).
- **Fit to width** sets `scale = viewportWidth / contentWidth` (clamped) and
  `offsetX = offsetY = 0`, computed on demand from `getBoundingClientRect()` at
  activation — nothing is observed continuously (FR-008, research Decision 6.4).
- **Expand** toggles `.is-expanded` on the viewport element and MUST NOT alter
  `scale` or the offsets (FR-009).

### Environment guards (research Decision 6)

The module MUST NOT call any of the following unguarded, because jsdom 25 — the
test environment — defines none of them:

- `Element.setPointerCapture` / `releasePointerCapture`: feature-guard, and fall
  back to `window`-level `pointermove`/`pointerup` listeners. The fallback also
  satisfies the "drag released outside the viewport" edge case.
- `window.matchMedia`: MUST NOT be called at all. `prefers-reduced-motion` is
  handled purely in CSS (FR-020).
- `ResizeObserver`: MUST NOT be used.

---

## 2. Mermaid bootstrap (`src/doc_generator/templates/layout.html.jinja`)

Replaces the current lines 67-71.

**Before**

```html
<script>
  if (window.mermaid) {
    mermaid.initialize({ startOnLoad: true });
  }
</script>
```

**After** — behavioural contract, not required verbatim:

```html
<script>
  if (window.mermaid) {
    mermaid.initialize({ startOnLoad: false });
    mermaid.run({ suppressErrors: true }).finally(function () {
      document.dispatchEvent(new CustomEvent('wiki:mermaid-rendered'));
    });
  }
</script>
```

Expected behavior:

- `startOnLoad` MUST be `false`. Left `true`, Mermaid draws on `DOMContentLoaded`
  and marks every element `data-processed`, so the later `run()` finds nothing
  and never signals (research Decision 2).
- `suppressErrors: true` MUST be set, so one unparseable diagram does not abort
  the batch (FR-016).
- The dispatch MUST be in `.finally()`, not `.then()`, so the enhancer still runs
  when `run()` rejects (FR-016).
- This block MUST remain in the layout's own inline script and MUST NOT move into
  `wiki-ui.js`: a failed bundle load must cost the zoom, never the diagram
  (FR-024).
- `securityLevel` MUST be left at its default (`strict`). `sandbox` renders into
  an iframe and rewrites link targets to `_top`, which would break both the
  enhancer's DOM access and every click target (research Decision 2).

Event name: `wiki:mermaid-rendered`, dispatched on `document`, no detail payload.

---

## 3. Bundle entry point (`frontend/src/main.tsx`)

- Calls `enhanceDiagrams()` on `document` when `wiki:mermaid-rendered` fires.
- Also calls it once at module evaluation, to cover the case where the bundle
  loads after the event was already dispatched. Idempotence (section 1) is what
  makes running both safe.
- Registered outside the three React `mount()` calls: the enhancer is not a React
  component and owns no React state, mirroring how `TocHighlighter` deliberately
  renders `null` and only touches server-rendered DOM.

---

## 4. Unchanged surfaces (asserted, not assumed)

These are part of the contract because the existing test suite is what proves
them, and it must keep passing **untouched**:

- `mermaid_diagram.py` — every `build_*_mermaid_source` function, including the
  `click <node> href "<href>" "_self"` directive lines, is unchanged.
- `html_render.py:139` — the `<pre class="mermaid">` fence rewrite is unchanged.
- All `*.md.jinja` templates — unchanged. The generated Markdown for a given
  repository is byte-identical before and after (FR-022, SC-006).
- `writer.py` — no new asset. Nothing is added to `src/doc_generator/assets/`
  beyond the rebuilt `wiki-ui.{js,css}` (FR-023).

If a change to this feature requires editing any file in this section, the
approach has drifted from the design and should be re-examined rather than
accommodated.
