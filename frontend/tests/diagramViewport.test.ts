import { readFile } from "node:fs/promises";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  BUTTON_ZOOM_STEP,
  enhanceDiagrams,
  KEYBOARD_PAN_PX,
  MAX_SCALE,
  MIN_SCALE,
} from "../src/lib/diagramViewport";

/**
 * jsdom 25 defines no `PointerEvent` constructor, so a pointer event is
 * dispatched as a `MouseEvent` carrying the same type string. Listeners key on
 * the type, and `MouseEvent` carries the `clientX`/`clientY` the handler reads,
 * so this exercises the production path rather than a test-only branch.
 */
function firePointer(target: EventTarget, type: string, x: number, y: number): void {
  target.dispatchEvent(
    new MouseEvent(type, { clientX: x, clientY: y, bubbles: true, cancelable: true }),
  );
}

function fireWheel(target: EventTarget, deltaY: number, x: number, y: number): WheelEvent {
  const event = new WheelEvent("wheel", {
    deltaY,
    clientX: x,
    clientY: y,
    bubbles: true,
    cancelable: true,
  });
  target.dispatchEvent(event);
  return event;
}

/** A `pre.mermaid` shaped like Mermaid's own output: an `<svg>` with a
 * `viewBox`, an inline `max-width`, and a real `<a>` around a node - which is
 * how Mermaid realises a `click <node> href "..."` directive. */
function buildDiagram(options: { viewBox?: string | null } = {}): HTMLPreElement {
  const viewBox = options.viewBox === undefined ? "0 0 800 600" : options.viewBox;
  const pre = document.createElement("pre");
  pre.className = "mermaid";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  if (viewBox !== null) svg.setAttribute("viewBox", viewBox);
  svg.setAttribute("width", "100%");
  svg.setAttribute("style", "max-width: 800px;");
  const anchor = document.createElementNS("http://www.w3.org/2000/svg", "a");
  anchor.setAttribute("href", "../modules/target.html");
  anchor.appendChild(document.createElementNS("http://www.w3.org/2000/svg", "rect"));
  svg.appendChild(anchor);
  pre.appendChild(svg);
  document.body.appendChild(pre);
  return pre;
}

/** An empty `pre.mermaid`: Mermaid has not drawn it (yet, or ever). */
function buildUndrawnDiagram(): HTMLPreElement {
  const pre = document.createElement("pre");
  pre.className = "mermaid";
  document.body.appendChild(pre);
  return pre;
}

function viewportOf(pre: Element): HTMLElement {
  const viewport = pre.querySelector<HTMLElement>(".diagram-viewport");
  if (!viewport) throw new Error("no .diagram-viewport was installed");
  return viewport;
}

function canvasOf(pre: Element): HTMLElement {
  const canvas = pre.querySelector<HTMLElement>(".diagram-canvas");
  if (!canvas) throw new Error("no .diagram-canvas was installed");
  return canvas;
}

/** Current scale, read back off the applied transform. */
function scaleOf(pre: Element): number {
  const match = /scale\(([-\d.]+)\)/.exec(canvasOf(pre).style.transform);
  if (!match) throw new Error(`no scale in transform: ${canvasOf(pre).style.transform}`);
  return Number(match[1]);
}

function offsetOf(pre: Element): { x: number; y: number } {
  const match = /translate\(([-\d.]+)px,\s*([-\d.]+)px\)/.exec(canvasOf(pre).style.transform);
  if (!match) throw new Error(`no translate in transform: ${canvasOf(pre).style.transform}`);
  return { x: Number(match[1]), y: Number(match[2]) };
}

/** jsdom returns an all-zero rect from `getBoundingClientRect`, so any test
 * that depends on geometry has to supply it. */
function stubRect(element: Element, rect: Partial<DOMRect>): void {
  const full = { x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, ...rect };
  vi.spyOn(element, "getBoundingClientRect").mockReturnValue({
    ...full,
    toJSON: () => full,
  } as DOMRect);
}

/** Dispatch a click and report whether anything called `preventDefault()`.
 *
 * This is the assertion that matters for click-vs-drag. Mermaid renders a
 * `click <node> href` directive as a real `<a>`, so navigation is the anchor's
 * *default action* - asserting that some handler spy went uncalled would pass
 * against an implementation that still navigates. */
function clickAndReportSuppression(target: EventTarget, x = 0, y = 0): boolean {
  const event = new MouseEvent("click", {
    clientX: x,
    clientY: y,
    bubbles: true,
    cancelable: true,
  });
  target.dispatchEvent(event);
  return event.defaultPrevented;
}

beforeEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("enhanceDiagrams - the sweep", () => {
  it("installs the viewport structure around a drawn diagram", () => {
    const pre = buildDiagram();

    expect(enhanceDiagrams()).toBe(1);

    const viewport = viewportOf(pre);
    expect(viewport.getAttribute("tabindex")).toBe("0");
    expect(viewport.getAttribute("role")).toBe("group");
    expect(viewport.getAttribute("aria-label")).toBeTruthy();
    // The SVG moved into the canvas, and its own contents are untouched: the
    // <a> Mermaid emitted is what makes a node a link.
    expect(canvasOf(pre).querySelector("svg")).not.toBeNull();
    expect(pre.querySelector("svg a")).not.toBeNull();
    expect(pre.querySelectorAll(".diagram-controls").length).toBe(1);
  });

  it("clears the inline max-width Mermaid stamps on the SVG", () => {
    const pre = buildDiagram();

    enhanceDiagrams();

    const svg = pre.querySelector("svg") as SVGElement;
    expect(svg.style.maxWidth).toBe("");
  });

  it("is idempotent: a second sweep enhances nothing and preserves the view", () => {
    const pre = buildDiagram();
    enhanceDiagrams();
    stubRect(viewportOf(pre), { width: 400, height: 300 });
    fireWheel(viewportOf(pre), -100, 200, 150);
    const afterZoom = canvasOf(pre).style.transform;

    expect(enhanceDiagrams()).toBe(0);

    expect(pre.querySelectorAll(".diagram-controls").length).toBe(1);
    expect(pre.querySelectorAll(".diagram-viewport").length).toBe(1);
    expect(canvasOf(pre).style.transform).toBe(afterZoom);
  });

  it("skips an undrawn diagram without marking it, and enhances it once drawn", () => {
    const pre = buildUndrawnDiagram();

    expect(enhanceDiagrams()).toBe(0);
    expect(pre.hasAttribute("data-viewport-enhanced")).toBe(false);

    // Mermaid draws it later; the next sweep picks it up.
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 100 100");
    pre.appendChild(svg);

    expect(enhanceDiagrams()).toBe(1);
  });

  it("skips a diagram with no usable viewBox but still enhances its siblings", () => {
    buildDiagram({ viewBox: null });
    const valid = buildDiagram();

    expect(enhanceDiagrams()).toBe(1);
    expect(valid.querySelector(".diagram-viewport")).not.toBeNull();
  });

  it("returns 0 when there is nothing to enhance", () => {
    expect(enhanceDiagrams()).toBe(0);
  });
});

/** A diagram whose viewport occupies a known rect, so geometry-dependent
 * behaviour has something to compute against. */
function enhancedDiagram(rect: Partial<DOMRect> = { width: 400, height: 300 }): HTMLPreElement {
  const pre = buildDiagram();
  enhanceDiagrams();
  stubRect(viewportOf(pre), rect);
  return pre;
}

function controlOf(pre: Element, label: string): HTMLButtonElement {
  const button = pre.querySelector<HTMLButtonElement>(`.diagram-controls button[aria-label="${label}"]`);
  if (!button) throw new Error(`no control labelled "${label}"`);
  return button;
}

