import { afterEach, describe, expect, it, vi } from "vitest";
import { installDiagramThemeSync, rerenderDiagramsForTheme } from "../src/lib/diagramViewport";

/**
 * Redrawing diagrams for a theme change (036 spec FR-013, FR-013a).
 *
 * Separate from diagramViewport.test.ts, which covers the pan/zoom gestures
 * from feature 034; this is a distinct concern with its own DOM fixture.
 *
 * Mermaid is a vendored global rather than a dependency of this bundle, so it
 * is stubbed here. What that cannot show is whether a *real* Mermaid redraw
 * looks right, which is checked in Chrome instead (quickstart.md §4, 4.7).
 */

function drawnDiagram(source: string): HTMLElement {
  // The shape the page is in once layout.html.jinja has stashed the source,
  // mermaid.run() has replaced the fence text with an SVG, and enhanceDiagrams
  // has wrapped that in a transformed canvas.
  const pre = document.createElement("pre");
  pre.className = "mermaid";
  pre.setAttribute("data-diagram-source", source);
  pre.setAttribute("data-viewport-enhanced", "true");
  const viewport = document.createElement("div");
  viewport.className = "diagram-viewport";
  const canvas = document.createElement("div");
  canvas.style.transform = "translate(37px, 91px) scale(2.5)";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 100 80");
  (svg as unknown as HTMLElement).style.width = "100px";
  (svg as unknown as HTMLElement).style.height = "80px";
  svg.setAttribute("data-generation", "first");
  canvas.appendChild(svg);
  viewport.appendChild(canvas);
  pre.appendChild(viewport);
  document.body.appendChild(pre);
  return pre;
}

function stubMermaid(impl?: (id: string, text: string) => Promise<{ svg: string }>) {
  const render =
    impl ??
    ((id: string) =>
      Promise.resolve({
        svg:
          `<svg viewBox="0 0 100 80" width="100%" style="max-width: 100px" ` +
          `data-generation="second" data-id="${id}"></svg>`,
      }));
  (window as unknown as { mermaid?: unknown }).mermaid = {
    initialize: vi.fn(),
    render: vi.fn(render),
  };
}

function mermaidStub(): { initialize: ReturnType<typeof vi.fn>; render: ReturnType<typeof vi.fn> } {
  return (window as unknown as {
    mermaid: { initialize: ReturnType<typeof vi.fn>; render: ReturnType<typeof vi.fn> };
  }).mermaid;
}

function generationOf(pre: HTMLElement): string | null | undefined {
  return pre.querySelector("svg")?.getAttribute("data-generation");
}

