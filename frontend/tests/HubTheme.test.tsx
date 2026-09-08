import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ThemeToggle } from "../src/components/ThemeToggle";

/**
 * Spec FR-044a to FR-044c.
 *
 * The homepage reuses the wiki's control and `lib/theme.ts` unchanged, keyed to
 * its own storage key. What is worth pinning here is that the reuse actually
 * works against a hub-scoped key, and that a refusing storage falls back to the
 * operating system rather than breaking the control.
 */

const HUB_KEY = "codepedia:theme:hub";

declare global {
  interface Window {
    __WIKI_THEME__?: { wikiId?: string; storageKey?: string };
  }
}

beforeEach(() => {
  // What src/hub_server/assets/index.html publishes before first paint.
  window.__WIKI_THEME__ = { storageKey: HUB_KEY };
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  delete window.__WIKI_THEME__;
  document.documentElement.removeAttribute("data-theme");
});

describe("the homepage's appearance control", () => {
  it("offers all three states", () => {
    render(<ThemeToggle />);

    expect(screen.getByRole("button", { name: "System" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Light" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dark" })).toBeInTheDocument();
  });

  it("makes the current state identifiable without interacting", () => {
    render(<ThemeToggle />);

    expect(screen.getByRole("button", { name: "System" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "false");
  });

  it("applies a choice immediately, with no reload", () => {
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: "Dark" }));

    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("reaches any state in one interaction from any other", () => {
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: "Light" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    fireEvent.click(screen.getByRole("button", { name: "System" }));
    // System is the *absence* of the attribute - that is what lets the
    // stylesheet's OS-preference rule apply.
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("remembers the choice under the hub's own key", () => {
    // Spec FR-044b: the homepage and each wiki are separate origins, so the
    // choice is the homepage's own and never travels between them.
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: "Dark" }));

    expect(window.localStorage.getItem(HUB_KEY)).toBe("dark");
  });

  it("starts from the remembered choice rather than defaulting", () => {
    window.localStorage.setItem(HUB_KEY, "light");

    render(<ThemeToggle />);

    expect(screen.getByRole("button", { name: "Light" })).toHaveAttribute("aria-pressed", "true");
  });

  it("falls back to the operating system when storage refuses", () => {
    // Spec FR-044c. A throwing accessor is a real case (private browsing, a
    // locked-down profile), not a defensive flourish.
    const storage = window.localStorage;
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem() {
          throw new Error("denied");
        },
        setItem() {
          throw new Error("denied");
        },
        removeItem() {
          throw new Error("denied");
        },
      },
    });

    try {
      render(<ThemeToggle />);
      expect(screen.getByRole("button", { name: "System" })).toHaveAttribute("aria-pressed", "true");
      // And it still operates - the current page follows the choice even
      // though nothing can be remembered for the next one.
      fireEvent.click(screen.getByRole("button", { name: "Dark" }));
      expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    } finally {
      Object.defineProperty(window, "localStorage", { configurable: true, value: storage });
    }
  });

  it("is operable by keyboard", () => {
    render(<ThemeToggle />);

    const dark = screen.getByRole("button", { name: "Dark" });
    dark.focus();
    expect(document.activeElement).toBe(dark);
  });
});