describe("US1 - zoom and pan", () => {
  it("anchors wheel zoom on the pointer: the point under it does not move", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);
    // Pointer 120px right and 90px down from the viewport's top-left corner.
    const pointerX = 120;
    const pointerY = 90;

    fireWheel(viewport, -100, pointerX, pointerY);

    // The content point that was under the pointer before the zoom must still
    // be under it after. Solve for it: contentPoint = (pointer - offset) / scale
    // must be equal before and after, and before the zoom offset was (0,0) and
    // scale was 1, so contentPoint === pointer.
    const { x, y } = offsetOf(pre);
    const scale = scaleOf(pre);
    expect((pointerX - x) / scale).toBeCloseTo(pointerX, 5);
    expect((pointerY - y) / scale).toBeCloseTo(pointerY, 5);
    expect(scale).toBeGreaterThan(1);
  });

  it("prevents the page from scrolling while zooming", () => {
    const pre = enhancedDiagram();

    const event = fireWheel(viewportOf(pre), -100, 10, 10);

    expect(event.defaultPrevented).toBe(true);
  });

  it("keeps scale within its bounds however far the wheel is turned", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);

    for (let i = 0; i < 200; i += 1) fireWheel(viewport, -100, 50, 50);
    expect(scaleOf(pre)).toBeLessThanOrEqual(MAX_SCALE);
    expect(scaleOf(pre)).toBeCloseTo(MAX_SCALE, 5);

    for (let i = 0; i < 400; i += 1) fireWheel(viewport, 100, 50, 50);
    expect(scaleOf(pre)).toBeGreaterThanOrEqual(MIN_SCALE);
    expect(scaleOf(pre)).toBeCloseTo(MIN_SCALE, 5);
  });

  it("pans by the pointer delta while dragging", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);

    firePointer(viewport, "pointerdown", 100, 100);
    firePointer(viewport, "pointermove", 130, 120);
    firePointer(viewport, "pointerup", 130, 120);

    expect(offsetOf(pre)).toEqual({ x: 30, y: 20 });
  });

  it("keeps panning when the pointer leaves the viewport, and stops on release", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);

    firePointer(viewport, "pointerdown", 100, 100);
    // Released outside: the window-level fallback has to end the gesture.
    firePointer(window, "pointermove", 150, 100);
    firePointer(window, "pointerup", 150, 100);
    firePointer(window, "pointermove", 900, 900);

    expect(offsetOf(pre)).toEqual({ x: 50, y: 0 });
  });

  it("restores the exact load-time view on reset", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);
    fireWheel(viewport, -240, 60, 60);
    firePointer(viewport, "pointerdown", 10, 10);
    firePointer(viewport, "pointermove", 90, 70);
    firePointer(viewport, "pointerup", 90, 70);
    expect(canvasOf(pre).style.transform).not.toBe("translate(0px, 0px) scale(1)");

    controlOf(pre, "Reset view").click();

    expect(canvasOf(pre).style.transform).toBe("translate(0px, 0px) scale(1)");
  });

  it("fits the diagram to the viewport width", () => {
    // viewBox is 800 wide; a 400px viewport should land at scale 0.5.
    const pre = enhancedDiagram({ width: 400, height: 300 });

    controlOf(pre, "Fit diagram to width").click();

    expect(scaleOf(pre)).toBeCloseTo(0.5, 5);
    expect(offsetOf(pre)).toEqual({ x: 0, y: 0 });
  });

  it("steps the scale by a fixed factor from the zoom buttons", () => {
    const pre = enhancedDiagram();

    controlOf(pre, "Zoom in").click();
    expect(scaleOf(pre)).toBeCloseTo(BUTTON_ZOOM_STEP, 5);

    controlOf(pre, "Zoom out").click();
    expect(scaleOf(pre)).toBeCloseTo(1, 5);
  });

  it("does not swallow a control press made straight after a drag", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);
    firePointer(viewport, "pointerdown", 10, 10);
    firePointer(viewport, "pointermove", 200, 200);
    firePointer(viewport, "pointerup", 200, 200);

    controlOf(pre, "Reset view").click();

    expect(canvasOf(pre).style.transform).toBe("translate(0px, 0px) scale(1)");
  });
});

/**
 * The tests that matter most in this file.
 *
 * Mermaid renders `click <node> href "..."` as a real `<a xlink:href>`, so
 * navigation is the anchor's default action. Every assertion here is on
 * `preventDefault()` for that reason: asserting that some handler spy went
 * uncalled would pass against an implementation that still navigates on every
 * drag, which is precisely the regression this story exists to prevent.
 */
describe("US2 - a click navigates, a drag never does", () => {
  function anchorOf(pre: Element): SVGAElement {
    const anchor = pre.querySelector<SVGAElement>("svg a");
    if (!anchor) throw new Error("fixture has no <a> node");
    return anchor;
  }

  it("lets a click through when the pointer barely moved", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);

    firePointer(viewport, "pointerdown", 100, 100);
    firePointer(viewport, "pointermove", 102, 100);
    firePointer(viewport, "pointerup", 102, 100);

    expect(clickAndReportSuppression(anchorOf(pre), 102, 100)).toBe(false);
  });

  it("suppresses the click that ends a drag", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);

    firePointer(viewport, "pointerdown", 100, 100);
    firePointer(viewport, "pointermove", 110, 100);
    firePointer(viewport, "pointerup", 110, 100);

    expect(clickAndReportSuppression(anchorOf(pre), 110, 100)).toBe(true);
  });

  it("treats a drag that returns to its origin as a drag, not a click", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);

    firePointer(viewport, "pointerdown", 100, 100);
    firePointer(viewport, "pointermove", 140, 100);
    firePointer(viewport, "pointermove", 100, 100);
    firePointer(viewport, "pointerup", 100, 100);

    // Distance is measured from the origin and latched, so coming back does not
    // turn the gesture back into a click.
    expect(clickAndReportSuppression(anchorOf(pre), 100, 100)).toBe(true);
  });

  it("navigates again on the next still click after a suppressed drag", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);
    firePointer(viewport, "pointerdown", 100, 100);
    firePointer(viewport, "pointermove", 140, 100);
    firePointer(viewport, "pointerup", 140, 100);
    expect(clickAndReportSuppression(anchorOf(pre), 140, 100)).toBe(true);

    firePointer(viewport, "pointerdown", 140, 100);
    firePointer(viewport, "pointerup", 140, 100);

    expect(clickAndReportSuppression(anchorOf(pre), 140, 100)).toBe(false);
  });

  it("leaves the anchors Mermaid emitted untouched", () => {
    const pre = enhancedDiagram();

    expect(anchorOf(pre).getAttribute("href")).toBe("../modules/target.html");
  });
});

