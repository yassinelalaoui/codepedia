# Feature Specification: Zoomable, Navigable Diagrams in the Generated Wiki

**Feature Branch**: `034-zoomable-diagrams`

**Created**: 2026-09-01

**Status**: Draft

**Input**: User description: "Zoomable, navigable diagrams in the generated wiki. Today every Mermaid diagram in the generated wiki is scaled to the content column width and becomes unreadable as soon as it has more than a handful of nodes. There is no way to zoom in or pan around to read it. Each rendered diagram must sit in a bounded viewport supporting cursor-anchored wheel zoom, drag-to-pan, and visible controls for zoom in, zoom out, reset, fit-to-width, and an expand-to-full-screen toggle, keyboard accessible with a focusable viewport, `+`/`-`/`0` and arrow keys, and an aria-label on every control. This must cover every diagram surface at once. Diagram click-navigation must not break: a drag must never fire a navigation. Zero network per constitution 2.2 - nothing new vendored, a small hand-rolled pan/zoom rather than svg-pan-zoom. Markdown output stays clean: the viewport wrapper belongs in client-side JS in the wiki-ui bundle. Render sequencing moves to `startOnLoad: false` plus an awaited `mermaid.run()` that dispatches a completion event. The enhancer neutralises the inline `max-width` Mermaid stamps on its SVG. Pan/zoom is a CSS transform on a wrapping div, never on SVG internals. Respect prefers-reduced-motion and keep the existing dark-mode tokens. Full-screen uses a CSS class with Escape to exit rather than the Fullscreen API."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read a dense diagram (Priority: P1)

A reader opens a wiki page whose diagram has more nodes than fit legibly in the
content column - the repository class diagram, or the dependency diagram of a
heavily-connected module. Today the diagram is shrunk to the column width and the
node labels are too small to read. The reader wants to magnify a region and move
around it until they have read what they came for.

**Why this priority**: This is the whole defect. Every other story in this feature
is a refinement of, or a guard on, this one. Shipping only this story already
turns unreadable diagrams into readable ones.

**Independent Test**: Generate a wiki for a repository with at least 20 classes,
open the repository class diagram, magnify a region and move around it, and read a
node label that is illegible at the default scale.

**Acceptance Scenarios**:

1. **Given** a rendered diagram larger than its container, **When** the reader
   scrolls the wheel with the pointer over a node, **Then** the diagram magnifies
   about that node - the point under the pointer stays under the pointer - rather
   than about the container's centre.
2. **Given** a magnified diagram, **When** the reader presses the pointer down on
   empty diagram space and moves it, **Then** the diagram follows the pointer, and
   stops following when the pointer is released.
3. **Given** a diagram the reader has magnified and moved, **When** the reader
   activates the reset control, **Then** the diagram returns to exactly the scale
   and position it had on page load.
4. **Given** a diagram wider than its container, **When** the reader activates the
   fit-to-width control, **Then** the whole diagram width is visible inside the
   container.
5. **Given** any diagram, **When** the page is displayed, **Then** the diagram is
   bounded by a visible viewport that does not grow with the diagram and does not
   make the page scroll sideways.

---

### User Story 2 - Follow a node link from inside a zoomed diagram (Priority: P1)

Diagram nodes are links: a node in a dependency diagram leads to that module's own
page. A reader who has zoomed in to find a module then clicks it to go there.
Equally, a reader who has just dragged the diagram across the viewport must not be
thrown onto another page because the drag happened to end over a node.

**Why this priority**: Click-navigation is an existing shipped capability and a
main way readers move between diagrams and pages. A change that silently swallows
those clicks - or fires them on every drag - makes the wiki worse than before this
feature, not better. It is P1 because it is a regression guard on something
readers already rely on, not a nice-to-have.

**Independent Test**: On a generated wiki, click a diagram node without moving the
pointer and confirm the target page opens; then press down on the same node, drag
well clear of it, release, and confirm no navigation happened and the page is
unchanged.

**Acceptance Scenarios**:

