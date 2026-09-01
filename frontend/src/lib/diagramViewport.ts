/**
 * Pan/zoom viewport around every Mermaid diagram the wiki renders.
 *
 * Written for this project rather than taken from a library, for two reasons.
 * Constitution 2.2 forbids a runtime network fetch, so any dependency would have
 * to be vendored beside `mermaid.min.js`; and every candidate installs its own
 * pointer handling, which is exactly the boundary this module has to control
 * precisely - see `classifyGesture` below.
 *
 * The enhancer never touches Mermaid's API. Mermaid is a vendored global
 * (`window.mermaid`), not an npm dependency of this bundle, so everything here
 * works off the rendered DOM. The one thing the page does supply is a
 * `wiki:mermaid-rendered` event telling us the SVGs exist; `main.tsx` wires it.
 */

/**
 * Pointer movement, in CSS pixels, past which a press-and-release is a drag
 * rather than a click. Small enough that a deliberate click is never
 * reclassified, large enough to absorb hand tremor and trackpad noise.
 */
export const DRAG_THRESHOLD_PX = 4;

/** Scale bounds. Below the minimum a diagram vanishes; above the maximum a
 * Mermaid label has long stopped being legible, so neither end feels clipped. */
export const MIN_SCALE = 0.2;
export const MAX_SCALE = 8;

/**
 * Wheel zoom is exponential in `deltaY` (`exp(-deltaY * rate)`), which is what
 * makes it feel linear in perceived magnification and behave the same for a
 * mouse wheel's large discrete deltas and a trackpad's stream of small ones.
 */
export const WHEEL_ZOOM_RATE = 0.0015;

/** Multiplier per activation of the zoom-in / zoom-out buttons and `+` / `-`. */
export const BUTTON_ZOOM_STEP = 1.25;

/** Pixels moved per arrow-key press. */
export const KEYBOARD_PAN_PX = 40;

/** Marks a `pre.mermaid` this module has already handled, so the sweep is
 * idempotent - see `enhanceDiagrams`. */
const ENHANCED_ATTRIBUTE = "data-viewport-enhanced";

interface ViewportState {
  scale: number;
  offsetX: number;
  offsetY: number;
}

/** What `reset` restores. A constant, not a snapshot taken at some arbitrary
 * moment, so reset cannot drift from the load-time view. */
const INITIAL_STATE: Readonly<ViewportState> = { scale: 1, offsetX: 0, offsetY: 0 };

function clampScale(scale: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
}

/** Intrinsic size, from the `viewBox` Mermaid always emits.
 *
 * Returns null when there is no usable one, which is the signal to skip the
 * diagram entirely: without it `fitToWidth` has no content width to divide by,
 * and a viewport whose fit control cannot work is worse than no viewport. */
function readViewBoxSize(svg: SVGElement): { width: number; height: number } | null {
  const parts = (svg.getAttribute("viewBox") ?? "").trim().split(/[\s,]+/).map(Number);
  if (parts.length !== 4 || parts.some((value) => !Number.isFinite(value))) return null;
  const [, , width, height] = parts;
  return width > 0 && height > 0 ? { width, height } : null;
}

/**
 * Install a pan/zoom viewport around every drawn, not-yet-enhanced diagram
 * under `root`. Returns how many were enhanced by this call.
 *
 * Idempotent, and deliberately so: `main.tsx` both listens for
 * `wiki:mermaid-rendered` and sweeps once on load, because either alone can
 * miss - the event can fire before the bundle parses, and a load-time sweep can
 * run before Mermaid has drawn anything. Running both is only safe because a
 * second pass over the same DOM is a no-op.
 *
 * A `pre.mermaid` with no `<svg>` is skipped *and left unmarked*, so a diagram
 * drawn later is picked up by a later sweep rather than being written off.
 */