function fireKey(target: EventTarget, key: string): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  target.dispatchEvent(event);
  return event;
}

describe("US3 - expand", () => {
  it("toggles the expanded state and relabels its control", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);

    controlOf(pre, "Expand diagram").click();
    expect(viewport.classList.contains("is-expanded")).toBe(true);

    controlOf(pre, "Collapse diagram").click();
    expect(viewport.classList.contains("is-expanded")).toBe(false);
  });

  it("collapses on Escape", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);
    controlOf(pre, "Expand diagram").click();

    fireKey(viewport, "Escape");

    expect(viewport.classList.contains("is-expanded")).toBe(false);
  });

  it("preserves the reader's zoom and position across expand and collapse", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);
    fireWheel(viewport, -160, 80, 60);
    firePointer(viewport, "pointerdown", 10, 10);
    firePointer(viewport, "pointermove", 60, 40);
    firePointer(viewport, "pointerup", 60, 40);
    const before = canvasOf(pre).style.transform;

    controlOf(pre, "Expand diagram").click();
    expect(canvasOf(pre).style.transform).toBe(before);
    controlOf(pre, "Collapse diagram").click();

    expect(canvasOf(pre).style.transform).toBe(before);
  });
});

describe("US4 - keyboard and assistive technology", () => {
  it("exposes the viewport to keyboard and assistive technology", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);

    expect(viewport.getAttribute("tabindex")).toBe("0");
    expect(viewport.getAttribute("role")).toBe("group");
    expect(viewport.getAttribute("aria-label")).toBeTruthy();
  });

  it("labels every control", () => {
    const pre = enhancedDiagram();

    const labels = Array.from(
      pre.querySelectorAll(".diagram-controls button"),
      (button) => button.getAttribute("aria-label"),
    );

    expect(labels).toEqual([
      "Zoom in",
      "Zoom out",
      "Reset view",
      "Fit diagram to width",
      "Expand diagram",
    ]);
  });

  it("zooms with + and -, and resets with 0", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);

    fireKey(viewport, "+");
    expect(scaleOf(pre)).toBeCloseTo(BUTTON_ZOOM_STEP, 5);
    fireKey(viewport, "-");
    expect(scaleOf(pre)).toBeCloseTo(1, 5);

    fireKey(viewport, "=");
    expect(scaleOf(pre)).toBeCloseTo(BUTTON_ZOOM_STEP, 5);
    fireKey(viewport, "0");
    expect(canvasOf(pre).style.transform).toBe("translate(0px, 0px) scale(1)");
  });

  it("pans with the arrow keys without scrolling the page", () => {
    const pre = enhancedDiagram();
    const viewport = viewportOf(pre);

    const right = fireKey(viewport, "ArrowRight");
    expect(offsetOf(pre)).toEqual({ x: -KEYBOARD_PAN_PX, y: 0 });
    expect(right.defaultPrevented).toBe(true);

    fireKey(viewport, "ArrowLeft");
    fireKey(viewport, "ArrowDown");
    expect(offsetOf(pre)).toEqual({ x: 0, y: -KEYBOARD_PAN_PX });
    fireKey(viewport, "ArrowUp");
    expect(offsetOf(pre)).toEqual({ x: 0, y: 0 });
  });
});


/**
 * A source-level guard, not a behavioural test - deliberately.
 *
 * `setPointerCapture` on the viewport retargets every subsequent pointer event
 * *and the click that follows* to the capturing element, so Mermaid's `<a>` node
 * links stop navigating entirely. That shipped once and no test here caught it:
 * jsdom does not define `setPointerCapture`, so the `typeof` guard around it
 * skipped the whole path in every run, in every browser-less test that could
 * ever be written against this module.
 *
 * The behaviour is verified for real against Chrome (see quickstart.md § 3a).
 * This assertion exists only so the call cannot quietly come back.
 */
describe("regression guard - pointer capture", () => {
  it("never captures the pointer, which would swallow diagram link clicks", async () => {
    // Path relative to the vitest root (frontend/); `import.meta.url` is
    // rewritten by the dev server under jsdom and is not a file: URL here.
    const source = await readFile("src/lib/diagramViewport.ts", "utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    expect(code).not.toMatch(/setPointerCapture/);
  });
});