afterEach(() => {
  delete (window as unknown as { mermaid?: unknown }).mermaid;
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("rerenderDiagramsForTheme", () => {
  it("redraws the diagram from its stashed source", async () => {
    stubMermaid();
    const pre = drawnDiagram("graph TD; A-->B");
    expect(await rerenderDiagramsForTheme("dark")).toBe(1);
    expect(generationOf(pre)).toBe("second");
  });

  it("passes the stashed source to mermaid, not the rendered markup", async () => {
    stubMermaid();
    drawnDiagram("graph TD; A-->B");
    await rerenderDiagramsForTheme("dark");
    expect(mermaidStub().render.mock.calls[0][1]).toBe("graph TD; A-->B");
  });

  it("initialises mermaid with the theme it was asked for", async () => {
    stubMermaid();
    drawnDiagram("graph TD; A-->B");
    await rerenderDiagramsForTheme("dark");
    expect(mermaidStub().initialize.mock.calls[0][0]).toMatchObject({ theme: "dark" });
    await rerenderDiagramsForTheme("light");
    expect(mermaidStub().initialize.mock.calls[1][0]).toMatchObject({ theme: "default" });
  });

  it("leaves the reader's zoom and pan exactly where they were", async () => {
    stubMermaid();
    const pre = drawnDiagram("graph TD; A-->B");
    const canvas = pre.querySelector(".diagram-viewport > div") as HTMLElement;
    await rerenderDiagramsForTheme("dark");
    expect(canvas.style.transform).toBe("translate(37px, 91px) scale(2.5)");
  });

  it("swaps only the svg, keeping the viewport and canvas elements themselves", async () => {
    stubMermaid();
    const pre = drawnDiagram("graph TD; A-->B");
    const viewport = pre.querySelector(".diagram-viewport");
    const canvas = pre.querySelector(".diagram-viewport > div");
    await rerenderDiagramsForTheme("dark");
    expect(pre.querySelector(".diagram-viewport")).toBe(viewport);
    expect(pre.querySelector(".diagram-viewport > div")).toBe(canvas);
  });

  it("clears the width and max-width mermaid stamps on the fresh svg", async () => {
    // Leaving these on re-introduces the letterboxing that made `scale` stop
    // meaning magnification - the defect enhanceOne's sizing comment records.
    stubMermaid();
    const pre = drawnDiagram("graph TD; A-->B");
    await rerenderDiagramsForTheme("dark");
    const svg = pre.querySelector("svg") as unknown as HTMLElement;
    expect(svg.getAttribute("width")).toBeNull();
    expect(svg.style.maxWidth).toBe("");
    expect(svg.style.width).toBe("100px");
    expect(svg.style.height).toBe("80px");
  });

  it("uses a unique id per render so mermaid cannot serve a cached definition", async () => {
    stubMermaid();
    drawnDiagram("graph TD; A-->B");
    drawnDiagram("graph LR; C-->D");
    await rerenderDiagramsForTheme("dark");
    const ids = mermaidStub().render.mock.calls.map((call: unknown[]) => call[0]);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("keeps ids unique across separate passes too", async () => {
    stubMermaid();
    drawnDiagram("graph TD; A-->B");
    await rerenderDiagramsForTheme("dark");
    await rerenderDiagramsForTheme("light");
    const ids = mermaidStub().render.mock.calls.map((call: unknown[]) => call[0]);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("leaves a diagram with no stashed source untouched", async () => {
    stubMermaid();
    const pre = drawnDiagram("graph TD; A-->B");
    pre.removeAttribute("data-diagram-source");
    expect(await rerenderDiagramsForTheme("dark")).toBe(0);
    expect(generationOf(pre)).toBe("first");
  });

  it("leaves a diagram with an empty stashed source untouched", async () => {
    stubMermaid();
    const pre = drawnDiagram("   \n  ");
    expect(await rerenderDiagramsForTheme("dark")).toBe(0);
    expect(generationOf(pre)).toBe("first");
  });

  it("leaves a diagram alone when mermaid throws, without aborting the batch", async () => {
    let call = 0;
    stubMermaid(() => {
      call += 1;
      if (call === 1) return Promise.reject(new Error("unparseable"));
      return Promise.resolve({ svg: `<svg viewBox="0 0 100 80" data-generation="second"></svg>` });
    });
    const failing = drawnDiagram("graph TD; broken");
    const healthy = drawnDiagram("graph LR; C-->D");
    expect(await rerenderDiagramsForTheme("dark")).toBe(1);
    expect(generationOf(failing)).toBe("first");
    expect(generationOf(healthy)).toBe("second");
  });

  it("does nothing when mermaid is not on the page", async () => {
    const pre = drawnDiagram("graph TD; A-->B");
    expect(await rerenderDiagramsForTheme("dark")).toBe(0);
    expect(generationOf(pre)).toBe("first");
  });
});

describe("installDiagramThemeSync", () => {
  it("redraws when a theme change is announced", async () => {
    stubMermaid();
    const pre = drawnDiagram("graph TD; A-->B");
    const stop = installDiagramThemeSync();
    document.dispatchEvent(
      new CustomEvent("wiki:theme-changed", { detail: { theme: "dark", preference: "dark" } }),
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(generationOf(pre)).toBe("second");
    stop();
  });

  it("ignores an event with no usable theme in it", async () => {
    stubMermaid();
    const stop = installDiagramThemeSync();
    document.dispatchEvent(new CustomEvent("wiki:theme-changed", { detail: {} }));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mermaidStub().render).not.toHaveBeenCalled();
    stop();
  });

  it("stops redrawing once detached", async () => {
    stubMermaid();
    const stop = installDiagramThemeSync();
    stop();
    document.dispatchEvent(
      new CustomEvent("wiki:theme-changed", { detail: { theme: "dark", preference: "dark" } }),
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mermaidStub().render).not.toHaveBeenCalled();
  });
});