export function enhanceDiagrams(root: ParentNode = document): number {
  const candidates = root.querySelectorAll<HTMLElement>(`pre.mermaid:not([${ENHANCED_ATTRIBUTE}])`);
  let enhanced = 0;
  for (const pre of Array.from(candidates)) {
    const svg = pre.querySelector("svg");
    // Not drawn yet. Left unmarked on purpose.
    if (!svg) continue;
    try {
      if (enhanceOne(pre, svg as SVGElement)) enhanced += 1;
    } catch {
      // One diagram that cannot be enhanced must not cost the others their
      // viewport, so the failure is swallowed here rather than at the caller.
    }
  }
  return enhanced;
}

function enhanceOne(pre: HTMLElement, svg: SVGElement): boolean {
  const contentSize = readViewBoxSize(svg);
  if (!contentSize) return false;

  const viewport = document.createElement("div");
  viewport.className = "diagram-viewport";
  viewport.tabIndex = 0;
  viewport.setAttribute("role", "group");
  viewport.setAttribute("aria-label", "Diagram viewport. Zoom and pan to read the diagram.");

  const canvas = document.createElement("div");
  canvas.className = "diagram-canvas";

  const controls = document.createElement("div");
  controls.className = "diagram-controls";

  // The SVG moves wholesale, with its internals untouched: every <a> Mermaid
  // emitted for a `click <node> href` directive has to survive byte for byte,
  // because those are the wiki's cross-page links.
  canvas.appendChild(svg);
  viewport.appendChild(canvas);
  viewport.appendChild(controls);
  pre.appendChild(viewport);

  // Mermaid stamps `style="max-width: Npx"` on the SVG, which is exactly what
  // pins a diagram to the column width. Cleared only now, at install time, so a
  // page whose bundle never loads still renders precisely as it does today.
  svg.style.maxWidth = "";
  svg.style.width = "100%";
  svg.style.height = "100%";

  const state: ViewportState = { ...INITIAL_STATE };
  const applyTransform = (): void => {
    canvas.style.transform =
      `translate(${state.offsetX}px, ${state.offsetY}px) scale(${state.scale})`;
  };
  applyTransform();

  /**
   * Zoom about a point given in viewport-local coordinates, holding the content
   * under that point still.
   *
   * The content point below the cursor is `(local - offset) / scale`; requiring
   * it to be unchanged after the scale changes gives the new offset directly.
   * Solved rather than approximated, because "the thing under the cursor stays
   * under the cursor" is the whole difference between zoom that feels like a map
   * and zoom that feels like a slideshow.
   */
  const zoomAbout = (localX: number, localY: number, factor: number): void => {
    const nextScale = clampScale(state.scale * factor);
    // Clamped to a no-op at the bounds: without this the offset would keep
    // drifting on every further wheel tick while the scale stood still.
    if (nextScale === state.scale) return;
    const contentX = (localX - state.offsetX) / state.scale;
    const contentY = (localY - state.offsetY) / state.scale;
    state.scale = nextScale;
    state.offsetX = localX - contentX * nextScale;
    state.offsetY = localY - contentY * nextScale;
    applyTransform();
  };

  const zoomAboutCentre = (factor: number): void => {
    const rect = viewport.getBoundingClientRect();
    zoomAbout(rect.width / 2, rect.height / 2, factor);
  };

  const reset = (): void => {
    Object.assign(state, INITIAL_STATE);
    applyTransform();
  };

  const fitToWidth = (): void => {
    const rect = viewport.getBoundingClientRect();
    if (rect.width <= 0) return;
    state.scale = clampScale(rect.width / contentSize.width);
    state.offsetX = 0;
    state.offsetY = 0;
    applyTransform();
  };

  const panBy = (deltaX: number, deltaY: number): void => {
    state.offsetX += deltaX;
    state.offsetY += deltaY;
    applyTransform();
  };

  viewport.addEventListener(
    "wheel",
    (event: WheelEvent) => {
      // Without this the page scrolls at the same time as the diagram zooms.
      event.preventDefault();
      const rect = viewport.getBoundingClientRect();
      zoomAbout(
        event.clientX - rect.left,
        event.clientY - rect.top,
        Math.exp(-event.deltaY * WHEEL_ZOOM_RATE),
      );
    },
    // Not passive: `preventDefault` on a wheel listener is the entire point, and
    // browsers treat wheel listeners on an element as passive by default.
    { passive: false },
  );

  // Expansion is a presentation state of the page, not a Fullscreen API call:
  // `requestFullscreen` can be refused without a user gesture and behaves
  // inconsistently for pages opened over file://, which is a first-class way
  // this wiki is read. Deliberately does not touch scale or offset - a reader
  // who expands mid-inspection keeps their view.
  const setExpanded = (expanded: boolean): void => {
    viewport.classList.toggle("is-expanded", expanded);
    const button = controls.querySelector<HTMLButtonElement>("[data-action='expand']");
    if (button) {
      button.setAttribute("aria-label", expanded ? "Collapse diagram" : "Expand diagram");
      button.textContent = expanded ? "⤡" : "⛶";
    }
  };

  viewport.addEventListener("keydown", (event: KeyboardEvent) => {
    switch (event.key) {
      case "+":
      case "=":
        zoomAboutCentre(BUTTON_ZOOM_STEP);
        break;
      case "-":
        zoomAboutCentre(1 / BUTTON_ZOOM_STEP);
        break;
      case "0":
        reset();
        break;
      case "ArrowLeft":
        panBy(KEYBOARD_PAN_PX, 0);
        break;
      case "ArrowRight":
        panBy(-KEYBOARD_PAN_PX, 0);
        break;
      case "ArrowUp":
        panBy(0, KEYBOARD_PAN_PX);
        break;
      case "ArrowDown":
        panBy(0, -KEYBOARD_PAN_PX);
        break;
      case "Escape":
        if (!viewport.classList.contains("is-expanded")) return;
        setExpanded(false);
        break;
      default:
        return;
    }
    // Only for a key this viewport actually handled: an unhandled key must keep
    // its normal meaning, and arrows in particular must not scroll the page out
    // from under a reader who is panning.
    event.preventDefault();
  });

  installPanAndClickHandling(viewport, panBy);
  buildControls(controls, {
    zoomAboutCentre,
    reset,
    fitToWidth,
    toggleExpanded: () => setExpanded(!viewport.classList.contains("is-expanded")),
  });

  pre.setAttribute(ENHANCED_ATTRIBUTE, "true");
  return true;
}