1. **Given** a diagram node that links to another page, **When** the reader
   presses and releases on it with no meaningful pointer movement, **Then** the
   linked page opens, exactly as it does today.
2. **Given** the same node, **When** the reader presses on it, moves the pointer
   well past the drag threshold, and releases, **Then** the diagram has panned and
   no navigation occurred.
3. **Given** a reader who has magnified the diagram, **When** they click a node,
   **Then** the correct target page opens - magnification must not misdirect a
   click to a neighbouring node.
4. **Given** a diagram with no linked nodes, **When** the reader drags it, **Then**
   panning behaves identically to a diagram that has links.

---

### User Story 3 - Expand a diagram beyond the content column (Priority: P2)

Even magnified, a wide diagram read through a narrow column means constant
panning. The reader wants to give the diagram the whole window for a moment, read
it, and return to the page.

**Why this priority**: A real improvement for the widest diagrams, but the reader
can already accomplish the task by zooming and panning from story 1. It is a
comfort, not the fix.

**Independent Test**: Open a wide diagram, expand it, confirm it occupies the
window and remains zoomable and pannable, then dismiss it and confirm the page is
where it was.

**Acceptance Scenarios**:

1. **Given** a diagram in its normal viewport, **When** the reader activates the
   expand control, **Then** the diagram fills the window and stays zoomable and
   pannable.
2. **Given** an expanded diagram, **When** the reader presses Escape or activates
   the control again, **Then** the diagram returns to its place in the page, at the
   page's previous scroll position.

---

### User Story 4 - Read a diagram without a mouse (Priority: P2)

A reader navigating by keyboard, or using a screen reader, reaches a diagram and
needs the same zoom and pan the mouse offers, with controls that announce what
they do.

**Why this priority**: Accessibility of a newly-introduced interactive control is
not optional - a diagram that is only readable with a mouse is a diagram some
readers cannot read at all. It is P2 only because the underlying zoom must exist
before it can be driven from the keyboard.

**Independent Test**: With the mouse unused, tab to a diagram, magnify it, move
around it, reset it, and confirm each control announces its purpose to assistive
technology.

**Acceptance Scenarios**:

1. **Given** a page with a diagram, **When** the reader tabs through the page,
   **Then** the diagram viewport receives focus and its focus is visible.
2. **Given** a focused diagram viewport, **When** the reader presses `+`, `-` or
   `0`, **Then** the diagram magnifies, shrinks, or resets respectively.
3. **Given** a focused diagram viewport, **When** the reader presses an arrow key,
   **Then** the diagram moves in that direction.
4. **Given** any diagram control, **When** it is reached by assistive technology,
   **Then** it announces its specific purpose rather than an unlabelled button.

---

### Edge Cases

- **A diagram smaller than its viewport**: no scrollbars, no forced magnification;
  zoom and pan remain available but the default view is the unchanged, whole
  diagram.
- **A diagram that fails to draw**: one unparseable diagram must not prevent every
  other diagram on the page from rendering, and must not prevent the readable ones
  from becoming zoomable.
- **JavaScript unavailable, or the wiki interface bundle fails to load**: diagrams
  must still render and their node links must still work. Losing zoom is
  acceptable; losing the diagram is not.
- **Opened directly from disk**: every behaviour above holds with no network
  access of any kind.
- **A page whose diagrams are re-drawn after the initial load**: the newly drawn
  diagram becomes zoomable too, and an already-enhanced diagram is not enhanced
  twice or reset by the second pass.
- **A reader who has asked for reduced motion**: no animated transitions are
  applied; the controls still work and respond immediately.
- **Dark presentation**: the viewport frame and controls follow the wiki's existing
  light and dark appearances rather than introducing a second, unrelated palette.
- **Very deep magnification or repeated shrinking**: scale is bounded at both ends
  so the diagram can neither vanish nor become an unrecoverable blur.
- **A drag released outside the viewport**: panning ends cleanly; the diagram does
  not stay stuck to the pointer.

