import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  THEME_CHANGED_EVENT,
  applyPreference,
  effectiveTheme,
  readPreference,
  setPreference,
  watchSystemTheme,
  writePreference,
} from "../src/lib/theme";

/**
 * Covers the storage contract (036 contracts/wiki-theme-shell.md §3) and the
 * System-is-absence rule (§2.1).
 *
 * What these cannot prove is that the theme is applied *before first paint*.
 * jsdom has no paint, so spec FR-008 is invisible here by construction and is
 * checked against real Chrome instead (quickstart.md §4, check 4.1/4.2).
 */

const KEY = "codepedia:theme:testwiki00000000";

function stubMatchMedia(prefersDark: boolean): void {
  const listeners = new Set<() => void>();
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: prefersDark && query.includes("dark"),
    media: query,
    addEventListener: (_: string, handler: () => void) => listeners.add(handler),
    removeEventListener: (_: string, handler: () => void) => listeners.delete(handler),
    dispatchEvent: () => false,
  }));
}

beforeEach(() => {
  window.__WIKI_THEME__ = { wikiId: "testwiki00000000", storageKey: KEY };
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  stubMatchMedia(false);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("readPreference", () => {
  it("defaults to system when nothing is stored", () => {
    expect(readPreference()).toBe("system");
  });

  it("reads back each of the three values", () => {
    for (const preference of ["system", "light", "dark"] as const) {
      writePreference(preference);
      expect(readPreference()).toBe(preference);
    }
  });

  it("treats an unrecognised stored value as system", () => {
    window.localStorage.setItem(KEY, "chartreuse");
    expect(readPreference()).toBe("system");
  });

  it("treats a value from a future version as system", () => {
    window.localStorage.setItem(KEY, "auto-dim");
    expect(readPreference()).toBe("system");
  });

  it("falls back to system when the storage accessor throws", () => {
    vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(readPreference()).toBe("system");
  });
});

describe("writePreference", () => {
  it("writes the literal 'system' rather than deleting the key", () => {
    writePreference("dark");
    writePreference("system");
    expect(window.localStorage.getItem(KEY)).toBe("system");
    expect(readPreference()).toBe("system");
  });

  it("does not throw when storage refuses the write", () => {
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    expect(() => writePreference("dark")).not.toThrow();
  });

  it("still applies the theme to the current page when storage refuses", () => {
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    setPreference("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("scopes the key to this wiki so another wiki cannot be clobbered", () => {
    writePreference("dark");
    // A second wiki on the same shared file:// origin.
    window.__WIKI_THEME__ = { wikiId: "otherwiki0000000", storageKey: "codepedia:theme:otherwiki0000000" };
    expect(readPreference()).toBe("system");
    writePreference("light");
    // The first wiki's choice survived the second wiki writing its own.
    expect(window.localStorage.getItem(KEY)).toBe("dark");
  });
});

describe("applyPreference", () => {
  it("removes the attribute entirely for system", () => {
    applyPreference("dark");
    applyPreference("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("never writes data-theme='system'", () => {
    applyPreference("system");
    expect(document.documentElement.getAttribute("data-theme")).not.toBe("system");
  });

  it("stamps a pinned choice", () => {
    applyPreference("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    applyPreference("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("emits the change event when the effective theme moves", () => {
    const seen = vi.fn();
    document.addEventListener(THEME_CHANGED_EVENT, seen);
    applyPreference("dark");
    expect(seen).toHaveBeenCalledTimes(1);
    document.removeEventListener(THEME_CHANGED_EVENT, seen);
  });

  it("does not emit when the effective theme is unchanged", () => {
    applyPreference("dark");
    const seen = vi.fn();
    document.addEventListener(THEME_CHANGED_EVENT, seen);
    // Re-selecting the option already in effect must not re-render diagrams.
    applyPreference("dark");
    expect(seen).not.toHaveBeenCalled();
    document.removeEventListener(THEME_CHANGED_EVENT, seen);
  });

  it("carries the effective theme and the preference in the event", () => {
    let detail: unknown = null;
    const capture = (event: Event) => {
      detail = (event as CustomEvent).detail;
    };
    document.addEventListener(THEME_CHANGED_EVENT, capture);
    applyPreference("dark");
    expect(detail).toEqual({ theme: "dark", preference: "dark" });
    document.removeEventListener(THEME_CHANGED_EVENT, capture);
  });
});

describe("effectiveTheme", () => {
  it("resolves system against a light OS", () => {
    stubMatchMedia(false);
    expect(effectiveTheme("system")).toBe("light");
  });

  it("resolves system against a dark OS", () => {
    stubMatchMedia(true);
    expect(effectiveTheme("system")).toBe("dark");
  });

  it("lets a pinned choice win over the OS in both directions", () => {
    stubMatchMedia(true);
    expect(effectiveTheme("light")).toBe("light");
    stubMatchMedia(false);
    expect(effectiveTheme("dark")).toBe("dark");
  });
});

describe("watchSystemTheme", () => {
  it("re-applies when the OS changes while system is selected", () => {
    const handlers: Array<() => void> = [];
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: false,
      media: query,
      addEventListener: (_: string, handler: () => void) => handlers.push(handler),
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }));
    writePreference("system");
    const stop = watchSystemTheme();
    expect(handlers).toHaveLength(1);
    expect(() => handlers[0]()).not.toThrow();
    stop();
  });

  it("ignores an OS change while a pinned choice is in effect", () => {
    const handlers: Array<() => void> = [];
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: true,
      media: query,
      addEventListener: (_: string, handler: () => void) => handlers.push(handler),
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }));
    writePreference("light");
    applyPreference("light");
    const stop = watchSystemTheme();
    const seen = vi.fn();
    document.addEventListener(THEME_CHANGED_EVENT, seen);
    handlers[0]();
    expect(seen).not.toHaveBeenCalled();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    document.removeEventListener(THEME_CHANGED_EVENT, seen);
    stop();
  });
});
