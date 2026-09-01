---

description: "Task list for 034-zoomable-diagrams"
---

# Tasks: Zoomable, Navigable Diagrams in the Generated Wiki

**Input**: Design documents from `/specs/034-zoomable-diagrams/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/diagram-viewport.md](./contracts/diagram-viewport.md), [quickstart.md](./quickstart.md)

**Tests**: Included. The specification requires them explicitly (spec § Testing,
quickstart § 1), and SC-003/SC-004 additionally require a manual pass that no
automated test can replace.

**Organization**: Grouped by user story. Note the honest caveat in
[Dependencies](#dependencies--execution-order): US1 and US2 both live in
`diagramViewport.ts`, so they are separable in *review* and in *test*, but not
genuinely parallel in *authoring*.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different file, no dependency on incomplete work
- **[Story]**: US1..US4, mapping to the user stories in spec.md

## Path Conventions

Web project, per plan.md § Structure Decision: browser code in `frontend/src/`,
its tests in `frontend/tests/`, generator code and its tests in
`src/doc_generator/` and `tests/`.

---

## Phase 1: Setup

**Purpose**: Create the two new files and the shared constants, so every later
task has somewhere to land.

- [X] T001 Create `frontend/src/lib/diagramViewport.ts` exporting the constants block from data-model.md § Constants (`DRAG_THRESHOLD_PX = 4`, `MIN_SCALE = 0.2`, `MAX_SCALE = 8`, `WHEEL_ZOOM_RATE = 0.0015`, `BUTTON_ZOOM_STEP = 1.25`, `KEYBOARD_PAN_PX = 40`) and a stub `enhanceDiagrams(root: ParentNode = document): number` returning `0`
- [X] T002 [P] Create `frontend/tests/diagramViewport.test.ts` with a `firePointer(el, type, x, y)` helper that dispatches `new MouseEvent(type, { clientX, clientY, bubbles: true })` — jsdom 25 has no `PointerEvent` constructor (research Decision 6) — and a `buildDiagram()` fixture producing `<pre class="mermaid"><svg viewBox="0 0 800 600"><a xlink:href="../modules/x.html"><rect/></a></svg></pre>`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Install a viewport around a drawn diagram, and make the browser tell
us when to do it. Nothing in any user story is reachable until a viewport exists.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests

- [X] T003 [P] In `frontend/tests/diagramViewport.test.ts`, add failing tests for the sweep contract (contracts § 1): (a) `enhanceDiagrams()` builds the `EnhancedDiagram` DOM shape from data-model.md; (b) a second call returns `0` and leaves one control bar (FR-015); (c) a `pre.mermaid` with no `<svg>` is skipped **and left unmarked**, then enhanced by a later sweep once an `<svg>` is added (FR-014); (d) a diagram with an unparseable `viewBox` is skipped while a sibling valid diagram is still enhanced (FR-016)
- [X] T004 [P] In `tests/integration/test_wiki_ui_assets.py`, add a failing assertion that the rendered layout contains `startOnLoad: false` and a `mermaid.run(` call, and does **not** contain `startOnLoad: true` (contracts § 2)

### Implementation

- [X] T005 Implement `ViewportState` in `frontend/src/lib/diagramViewport.ts` — `{ scale, offsetX, offsetY, isExpanded }` per closure, a single `clampScale()` helper enforcing `[MIN_SCALE, MAX_SCALE]`, and an `applyTransform()` writing `translate(${offsetX}px, ${offsetY}px) scale(${scale})` to the canvas element
- [X] T006 Implement the DOM builder in `frontend/src/lib/diagramViewport.ts` — wrap the existing `<svg>` in `div.diagram-canvas` inside `div.diagram-viewport[tabindex="0"][role="group"][aria-label]`, appending an empty `div.diagram-controls`. Move the `<svg>` node without touching its internals, so every `<svg:a>` survives (FR-005)
- [X] T007 Implement `viewBox` reading and inline `max-width` clearing in `frontend/src/lib/diagramViewport.ts` — read intrinsic size from the SVG's `viewBox` first; if absent or unparseable, skip the diagram entirely rather than install a viewport that cannot fit-to-width (research Decision 5)
- [X] T008 Implement the `enhanceDiagrams(root)` sweep in `frontend/src/lib/diagramViewport.ts` — select `pre.mermaid` that contain an `<svg>` and lack `data-viewport-enhanced`, enhance each inside a `try/catch` so one failure cannot abort the batch, stamp the marker, return the count. Makes T003 pass
- [X] T009 [P] Add the base viewport CSS to `frontend/src/styles.css`, replacing the current `pre.mermaid` rule at line 463 — bounded height, `overflow: hidden`, `touch-action: none` on the viewport, `transform-origin: 0 0` on the canvas, using the existing `--surface` / `--border` / `--ink-soft` tokens so light and dark both follow (FR-021)
- [X] T010 [P] Change the Mermaid bootstrap in `src/doc_generator/templates/layout.html.jinja` (lines 67-71) to `startOnLoad: false` plus `mermaid.run({ suppressErrors: true }).finally(...)` dispatching `wiki:mermaid-rendered` on `document`. Leave `securityLevel` at its default. Keep the block inline — it must not move into `wiki-ui.js` (FR-024). Makes T004 pass
- [X] T011 [P] Wire the enhancer in `frontend/src/main.tsx` — call `enhanceDiagrams()` on the `wiki:mermaid-rendered` event and once at module evaluation, registered outside the three React `mount()` calls

**Checkpoint**: A generated wiki shows every diagram inside a bounded viewport.
Nothing zooms yet, and node links still navigate exactly as before.

---

## Phase 3: User Story 1 — Read a dense diagram (Priority: P1) 🎯 MVP

**Goal**: Magnify and move a diagram until an illegible label can be read.

**Independent Test**: Open the repository class diagram, wheel-zoom onto a node,
drag the canvas, and read a label that is illegible at the default scale. Reset
returns the load-time view; fit-to-width shows the whole diagram width.

### Tests for User Story 1

> Write these first and confirm they fail.

- [X] T012 [P] [US1] In `frontend/tests/diagramViewport.test.ts`, add failing tests for cursor-anchored zoom: with `getBoundingClientRect` stubbed (jsdom returns zeros — research Decision 6), a `wheel` at a known offset leaves the point under the pointer invariant (FR-002), and the event's default is prevented so the page does not scroll
- [X] T013 [P] [US1] In `frontend/tests/diagramViewport.test.ts`, add failing tests for scale bounds: repeated wheel-in and wheel-out leave `scale` within `[0.2, 8]` (FR-004)
- [X] T014 [P] [US1] In `frontend/tests/diagramViewport.test.ts`, add failing tests for pan and reset: a pointer drag translates the canvas by the pointer delta (FR-003); after zoom and pan, reset yields exactly `translate(0px, 0px) scale(1)` (FR-007, SC-009)
- [X] T015 [P] [US1] In `frontend/tests/diagramViewport.test.ts`, add a failing test for fit-to-width: with stubbed viewport and content rects, activating the control sets `scale = viewportWidth / contentWidth` clamped, and zeroes both offsets (FR-008)

### Implementation for User Story 1

- [X] T016 [US1] Implement cursor-anchored wheel zoom in `frontend/src/lib/diagramViewport.ts` — multiply `scale` by `exp(-deltaY * WHEEL_ZOOM_RATE)`, clamp, and adjust `offsetX/offsetY` so the point under the pointer is invariant; call `preventDefault()`. Makes T012, T013 pass
- [X] T017 [US1] Implement drag-to-pan in `frontend/src/lib/diagramViewport.ts` — `pointerdown`/`pointermove`/`pointerup` translating by the frame-to-frame delta. Guard `setPointerCapture` behind a `typeof` check and fall back to `window`-level `pointermove`/`pointerup` listeners, which is also what makes a drag released outside the viewport end cleanly (research Decision 6.2). Makes T014's pan case pass
- [X] T018 [US1] Add the zoom-in, zoom-out, reset and fit-to-width buttons to `div.diagram-controls` in `frontend/src/lib/diagramViewport.ts` as `<button type="button">` with the exact `aria-label` values from data-model.md; wire zoom-in/out to `BUTTON_ZOOM_STEP` about the viewport centre, reset to the initial state constant, and fit-to-width to an on-demand `getBoundingClientRect()` computation — no `ResizeObserver` (research Decision 6.4). Makes T014's reset case and T015 pass
- [X] T019 [P] [US1] Style the control bar in `frontend/src/styles.css` — positioned over the viewport, using existing tokens, with `grab`/`grabbing` cursors on the canvas

**Checkpoint**: User Story 1 is fully functional. Diagrams zoom, pan, reset and
fit. Node clicks still work because nothing has intercepted them yet — US2 makes
that hold once dragging exists.

---

## Phase 4: User Story 2 — Follow a node link from a zoomed diagram (Priority: P1)

**Goal**: A click navigates; a drag never does.

**Independent Test**: Click a node without moving the pointer → the target page
opens. Press the same node, drag well clear, release → nothing navigates.

**⚠️ The trap**: Mermaid renders `click … href` as a real `<svg:a xlink:href>`
(research Decision 3), so navigation is the anchor's **default action**.
`stopPropagation()` alone does not stop it. Assert on `preventDefault()`, never
on an uncalled handler spy — a spy-based test passes against an implementation
that still navigates.

**Scope note**: only two of the five diagram surfaces carry click targets at all
— module dependency diagrams and the section/feature internal-dependency diagram
(`mermaid_diagram.py` lines 75 and 315). The class, sequence and use-case
diagrams emit no `click` directives, so this story's regression risk is confined
to those two surfaces.

### Tests for User Story 2

- [X] T020 [P] [US2] In `frontend/tests/diagramViewport.test.ts`, add a failing test: press, move **2px**, release, then click the anchor → `preventDefault()` was NOT called and the anchor's default is allowed (FR-010)
- [X] T021 [P] [US2] In `frontend/tests/diagramViewport.test.ts`, add a failing test: press, move **10px**, release, then click → `preventDefault()` WAS called (FR-011)
- [X] T022 [P] [US2] In `frontend/tests/diagramViewport.test.ts`, add a failing test for threshold latching: press, drag 40px away, drag back to the origin, release, then click → `preventDefault()` WAS called. Distance is measured from the gesture origin, not the previous position (data-model § `GestureState`)
- [X] T023 [P] [US2] In `frontend/tests/diagramViewport.test.ts`, add a failing test that the flag clears: after a suppressed drag-click, a second unmoved click on the same node is NOT suppressed

### Implementation for User Story 2

- [X] T024 [US2] Implement `GestureState` in `frontend/src/lib/diagramViewport.ts` — record `originX/originY` at `pointerdown`, compare squared distance against `DRAG_THRESHOLD_PX ** 2` on each `pointermove`, and **latch** `exceededThreshold` once exceeded. Makes T022 pass
- [X] T025 [US2] Add a **capture-phase** `click` listener on the viewport in `frontend/src/lib/diagramViewport.ts` that calls `preventDefault()` **and** `stopPropagation()` when `exceededThreshold` is set, then clears the flag. Makes T020, T021, T023 pass
- [X] T026 [P] [US2] Add one assertion that `click … href` directives still reach the rendered page to `tests/integration/test_mermaid_diagram.py` and `tests/integration/test_section_pages.py` — and to those two only. Verified against `src/doc_generator/mermaid_diagram.py`: only `build_mermaid_source` (line 75, module dependency diagrams) and `build_section_diagram_mermaid_source` (line 315, section/feature pages) emit `click` directives. The class, sequence and use-case builders emit none, so there is no click-navigation to preserve on those three surfaces. **Do not modify any existing assertion** — their passing untouched is the evidence the viewport stayed client-side (FR-022, contracts § 4)

**Checkpoint**: Both P1 stories complete. This is the shippable increment.

---

## Phase 5: User Story 3 — Expand beyond the content column (Priority: P2)

**Goal**: Give a wide diagram the whole window, then return to the page.

**Independent Test**: Expand a wide diagram, confirm it fills the window and
stays zoomable, dismiss it, confirm the page is where it was.

### Tests for User Story 3

- [X] T027 [P] [US3] In `frontend/tests/diagramViewport.test.ts`, add failing tests: activating expand toggles `.is-expanded` and swaps the control's `aria-label` to `"Collapse diagram"`; Escape collapses it; and neither transition alters `scale`, `offsetX` or `offsetY` (FR-009, data-model invariant)

### Implementation for User Story 3

- [X] T028 [US3] Add the expand control and its toggle logic to `frontend/src/lib/diagramViewport.ts`, plus a `keydown` Escape handler that collapses without touching the transform. Makes T027 pass
- [X] T029 [P] [US3] Add the `.diagram-viewport.is-expanded` rule to `frontend/src/styles.css` — `position: fixed; inset: 0`, above the shell's stacking context, with a solid token-based background so page content does not show through

**Checkpoint**: US1, US2 and US3 all work independently.

---

## Phase 6: User Story 4 — Read a diagram without a mouse (Priority: P2)

**Goal**: Keyboard parity with the mouse, and controls that announce themselves.

**Independent Test**: With the mouse unused, tab to a diagram, magnify, move,
reset, and confirm each control announces its purpose.

### Tests for User Story 4

- [X] T030 [P] [US4] In `frontend/tests/diagramViewport.test.ts`, add failing tests for the keyboard map: `+`/`=` zooms in, `-` zooms out, `0` resets, and the four arrow keys pan by `KEYBOARD_PAN_PX`, with `preventDefault()` called on the arrows so the page does not scroll (FR-018)
- [X] T031 [P] [US4] In `frontend/tests/diagramViewport.test.ts`, add a failing test that the viewport carries `tabindex="0"`, `role="group"` and a non-empty `aria-label`, and that all five controls carry their exact `aria-label` values (FR-017, FR-019)

### Implementation for User Story 4

- [X] T032 [US4] Implement the `keydown` handler in `frontend/src/lib/diagramViewport.ts` for `+`, `=`, `-`, `0` and the arrow keys, reusing the same zoom and pan helpers the controls use. Makes T030 pass
- [X] T033 [P] [US4] Add a visible `:focus-visible` style for the viewport and its controls in `frontend/src/styles.css`, consistent with the existing `a:focus-visible, button:focus-visible` rule at line 94

**Checkpoint**: All four user stories are independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T034 [P] Add the `@media (prefers-reduced-motion: reduce)` block to `frontend/src/styles.css` suppressing control transitions. CSS only — the module must never call `matchMedia`, which jsdom does not define (FR-020, research Decision 6.3)
- [X] T035 [P] Verify no unguarded use of `setPointerCapture`, `matchMedia` or `ResizeObserver` in `frontend/src/lib/diagramViewport.ts` (contracts § 1 Environment guards)
- [X] T036 Run `npm run build` in `frontend/` and stage the regenerated `src/doc_generator/assets/wiki-ui.js` and `wiki-ui.css` — they are committed build artifacts and the Python tests serve them (quickstart § 4)
- [X] T037 Run `cd frontend && npm test` — all suites green
- [X] T038 Run `pytest --basetemp=<scratchpad> -p no:cacheprovider`. Existing diagram-test assertions must pass **unmodified**. Result: **668 passed, 0 failed** — including `test_config_before_any_provider_reachable_still_reports_without_failing`, which an earlier note wrongly recorded as a known baseline failure
- [ ] T039 **(OPEN - requires a human at a browser)** Execute the manual pass in [quickstart.md](./quickstart.md) § 3 steps 1-10 on a regenerated wiki. **Required, not optional**: SC-003 and SC-004 cannot be satisfied by any headless test, because whether Mermaid's own anchor still fires under a transformed ancestor is not something jsdom can answer
- [X] T040 Confirm FR-022 by diffing the generated Markdown against a pre-change build: `diff -r docs-before/ docs-after/ --exclude='*.html' --exclude=assets` must report no differences (SC-006)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no dependencies
- **Phase 2 (Foundational)**: depends on Phase 1 — **blocks every user story**
- **Phases 3-6 (User Stories)**: all depend on Phase 2
- **Phase 7 (Polish)**: depends on every story you intend to ship

### User Story Dependencies — read this before planning parallel work

The template's usual promise, that stories can be built in parallel by different
people, **does not hold cleanly here**, and pretending otherwise would produce
merge conflicts rather than throughput:

- **US1, US2, US3 and US4 all write to the same file**, `diagramViewport.ts`.
  They are independently *testable* and independently *reviewable*, and each is a
  real increment — but they are not independently *authorable* in parallel.
- **US2 depends on US1 in practice**, not just in priority. There is no drag to
  suppress until T017 exists. Sequencing US1 → US2 is a genuine dependency, not a
  priority preference.
- **US3 and US4 are independent of each other** and of US2 once US1 has landed.

The honest parallel unit here is *file*, not *story*: the CSS tasks and the
Python-side tasks can proceed alongside the TypeScript.

### Parallel Opportunities

Genuinely parallel, because they touch different files:

- **T009** (`styles.css`), **T010** (`layout.html.jinja`), **T011** (`main.tsx`)
  after T008 lands
- **T019**, **T029**, **T033**, **T034** — all `styles.css`; parallel with any
  TypeScript task, sequential among themselves
- **T026** (five Python test files) — parallel with everything on the frontend
- All `[P]` test-writing tasks within one phase, since they append independent
  cases to the same new test file and can be authored before the implementation

Not parallel, despite appearances: T005-T008, T016-T018, T024-T025, T028, T032 —
one file, `diagramViewport.ts`.

---

## Parallel Example: after Foundational implementation lands

```bash
# Three different files, no shared state:
Task: "T009 base viewport CSS in frontend/src/styles.css"
Task: "T010 Mermaid bootstrap in src/doc_generator/templates/layout.html.jinja"
Task: "T011 enhancer wiring in frontend/src/main.tsx"
```

---

## Implementation Strategy

### MVP scope

**Phases 1, 2, 3 and 4** — that is, both P1 stories. US1 alone is *not* a
shippable MVP here: once T017 introduces dragging, a drag that ends over a node
navigates, so shipping US1 without US2 actively breaks existing behaviour. The
two P1 stories are one release boundary.

1. Complete Phase 1 + Phase 2 → every diagram sits in a viewport, nothing has
   changed behaviourally
2. Complete Phase 3 → diagrams zoom and pan
3. Complete Phase 4 → clicks and drags are correctly distinguished
4. **STOP and VALIDATE**: quickstart § 3 steps 1-2, on a real wiki
5. Ship

### Incremental delivery

- MVP (above) → validate → ship
- Add US3 (expand) → validate → ship
- Add US4 (keyboard) → validate → ship
- Phase 7 before any of these reaches a commit: T036 must run or the committed
  bundle goes stale

---

## Notes

- `[P]` = different file, no dependency on incomplete work
- Most of this feature is one 150-line module; the task count is high because the
  behaviours are small and separately testable, not because the surface is wide
- Verify each test fails before implementing against it — particularly T020-T023,
  where a wrong assertion passes against broken code
- Commit after each checkpoint; T036 (rebuild the bundle) belongs in any commit
  that touched `frontend/src`