## Requirements *(mandatory)*

### Functional Requirements

#### Viewport and transformation

- **FR-001**: Every rendered diagram MUST be presented inside a bounded viewport
  whose height does not grow with the diagram's own size and which never causes the
  page to scroll horizontally.
- **FR-002**: The system MUST support magnifying and shrinking a diagram
  continuously by wheel or trackpad, anchored on the pointer position, so that the
  point under the pointer remains under the pointer.
- **FR-003**: The system MUST support moving a diagram within its viewport by
  pressing and dragging.
- **FR-004**: The system MUST bound magnification at both a minimum and a maximum
  so a diagram can be neither shrunk out of visibility nor magnified past recovery.
- **FR-005**: The system MUST apply magnification and movement without altering the
  diagram's own internal structure, so that node positions, node links and hit
  areas remain mutually consistent at every scale.

#### Controls

- **FR-006**: Every diagram MUST carry visible controls for magnify, shrink, reset,
  fit-to-width, and expand.
- **FR-007**: Reset MUST restore the exact scale and position the diagram had when
  the page finished loading.
- **FR-008**: Fit-to-width MUST scale the diagram so its full width is visible
  within the viewport.
- **FR-009**: Expand MUST give the diagram the full window, keep it zoomable and
  pannable while expanded, and MUST be dismissible by Escape as well as by the
  control itself.

#### Navigation preservation

- **FR-010**: A press-and-release on a linked diagram node with pointer movement
  below a small threshold MUST navigate to that node's target page, as it does
  today.
- **FR-011**: A press-and-release whose pointer movement exceeds that threshold
  MUST be treated as a pan and MUST NOT navigate.
- **FR-012**: The threshold separating a click from a drag MUST be small enough
  that an ordinary click is never mistaken for a drag, and large enough that
  incidental hand movement during a click does not suppress navigation.

#### Coverage and sequencing

- **FR-013**: The behaviour above MUST apply to every diagram the wiki renders -
  per-module dependency diagrams, the repository class diagram, entry-point
  sequence diagrams, the use-case diagram, the feature-page internal-dependency
  diagram, and the class diagram embedded in the home page - through one shared
  mechanism rather than a per-page adaptation.
- **FR-014**: The system MUST attach the viewport only after a diagram has actually
  been drawn, and MUST do so for diagrams drawn after the initial page load as
  well.
- **FR-015**: Attaching the viewport MUST be repeatable without duplicating a
  viewport, stacking controls, or discarding a reader's current zoom and position.
- **FR-016**: A diagram that fails to draw MUST NOT prevent the remaining diagrams
  on the same page from drawing or from becoming zoomable.

#### Accessibility and presentation

- **FR-017**: Each diagram viewport MUST be reachable by keyboard, MUST show a
  visible focus indicator, and MUST expose an accessible description of its
  purpose.
- **FR-018**: A focused viewport MUST respond to `+` and `-` for magnify and
  shrink, `0` for reset, and the arrow keys for movement.
- **FR-019**: Every control MUST carry an accessible label naming its specific
  action.
- **FR-020**: The system MUST honour a reader's reduced-motion preference by
  suppressing transitions.
- **FR-021**: The viewport and its controls MUST use the wiki's existing visual
  presentation, including its light and dark appearances.

#### Output and delivery constraints

- **FR-022**: The Markdown output of every page MUST remain unchanged by this
  feature - the viewport is a property of the rendered wiki, not of the shipped
  Markdown source.
- **FR-023**: The feature MUST make no network request of any kind at read time and
  MUST NOT introduce a new externally-fetched runtime asset, in keeping with
  constitution principle 2.2.
- **FR-024**: If the interactive layer is unavailable for any reason, diagrams MUST
  still render and their node links MUST still navigate.

### Key Entities

- **Diagram viewport**: the bounded region a single diagram is read through. Holds
  the current scale and offset, the bounds those may take, and whether it is
  currently expanded. One per rendered diagram, with no shared state between them,
  so zooming one diagram never moves another.
