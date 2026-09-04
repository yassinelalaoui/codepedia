/**
 * The reader's light/dark choice for this wiki (036 data-model.md).
 *
 * The palette already had three states before this module existed - light,
 * OS-dark, and a pinned state overriding the OS in both directions - but
 * nothing in the shipped output ever wrote `data-theme`, so two of the three
 * were unreachable. This is the piece that selects between them.
 *
 * ## Why System is the *absence* of the attribute
 *
 * `styles.css` guards its dark rule on `:root:not([data-theme="light"])`, so an
 * absent attribute already means "follow the OS". Writing `data-theme="system"`
 * would satisfy that guard while matching no `[data-theme="dark"]` rule either,
 * producing a state the stylesheet cannot express. Removing the attribute is
 * also what makes the no-JavaScript path correct for free: nothing runs,
 * nothing is stamped, and the page lands in exactly the System state that
 * readers get today (spec FR-011).
 *
 * ## Why the key is scoped per wiki
 *
 * Chrome reports `location.origin` as `file://` for *every* local document
 * regardless of directory, so all wikis opened from the filesystem share one
 * `localStorage` - measured, not assumed (research.md §2). An unscoped key
 * would let any two wikis silently overwrite each other's theme, which spec
 * FR-007 explicitly forbids. The key therefore carries this wiki's id, which
 * the pre-paint script in `layout.html.jinja` publishes on
 * `window.__WIKI_THEME__` so the key is derived in exactly one place and the
 * two cannot drift apart.
 *
 * Every read and write is wrapped: a throwing accessor is a real case, not a
 * defensive flourish (private browsing, a locked-down profile), and spec FR-010
 * requires the control to keep working for the current page when it happens.
 */

export type ThemePreference = "system" | "light" | "dark";
export type EffectiveTheme = "light" | "dark";

/** Fired after `data-theme` changes, and only when the *effective* theme moved. */
export const THEME_CHANGED_EVENT = "wiki:theme-changed";

const THEME_ATTRIBUTE = "data-theme";
const KEY_PREFIX = "codepedia:theme:";
const DARK_QUERY = "(prefers-color-scheme: dark)";

const PREFERENCES: readonly ThemePreference[] = ["system", "light", "dark"];

declare global {
  interface Window {
    __WIKI_THEME__?: { wikiId?: string; storageKey?: string };
  }
}

/**
 * The storage key for this wiki.
 *
 * Prefers the value the pre-paint script already computed, so the key the
 * bundle writes is byte-identical to the one the `<head>` script read. Falls
 * back to deriving it from the published `wikiId`, and finally to the bare
 * prefix - which only happens in a test harness or a page rendered without the
 * script, where cross-wiki collision is not a concern anyway.
 */
function storageKey(): string {
  const published = window.__WIKI_THEME__;
  if (published?.storageKey) return published.storageKey;
  if (published?.wikiId) return `${KEY_PREFIX}${published.wikiId}`;
  return KEY_PREFIX;
}

function isPreference(value: unknown): value is ThemePreference {
  return typeof value === "string" && (PREFERENCES as readonly string[]).includes(value);
}

/**
 * What the reader chose, or `"system"` for anyone who has not chosen.
 *
 * A missing key, a hand-edited value, and a value written by a future version
 * all resolve the same way (spec FR-003, FR-009). Absence is the normal state
 * for a first-time reader, not an error.
 */
export function readPreference(): ThemePreference {
  let stored: string | null = null;
  try {
    stored = window.localStorage.getItem(storageKey());
  } catch {
    // Storage refused. The reader still gets a working control for this page;
    // it simply will not be remembered on the next one (spec FR-010).
    return "system";
  }
  return isPreference(stored) ? stored : "system";
}

export function writePreference(preference: ThemePreference): void {
  try {
    // "system" is written rather than deleting the key: both read back
    // identically, but writing makes the reader's choice explicit and
    // inspectable, and avoids a delete path that can fail on its own.
    window.localStorage.setItem(storageKey(), preference);
  } catch {
    // Same as above - nothing to fall back to, and nothing worth telling the
    // reader about. The theme still applies to the page they are looking at.
  }
}

function osPrefersDark(): boolean {
  try {
    return window.matchMedia(DARK_QUERY).matches;
  } catch {
    // matchMedia is missing or threw (very old browser, unusual harness).
    // Light is the palette's own default, so it is the honest fallback.
    return false;
  }
}

/** What the reader actually sees: System resolved against the OS. */
export function effectiveTheme(preference: ThemePreference = readPreference()): EffectiveTheme {
  if (preference === "light" || preference === "dark") return preference;
  return osPrefersDark() ? "dark" : "light";
}

function currentAttribute(): string | null {
  return document.documentElement.getAttribute(THEME_ATTRIBUTE);
}

/**
 * Stamps the preference onto `<html>` and announces a real change.
 *
 * The event is deliberately *not* fired when the effective theme is unchanged -
 * re-selecting the active option, or an OS flip while Light or Dark is pinned.
 * Every firing re-renders every diagram on the page
 * (contracts/wiki-theme-shell.md §4), so a spurious one is not free.
 */
export function applyPreference(preference: ThemePreference): void {
  const before = effectiveThemeFromAttribute();
  if (preference === "system") {
    document.documentElement.removeAttribute(THEME_ATTRIBUTE);
  } else {
    document.documentElement.setAttribute(THEME_ATTRIBUTE, preference);
  }
  const after = effectiveTheme(preference);
  if (before === after) return;
  document.dispatchEvent(
    new CustomEvent(THEME_CHANGED_EVENT, { detail: { theme: after, preference } }),
  );
}

/** The theme currently on screen, read from the DOM rather than from storage. */
function effectiveThemeFromAttribute(): EffectiveTheme {
  const attribute = currentAttribute();
  if (attribute === "light" || attribute === "dark") return attribute;
  return osPrefersDark() ? "dark" : "light";
}

export function setPreference(preference: ThemePreference): void {
  writePreference(preference);
  applyPreference(preference);
}

/**
 * Keeps a System reader in step with a live OS change (spec FR-005).
 *
 * Returns a teardown so tests can detach; the wiki itself never calls it, since
 * the listener should live as long as the page.
 */
export function watchSystemTheme(): () => void {
  let media: MediaQueryList;
  try {
    media = window.matchMedia(DARK_QUERY);
  } catch {
    return () => {};
  }
  const onChange = (): void => {
    // Only System defers to the OS; a pinned choice must win in both
    // directions (spec FR-006), and re-applying it would emit no event anyway.
    if (readPreference() !== "system") return;
    applyPreference("system");
  };
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}
