import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ThemeToggle } from "../src/components/ThemeToggle";

/**
 * The segmented System/Light/Dark control (036 spec FR-001, FR-002, FR-012).
 *
 * `fireEvent`, matching the rest of this suite - `@testing-library/user-event`
 * is not a dependency of this project and 036 plan.md commits to adding none.
 *
 * That bounds what the keyboard assertions below can claim. They prove the
 * options are real `<button>` elements that nothing has removed from the tab
 * order, which is *why* they are keyboard reachable, and that activation does
 * not depend on a mouse. They do not prove the browser's focus order, because
 * jsdom does not implement Tab traversal. SC-009 is settled against real Chrome
 * (quickstart.md §5).
 */

const KEY = "codepedia:theme:testwiki00000000";

beforeEach(() => {
  window.__WIKI_THEME__ = { wikiId: "testwiki00000000", storageKey: KEY };
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ThemeToggle", () => {
  it("renders exactly three options, in order", () => {
    render(<ThemeToggle />);
    const options = screen.getAllByRole("button");
    expect(options.map((option) => option.textContent)).toEqual(["System", "Light", "Dark"]);
  });

  it("carries an accessible name describing its purpose", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("group", { name: /theme/i })).toBeTruthy();
  });

  it("shows System as selected for a reader who has not chosen", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "System" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Dark" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("shows the stored choice as selected", () => {
    window.localStorage.setItem(KEY, "dark");
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Dark" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "System" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("applies and persists a choice when an option is activated", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem(KEY)).toBe("dark");
  });

  it("moves the selected marker to the activated option", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Light" }));
    expect(screen.getByRole("button", { name: "Light" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "System" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("removes the attribute entirely when System is chosen", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    fireEvent.click(screen.getByRole("button", { name: "System" }));
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("leaves every option in the tab order", () => {
    render(<ThemeToggle />);
    for (const name of ["System", "Light", "Dark"]) {
      const option = screen.getByRole("button", { name });
      expect(option.tagName).toBe("BUTTON");
      // A negative tabindex is the usual way an option gets silently dropped
      // from keyboard reach; native buttons are focusable without one.
      expect(option.getAttribute("tabindex")).not.toBe("-1");
      expect(option.hasAttribute("disabled")).toBe(false);
    }
  });

  it("can be focused and activated without a mouse", () => {
    render(<ThemeToggle />);
    const dark = screen.getByRole("button", { name: "Dark" });
    dark.focus();
    expect(document.activeElement).toBe(dark);
    // Enter on a focused native button dispatches a click; jsdom does not do
    // that implicitly, so the click is what a real Enter press becomes.
    fireEvent.click(dark);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("keeps .theme-toggle as the first class so tests and CSS can hook it", () => {
    const { container } = render(<ThemeToggle />);
    const root = container.querySelector(".theme-toggle");
    expect(root).not.toBeNull();
    expect(root?.className.split(/\s+/)[0]).toBe("theme-toggle");
  });
});
