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