interface ControlActions {
  zoomAboutCentre: (factor: number) => void;
  reset: () => void;
  fitToWidth: () => void;
  toggleExpanded: () => void;
}

function buildControls(container: HTMLElement, actions: ControlActions): void {
  // `aria-label` rather than the glyph, because "+" and "0" announce as
  // punctuation. The glyph is what a sighted reader sees; the label is what
  // everyone else gets.
  const definitions: ReadonlyArray<{
    label: string;
    glyph: string;
    action?: string;
    run: () => void;
  }> = [
    { label: "Zoom in", glyph: "+", run: () => actions.zoomAboutCentre(BUTTON_ZOOM_STEP) },
    { label: "Zoom out", glyph: "−", run: () => actions.zoomAboutCentre(1 / BUTTON_ZOOM_STEP) },
    { label: "Reset view", glyph: "⟲", run: actions.reset },
    { label: "Fit diagram to width", glyph: "⤢", run: actions.fitToWidth },
    { label: "Expand diagram", glyph: "⛶", action: "expand", run: actions.toggleExpanded },
  ];
  for (const definition of definitions) {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("aria-label", definition.label);
    if (definition.action) button.dataset.action = definition.action;
    button.textContent = definition.glyph;
    button.addEventListener("click", (event) => {
      // The viewport's own capture-phase click handler must not see this as a
      // diagram click, and the page must not scroll to the button.
      event.stopPropagation();
      definition.run();
    });
    container.appendChild(button);
  }
}

