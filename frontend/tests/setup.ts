import "@testing-library/jest-dom/vitest";

// Newer Node versions ship their own experimental global `localStorage`
// (requiring a `--localstorage-file` flag to actually function), which wins
// over jsdom's own implementation and leaves `window.localStorage` an inert,
// method-less object under this Node/vitest-environment-jsdom combination.
// A minimal in-memory Storage polyfill sidesteps that entirely for tests.
class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

if (typeof window !== "undefined" && typeof window.localStorage?.clear !== "function") {
  const storage = new MemoryStorage();
  Object.defineProperty(window, "localStorage", { value: storage, configurable: true });
  Object.defineProperty(globalThis, "localStorage", { value: storage, configurable: true });
}

// jsdom 25 leaves `scrollIntoView` undefined, so production code has to guard it
// with `typeof`. Left unstubbed, that guard is always false under test and the
// whole fragment-scrolling path is skipped - which is exactly how feature 034's
// `setPointerCapture` defect stayed invisible to all 27 of its tests while
// breaking every diagram link in a real browser.
//
// Defining a no-op here makes the guard true, so the path executes and a test
// can spy on it. It proves the call was made on the right element; it can never
// prove the browser scrolled anywhere, which is why the fragment behaviour is
// also checked against real Chrome (quickstart § 2).
if (typeof Element !== "undefined" && typeof Element.prototype.scrollIntoView !== "function") {
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    value: function scrollIntoView(): void {},
    writable: true,
    configurable: true,
  });
}
