import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TocHighlighter } from "../src/components/TocHighlighter";

type ObserverCallback = (entries: { target: Element; isIntersecting: boolean }[]) => void;

let lastCallback: ObserverCallback | null = null;
let observed: Element[] = [];
let disconnected = 0;

class FakeIntersectionObserver {
  constructor(callback: ObserverCallback) {
    lastCallback = callback;
  }
  observe(element: Element): void {
    observed.push(element);
  }
  disconnect(): void {
    disconnected += 1;
  }
  unobserve(): void {}
  takeRecords(): [] {
    return [];
  }
}

/** The rail markup `doc_generator`'s Jinja layout emits, plus the headings it points at. */
function renderPage(): void {
  document.body.innerHTML = `
    <div class="nav-group page-toc">
      <a class="page-toc-link" href="#summary">Summary</a>
      <a class="page-toc-link" href="#classes">Classes</a>
      <a class="page-toc-link" href="#missing">Dangling</a>
    </div>
    <div class="content-col">
      <h2 id="summary">Summary</h2>
      <h2 id="classes">Classes</h2>
    </div>
  `;
}

function linkFor(anchor: string): HTMLAnchorElement {
  return document.querySelector<HTMLAnchorElement>(`a[href="#${anchor}"]`)!;
}

beforeEach(() => {
  lastCallback = null;
  observed = [];
  disconnected = 0;
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  renderPage();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("TocHighlighter", () => {
  it("observes every heading a rail entry actually points at", () => {
    render(<TocHighlighter />);

    expect(observed.map((element) => (element as HTMLElement).id)).toEqual([
      "summary",
      "classes",
    ]);
  });

  it("marks the section currently in view as active", () => {
    render(<TocHighlighter />);

    lastCallback!([{ target: document.getElementById("classes")!, isIntersecting: true }]);

    expect(linkFor("classes").classList.contains("active")).toBe(true);
    expect(linkFor("summary").classList.contains("active")).toBe(false);
  });

  it("prefers the earliest visible section when several are in view", () => {
    render(<TocHighlighter />);

    lastCallback!([
      { target: document.getElementById("classes")!, isIntersecting: true },
      { target: document.getElementById("summary")!, isIntersecting: true },
    ]);

    expect(linkFor("summary").classList.contains("active")).toBe(true);
    expect(linkFor("classes").classList.contains("active")).toBe(false);
  });

  it("keeps the last active section when nothing is in the detection band", () => {
    render(<TocHighlighter />);
    lastCallback!([{ target: document.getElementById("summary")!, isIntersecting: true }]);

    lastCallback!([{ target: document.getElementById("summary")!, isIntersecting: false }]);

    expect(linkFor("summary").classList.contains("active")).toBe(true);
  });

  it("leaves a rail entry whose heading is absent alone", () => {
    render(<TocHighlighter />);

    expect(linkFor("missing").classList.contains("active")).toBe(false);
  });

  it("disconnects the observer on unmount so StrictMode cannot leak one", () => {
    const view = render(<TocHighlighter />);

    view.unmount();

    expect(disconnected).toBeGreaterThan(0);
  });

  it("renders nothing and does not throw without IntersectionObserver", () => {
    vi.stubGlobal("IntersectionObserver", undefined);

    const view = render(<TocHighlighter />);

    expect(view.container.innerHTML).toBe("");
  });
});