/**
 * Drag-to-pan, and the click/drag distinction that protects diagram links.
 *
 * Mermaid realises a `click <node> href "..."` directive as a real
 * `<a xlink:href>` wrapping the node, so navigation is the anchor's *default
 * action* - not a handler this module could simply decline to call. Suppressing
 * a drag therefore needs `preventDefault()`, in the capture phase, before the
 * event reaches the anchor. `stopPropagation()` alone would let every drag
 * navigate.
 */
function installPanAndClickHandling(
  viewport: HTMLElement,
  panBy: (deltaX: number, deltaY: number) => void,
): void {
  let pointerIsDown = false;
  let originX = 0;
  let originY = 0;
  let lastX = 0;
  let lastY = 0;
  let exceededThreshold = false;

  const endGesture = (): void => {
    pointerIsDown = false;
    viewport.classList.remove("is-grabbing");
    window.removeEventListener("pointermove", onWindowMove);
    window.removeEventListener("pointerup", onWindowUp);
  };

  function onMove(event: MouseEvent): void {
    if (!pointerIsDown) return;
    const dx = event.clientX - originX;
    const dy = event.clientY - originY;
    // Measured from the gesture's origin, never from the previous position, and
    // latched once set: a drag that wanders away and comes back is still a drag,
    // and releasing it over a node must not navigate.
    if (!exceededThreshold && dx * dx + dy * dy >= DRAG_THRESHOLD_PX * DRAG_THRESHOLD_PX) {
      exceededThreshold = true;
      viewport.classList.add("is-grabbing");
    }
    panBy(event.clientX - lastX, event.clientY - lastY);
    lastX = event.clientX;
    lastY = event.clientY;
  }

  function onWindowMove(event: Event): void {
    onMove(event as MouseEvent);
  }

  function onWindowUp(): void {
    endGesture();
  }

  viewport.addEventListener("pointerdown", (event: MouseEvent) => {
    pointerIsDown = true;
    exceededThreshold = false;
    originX = event.clientX;
    originY = event.clientY;
    lastX = event.clientX;
    lastY = event.clientY;
    // jsdom defines neither of these, and an old browser may not either. The
    // window-level fallback below is not merely a stand-in: it is also what ends
    // a drag cleanly when the pointer is released outside the viewport.
    const target = viewport as HTMLElement & { setPointerCapture?: (id: number) => void };
    const pointerId = (event as MouseEvent & { pointerId?: number }).pointerId;
    if (typeof target.setPointerCapture === "function" && typeof pointerId === "number") {
      try {
        target.setPointerCapture(pointerId);
      } catch {
        // A pointer id the browser no longer recognises; the fallback covers it.
      }
    }
    window.addEventListener("pointermove", onWindowMove);
    window.addEventListener("pointerup", onWindowUp);
  });

  viewport.addEventListener("pointermove", onMove);
  viewport.addEventListener("pointerup", endGesture);
  viewport.addEventListener("pointercancel", endGesture);

  viewport.addEventListener(
    "click",
    (event: MouseEvent) => {
      // A control is never a diagram link, so it is never suppressed. The flag
      // has to survive from `pointerup` to the `click` that follows it - that is
      // the whole mechanism - which means without this exclusion the first
      // control pressed after a drag would be swallowed instead of acted on.
      if ((event.target as Element | null)?.closest?.(".diagram-controls")) return;
      if (!exceededThreshold) return;
      // Both, and in this order of importance: preventDefault stops the anchor
      // navigating, stopPropagation stops anything else acting on the click.
      event.preventDefault();
      event.stopPropagation();
      // Cleared here, so the next unmoved click on the same node navigates.
      exceededThreshold = false;
    },
    true,
  );
}
