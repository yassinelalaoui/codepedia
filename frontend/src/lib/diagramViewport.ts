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

/** Scale bounds. Below the minimum a diagram vanishes; the maximum is set by
 * what stays *readable*, not by what stays sharp - the SVG is still re-rendered
 * from its vector geometry far beyond this (verified crisp at 50x in Chrome),
 * so the ceiling only has to leave room for the 1000%-and-beyond inspection
 * this viewport exists to support. */
export const MIN_SCALE = 0.2;
export const MAX_SCALE = 16;

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

/** The identity view. Only the starting point and the fallback `fitToContain`
 * degrades to when the viewport has no measurable size yet - what `reset`
 * actually restores is that recomputed fit, never a snapshot, so reset cannot
 * drift from the load-time view. */
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
  // `diagram-viewport` itself is not a style, it is the hook this module and the
  // test suite query by; the utilities after it are the style. Same for the
  // `is-expanded` / `is-grabbing` markers, which JavaScript toggles and which
  // are therefore expressed as arbitrary variants rather than as utilities that
  // would have to be added and removed by hand.
  viewport.className = [
    "diagram-viewport relative h-[460px] max-h-[70vh] overflow-hidden",
    "bg-surface border border-line rounded-md",
    // The viewport owns wheel and drag gestures; without `touch-none` the
    // browser also scrolls the page and pans the diagram at the same time.
    "touch-none cursor-grab [&.is-grabbing]:cursor-grabbing",
    "focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2",
    // Expanded is a presentation state of the page, not the Fullscreen API,
    // which can be refused and behaves inconsistently over file://.
    "[&.is-expanded]:fixed [&.is-expanded]:inset-0 [&.is-expanded]:z-50",
    "[&.is-expanded]:h-auto [&.is-expanded]:max-h-none [&.is-expanded]:rounded-none",
    // Opaque, so page content cannot show through behind the diagram.
    "[&.is-expanded]:bg-page",
  ].join(" ");
  viewport.tabIndex = 0;
  viewport.setAttribute("role", "group");
  viewport.setAttribute("aria-label", "Diagram viewport. Zoom and pan to read the diagram.");

  const canvas = document.createElement("div");
  // Transform target. Deliberately a wrapper div rather than the SVG itself:
  // hit-testing, <a> targets and Mermaid's coordinate system all survive a
  // transform on an ancestor, whereas rewriting the SVG's own transform is where
  // anchor hit areas drift away from the shapes they wrap. Measured, not
  // assumed: scaling this wrapper renders identically to scaling the <svg>.
  //
  // NEVER give this element a will-change hint for the transform property. (The
  // utility is not named literally anywhere in this file on purpose: Tailwind's
  // scanner reads comments too, and naming it would emit the very rule this
  // paragraph exists to keep out of the stylesheet.) It promotes this wrapper to its own
  // composited layer, and a composited layer is rastered once at the scale it
  // was created at - 1 - and thereafter *stretched* by the compositor on every
  // transform change instead of the SVG being re-rendered from its vector
  // geometry. That is the whole of the blur this viewport used to suffer:
  // measured in Chrome 152 at dpr 1, zooming to 20x drove the rendered frame's
  // Laplacian variance from 338 down to 1.1 and left it there however long the
  // page was given to settle. Removing that one declaration, changing nothing
  // else, put it back to 338 on the spot. It bought no measurable pan
  // performance to trade against that.
  //
  // `[&>svg]:block` styles Mermaid's own <svg>, which nothing can put a class
  // on; its width and height are set in pixels from the viewBox further down.
  canvas.className = "diagram-canvas absolute inset-0 origin-top-left [&>svg]:block";

  const controls = document.createElement("div");
  controls.className = [
    "diagram-controls absolute top-2 right-2 flex gap-1 p-1",
    "bg-[color-mix(in_srgb,var(--surface)_88%,transparent)]",
    "border border-line rounded-sm shadow-1",
  ].join(" ");

  // The SVG moves wholesale, with its internals untouched: every <a> Mermaid
  // emitted for a `click <node> href` directive has to survive byte for byte,
  // because those are the wiki's cross-page links.
  canvas.appendChild(svg);
  viewport.appendChild(canvas);
  viewport.appendChild(controls);
  pre.appendChild(viewport);

  // Mermaid stamps `width="100%"` and `style="max-width: Npx"` on the SVG, which
  // between them pin a diagram to the column width. Cleared only now, at install
  // time, so a page whose bundle never loads still renders precisely as it does
  // today.
  //
  // They are replaced by the viewBox's own dimensions in CSS pixels rather than
  // by percentages. A percentage-sized SVG is laid out at the viewport's
  // dimensions and its `preserveAspectRatio` then letterboxes the viewBox inside
  // that box, which silently pre-scales the diagram before `state.scale` is
  // applied at all - so `state.scale` stopped being a magnification factor and
  // every consumer of it inherited the error. `fitToWidth` was the visible
  // casualty: measured in Chrome, it left a 1200x800 diagram 432px wide inside a
  // 720px viewport instead of filling it. At one viewBox unit per CSS pixel the
  // letterbox is gone and scale means exactly what it says.
  //
  // The viewBox is read but never written: it stays the authoritative coordinate
  // system, which is what keeps every <a xlink:href> and Mermaid-bound onclick
  // hit-testing against the geometry it was drawn with.
  svg.removeAttribute("width");
  svg.removeAttribute("height");
  svg.style.maxWidth = "";
  svg.style.width = `${contentSize.width}px`;
  svg.style.height = `${contentSize.height}px`;

  const state: ViewportState = { ...INITIAL_STATE };
  const applyTransform = (): void => {
    canvas.style.transform =
      `translate(${state.offsetX}px, ${state.offsetY}px) scale(${state.scale})`;
  };

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

  /**
   * The load-time view: the whole diagram visible and centred, never magnified
   * past 1:1 for a diagram that already fits.
   *
   * Recomputed from the viewBox and the current viewport rather than restored
   * from a snapshot taken at install, so it cannot drift from the view the
   * reader was given - and so a diagram whose viewport was not yet measurable
   * when it was enhanced still resets to something sensible. With no measurable
   * viewport it degrades to `INITIAL_STATE`, which is the identity transform.
   */
  const fitToContain = (): void => {
    const rect = viewport.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      Object.assign(state, INITIAL_STATE);
      applyTransform();
      return;
    }
    state.scale = clampScale(
      Math.min(1, rect.width / contentSize.width, rect.height / contentSize.height),
    );
    state.offsetX = Math.max(0, (rect.width - contentSize.width * state.scale) / 2);
    state.offsetY = Math.max(0, (rect.height - contentSize.height * state.scale) / 2);
    applyTransform();
  };

  const reset = (): void => {
    fitToContain();
  };

  const fitToWidth = (): void => {
    const rect = viewport.getBoundingClientRect();
    if (rect.width <= 0) return;
    // Correct now only because the SVG is sized one CSS pixel per viewBox unit;
    // see the sizing note in this function's preamble.
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

  // Establishes the load-time view, and is the first thing to write a transform.
  fitToContain();

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
    button.className = [
      "inline-flex items-center justify-center size-[26px] p-0",
      "border-0 bg-transparent rounded-sm cursor-pointer",
      "text-ink-soft font-mono text-[13px] leading-none",
      "transition-[background-color,color] duration-[120ms] motion-reduce:transition-none",
      "hover:bg-sunken hover:text-ink",
      "focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-1",
    ].join(" ");
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
    // Deliberately NO `setPointerCapture` here.
    //
    // Capturing the pointer on the viewport retargets every subsequent pointer
    // event *and the click that follows* to the capturing element. Mermaid's
    // node links are real `<a>` elements inside the SVG, so capture means the
    // anchor never receives the click and no diagram node ever navigates -
    // precisely the regression this module exists to avoid. It was found in a
    // real browser; no jsdom test could have caught it, because jsdom does not
    // define `setPointerCapture` at all and skipped the whole path.
    //
    // The window-level listeners below do the only job capture was wanted for:
    // continuing and cleanly ending a drag whose pointer leaves the viewport.
    window.addEventListener("pointermove", onWindowMove);
    window.addEventListener("pointerup", onWindowUp);
  });

  // Movement and release are tracked on `window` only, never also on the
  // viewport: a pointermove inside the viewport bubbles to both, and handling it
  // twice worked only by accident (the second pass computes a zero delta because
  // the first already advanced `lastX`/`lastY`). One listener, one delta.
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
