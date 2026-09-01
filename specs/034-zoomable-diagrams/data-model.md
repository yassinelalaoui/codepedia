# Phase 1 Data Model: Zoomable, Navigable Diagrams

**Feature**: 034-zoomable-diagrams | **Date**: 2026-09-01

This feature persists nothing. There is no database change, no manifest change,
and no new generated file. Every entity below is in-memory browser state, created
when a diagram is enhanced and discarded when the page unloads. The
"persistence" question the template usually asks is answered by FR-022: the
Markdown and the stored manifest are untouched.

---

## Entity: `ViewportState`

The scale and offset one diagram is currently read at. One instance per rendered
diagram, held in the closure of that diagram's enhancer — never in a shared
module-level registry, so zooming one diagram cannot move another (spec Key
Entities).

| Field | Type | Initial | Notes |
| --- | --- | --- | --- |
| `scale` | number | `1` | Clamped to `[MIN_SCALE, MAX_SCALE]` on every write. |
| `offsetX` | number | `0` | CSS pixels, pre-scale translation of the canvas. |
| `offsetY` | number | `0` | CSS pixels. |
| `isExpanded` | boolean | `false` | Drives the `.is-expanded` class. |

**Invariants**

- `MIN_SCALE <= scale <= MAX_SCALE` holds after every operation, including the
  compound wheel case. Enforced in one clamp helper, not at each call site.
- The initial state `(1, 0, 0, false)` is exactly what `reset()` restores
  (FR-007, SC-009). It is a constant, not a snapshot taken at an arbitrary
  moment, so reset cannot drift.
- `isExpanded` is presentation only: expanding and collapsing must not alter
  `scale`, `offsetX` or `offsetY` (spec US3 scenario 2 — the reader keeps their
  view across the transition).

**Derived, never stored**

- The rendered transform string, `translate(${offsetX}px, ${offsetY}px) scale(${scale})`.
- The fit-to-width scale, computed on demand from the viewport and content rects
  (research Decision 6.4 — no `ResizeObserver`, nothing observed continuously).

---

## Entity: `GestureState`

The in-flight classification of one press-move-release over a viewport. Exists
only between `pointerdown` and `pointerup`.

| Field | Type | Initial | Notes |
| --- | --- | --- | --- |
| `originX` | number | pointer `clientX` at press | Reference for the distance test. |
| `originY` | number | pointer `clientY` at press | |
| `lastX` | number | `originX` | Previous move position, for the pan delta. |
| `lastY` | number | `originY` | |
| `exceededThreshold` | boolean | `false` | Latches true; never returns to false within one gesture. |

**State transitions**

```text
idle
  --pointerdown-->            pressing (exceededThreshold = false)
  --pointermove, total movement <  DRAG_THRESHOLD_PX --> pressing
  --pointermove, total movement >= DRAG_THRESHOLD_PX --> dragging (latched)
  --pointerup / pointercancel / window pointerup -->   idle

click event, capture phase, fired after pointerup:
  exceededThreshold === false -> allow  (default action proceeds: the <a> navigates)
  exceededThreshold === true  -> suppress (preventDefault + stopPropagation)
```

**Invariants**

- `exceededThreshold` **latches**. A drag that returns near its origin is still a
  drag; without latching, a reader who drags out and back would navigate on
  release. This is the difference between comparing against the origin and
  comparing against the last position, and it is the reason `originX/Y` and
  `lastX/Y` are separate fields.
- Suppression is decided at `click` time from the gesture that just ended, and
  the flag is cleared after that click is handled — so the next unmoved click on
  the same node navigates normally (US2 scenarios 1 and 2 in sequence).
- Distance is compared squared against `DRAG_THRESHOLD_PX ** 2`; no square root.

---

## Entity: `EnhancedDiagram`

The DOM structure the enhancer installs around one drawn diagram. Not a
JavaScript object — a documented shape, because the CSS and the tests both depend
on it.

```text
pre.mermaid[data-viewport-enhanced="true"]      <- existing element, marker added
└── div.diagram-viewport            tabindex="0" role="group" aria-label=…
    ├── div.diagram-canvas          <- the transform target (research Decision 4)
    │   └── svg                     <- Mermaid's output, inline max-width cleared
    └── div.diagram-controls
        ├── button[aria-label="Zoom in"]
        ├── button[aria-label="Zoom out"]
        ├── button[aria-label="Reset view"]
        ├── button[aria-label="Fit diagram to width"]
        └── button[aria-label="Expand diagram"]   <- label swaps when expanded
```

**Invariants**

- `data-viewport-enhanced` on the `pre.mermaid` is the idempotence key
  (research Decision 8). A sweep skips any element carrying it, so re-invocation
  never duplicates controls nor resets `ViewportState` (FR-015).
- A `pre.mermaid` with no `<svg>` child is **not** enhanced and **not** marked, so
  a diagram drawn later is picked up by a later sweep (FR-014, FR-016).
- The `<svg>` is moved into `div.diagram-canvas` but otherwise unmodified apart
  from clearing the inline `max-width` (research Decision 5). Its internal
  structure — including every `<svg:a>` — is untouched (FR-005).
- Controls are `<button type="button">`, never `<a>`, so they can never be
  confused with a diagram link and never submit anything.

---

## Constants

One module-level block, named so they can be retuned after hand-verification
without hunting through the logic.

| Name | Value | Source |
| --- | --- | --- |
| `DRAG_THRESHOLD_PX` | `4` | Spec Assumptions; FR-012 |
| `MIN_SCALE` | `0.2` | research Decision 9; FR-004 |
| `MAX_SCALE` | `8` | research Decision 9; FR-004 |
| `WHEEL_ZOOM_RATE` | `0.0015` | research Decision 9; applied as `exp(-deltaY * rate)` |
| `BUTTON_ZOOM_STEP` | `1.25` | research Decision 9 |
| `KEYBOARD_PAN_PX` | `40` | research Decision 9; FR-018 |

---

## What this feature does *not* touch

Stated explicitly because the surrounding pipeline has many stateful parts and
none of them are in scope:

- `doc_pages` / `doc_section_narrations` manifest tables — unchanged.
- `PageManifestEntry`, `DocPage`, `PageKind` — unchanged.
- Mermaid *source text* generation in `mermaid_diagram.py` — unchanged. This is
  what keeps the existing Python integration tests passing untouched, which is
  itself the evidence that the viewport stayed client-side.
- `search-index.json` — unchanged.
- The incremental regeneration impact set — unchanged; no page's content hash
  moves because of this feature.
