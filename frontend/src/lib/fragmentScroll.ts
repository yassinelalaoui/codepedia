/**
 * Fragment (`#heading`) navigation, now that page content scrolls inside
 * `.main` rather than as the whole document.
 *
 * Browsers handle a same-page fragment click reliably even when the scroll
 * container is not the document. The *initial page load* is the unreliable case
 * - and it is the one that matters most here, because every search result
 * pointing at a symbol (`modules/foo.html#bar`) arrives as a fresh page load,
 * and every page in the wiki carries an "On this page" rail.
 *
 * No offset arithmetic lives here: `scroll-padding-top` on `.main` keeps the
 * heading clear of the top edge, and `scroll-behavior` there honours the
 * reader's motion preference. Doing it in JS instead would duplicate both and
 * silently ignore the reduced-motion setting.
 */

/** Scroll to whatever `location.hash` currently names, if anything.
 *
 * Returns the element it scrolled to, or null - a hash naming nothing must
 * leave the page exactly as it is rather than throwing.
 */
export function scrollToCurrentFragment(): Element | null {
  const raw = window.location.hash.replace(/^#/, "");
  if (!raw) return null;

  let id = raw;
  try {
    id = decodeURIComponent(raw);
  } catch {
    // A malformed escape sequence in the URL: fall back to the raw text rather
    // than throwing, since it may still match an id verbatim.
  }

  const target = document.getElementById(id);
  if (!target) return null;
  // Guarded because an old browser may not define it. The test setup stubs the
  // method so this branch is exercised rather than skipped - a `typeof` guard
  // that is always false under test is how feature 034's pointer-capture defect
  // stayed invisible to every one of its tests.
  if (typeof target.scrollIntoView === "function") target.scrollIntoView();
  return target;
}

/** Resolve the fragment now and on every later hash change.
 *
 * Safe to call once at bundle evaluation: this bundle is loaded at the end of
 * `<body>`, so the document is already parsed.
 */
export function installFragmentScrolling(): void {
  window.addEventListener("hashchange", scrollToCurrentFragment);
  scrollToCurrentFragment();
}
