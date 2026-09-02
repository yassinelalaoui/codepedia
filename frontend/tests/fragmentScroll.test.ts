import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installFragmentScrolling, scrollToCurrentFragment } from "../src/lib/fragmentScroll";

/**
 * These assert that `scrollIntoView` was called on the right element - which is
 * only possible because `tests/setup.ts` stubs the method jsdom leaves
 * undefined. Without that stub the production `typeof` guard would be false
 * here and the whole path would be skipped silently, which is exactly how
 * feature 034's `setPointerCapture` defect passed all 27 of its tests while
 * breaking every diagram link in a real browser.
 *
 * What this still cannot prove is that the browser scrolled anywhere, or to the
 * right offset. That is checked against real Chrome (quickstart § 2, check 4).
 */
function headingAt(id: string): HTMLElement {
  const heading = document.createElement("h2");
  heading.id = id;
  document.body.appendChild(heading);
  return heading;
}

beforeEach(() => {
  document.body.innerHTML = "";
  window.history.pushState({}, "", "/");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("scrollToCurrentFragment", () => {
  it("scrolls to the element the hash names", () => {
    const heading = headingAt("summary");
    const spy = vi.spyOn(heading, "scrollIntoView");
    window.history.pushState({}, "", "/page.html#summary");

    expect(scrollToCurrentFragment()).toBe(heading);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("does nothing when there is no hash", () => {
    const heading = headingAt("summary");
    const spy = vi.spyOn(heading, "scrollIntoView");

    expect(scrollToCurrentFragment()).toBeNull();
    expect(spy).not.toHaveBeenCalled();
  });

  it("does nothing, and does not throw, when the hash names no element", () => {
    window.history.pushState({}, "", "/page.html#not-on-this-page");

    expect(() => scrollToCurrentFragment()).not.toThrow();
    expect(scrollToCurrentFragment()).toBeNull();
  });

  it("resolves a percent-encoded id", () => {
    const heading = headingAt("class name");
    const spy = vi.spyOn(heading, "scrollIntoView");
    window.history.pushState({}, "", "/page.html#class%20name");

    expect(scrollToCurrentFragment()).toBe(heading);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("falls back to the raw hash when it is not valid percent-encoding", () => {
    const heading = headingAt("100%");
    window.history.pushState({}, "", "/page.html#100%");

    // decodeURIComponent throws on a lone '%'; the id may still match verbatim.
    expect(() => scrollToCurrentFragment()).not.toThrow();
    expect(scrollToCurrentFragment()).toBe(heading);
  });
});

describe("installFragmentScrolling", () => {
  it("resolves the fragment present at load", () => {
    const heading = headingAt("summary");
    const spy = vi.spyOn(heading, "scrollIntoView");
    window.history.pushState({}, "", "/page.html#summary");

    installFragmentScrolling();

    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("re-resolves on a later hash change", () => {
    const first = headingAt("one");
    const second = headingAt("two");
    const firstSpy = vi.spyOn(first, "scrollIntoView");
    const secondSpy = vi.spyOn(second, "scrollIntoView");
    window.history.pushState({}, "", "/page.html#one");

    installFragmentScrolling();
    expect(firstSpy).toHaveBeenCalledTimes(1);

    window.history.pushState({}, "", "/page.html#two");
    window.dispatchEvent(new Event("hashchange"));

    expect(secondSpy).toHaveBeenCalledTimes(1);
  });
});