- **Diagram controls**: the labelled actions attached to one viewport - magnify,
  shrink, reset, fit-to-width, expand - each mapping to a defined transformation of
  that viewport's scale and offset.
- **Pointer gesture**: a press, movement and release over a viewport, classified as
  either a click (navigation is allowed to proceed) or a drag (the diagram moves
  and navigation is suppressed), decided by accumulated movement distance.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reader can read any individual node label in the repository's
  largest generated diagram without leaving the page, using only zoom and pan.
- **SC-002**: 100% of the wiki's diagram surfaces - per-module dependency,
  repository class, entry-point sequence, use-case, feature internal-dependency,
  and the home page's embedded class diagram - are zoomable and pannable.
- **SC-003**: 100% of diagram node links that navigate today still navigate after
  this change, verified on a regenerated wiki rather than in a test harness alone.
- **SC-004**: Zero navigations are triggered by a completed drag gesture across the
  diagram surfaces above.
- **SC-005**: A reader using only a keyboard can magnify, move, and reset every
  diagram, and every control announces its specific action to assistive technology.
- **SC-006**: The generated Markdown output is byte-identical to what the same
  repository produced before this change.
- **SC-007**: A generated wiki opened with no network available behaves identically
  to one opened online, including on a machine that has never fetched an external
  asset.
- **SC-008**: A single undrawable diagram costs only itself: every other diagram on
  the same page still renders and is still zoomable.
- **SC-009**: Reset returns a diagram to its load-time appearance exactly, so a
  reader can always recover a known view.

## Assumptions

Recorded because the feature description settled them in advance; they constrain
the solution rather than being open questions.

- **Interaction layer placement**: the viewport is applied by the wiki's existing
  client-side interface bundle, not by the documentation generator's page templates
  or its HTML rendering step. The diagram itself is only drawn in the reader's
  browser, so the enhancement has to run there regardless, and defining the wrapper
  in the generator as well would specify the same structure twice. This is what
  keeps FR-022 true for free.
- **No new third-party dependency**: the pan and zoom behaviour is written for this
  project rather than adopted from a library. A library would have to be vendored
  to satisfy FR-023, and the candidates carry their own pointer handling, which is
  precisely what FR-010 and FR-011 require exact control of.
- **Drag threshold**: approximately 4 pixels of accumulated pointer movement
  separates a click from a drag (FR-012). Small enough that a deliberate click is
  never reclassified, large enough to absorb hand tremor and trackpad noise.
- **Draw-completion signal**: the diagram library is switched from draw-on-load to
  an explicitly invoked, awaited draw that reports completion, because
  draw-on-load offers no completion signal to attach to (FR-014). The invocation
  stays in the page's own inline script so FR-024 holds when the interface bundle
  does not load, and it suppresses per-diagram errors so FR-016 holds.
- **Scale application**: the transformation is applied to a wrapping element around
  the drawn diagram, not to the diagram's own internal coordinate system, which is
  what preserves link targets and hit areas under magnification (FR-005, FR-010).
- **Width constraint**: the drawn diagram carries an inline maximum width that
  would defeat a bounded viewport; it is neutralised at the moment the viewport is
  installed, so the pre-enhancement appearance is unchanged and there is no visible
  reflow.
- **Expansion mechanism**: expansion is a presentation state of the page rather
  than a request to the browser's full-screen facility, which can be refused and
  which behaves inconsistently for pages opened directly from disk (FR-009).
- **Touch and pinch gestures are out of scope** for this feature. The generated
  wiki is read on a desktop browser; wheel, trackpad, pointer drag and keyboard are
  the input methods covered.
- **Existing diagram content is unchanged**: this feature alters how a diagram is
  read, never which nodes or edges it contains, nor how many are included. Existing
  per-diagram size caps stay as they are.
- **Delivery**: the interface bundle is a build artifact committed to the
  repository and served by the documentation tests, so the rebuilt bundle ships in
  the same change as the source that produced it.
