# Phase 0 Research: Wiki Theming and Brand Identity

**Feature**: `036-wiki-theming-brand` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

Every decision below was checked against the working tree, and §2 was verified
empirically in Chrome rather than assumed.

---

## §1 Applying the theme before first paint

**Decision**: A small inline `<script>` in `<head>` of `layout.html.jinja` reads
the stored preference and stamps `data-theme` on `<html>` before the body is
parsed. The segmented control itself ships in the React bundle and mounts into a
`<div id="wiki-theme-root">` in the sidebar.

**Rationale**: `wiki-ui.js` is loaded by a plain `<script>` at the end of
`<body>` (`layout.html.jinja` line 84). A theme applied from that bundle runs
after the document has already been parsed and painted, so a reader who chose
Dark gets a white flash on every single navigation — spec FR-008 forbids exactly
this. Only markup in `<head>`, executed synchronously before the body renders,
can set the attribute in time. The script is deliberately tiny and dependency
free: it must not need the bundle, must not be `defer`red, and must not throw.

The control is a separate concern from applying the theme, and belongs in the
bundle where the rest of the wiki's interactive UI already lives
(`SearchWidget`, `ChatPanel`, `TocHighlighter` all mount this way). This split is
also what makes FR-011 fall out for free: with scripting unavailable, neither the
inline script nor the bundle runs, no `data-theme` is stamped, and the existing
`@media (prefers-color-scheme: dark)` rule governs — which is precisely today's
behaviour.

**Alternatives considered**:

- *Toggle entirely inside the React bundle.* Rejected: guarantees a flash on
  every page load, violating FR-008.
- *A `<noscript>` fallback stylesheet.* Unnecessary — the CSS already degrades
  correctly, because the dark rule is guarded on `:root:not([data-theme="light"])`
  and an absent attribute satisfies that selector.

---

## §2 Scoping the stored preference per wiki

**Decision**: Key the stored preference as `codepedia:theme:<wiki_id>`, where
`wiki_id` is a 16-character hex digest of the repository id, baked into each page
by the generator and read by the inline script.

**Rationale — this was measured, not assumed.** Two throwaway wikis were written
to separate directories and driven in real Chrome (`--headless=new`, CDP,
`--allow-file-access-from-files`):

| Probe | Result |
|---|---|
| `location.origin` at `…/wikiA/index.html` | `file://` |
| `localStorage.setItem("cp-theme","dark")` in wikiA | succeeded |
| `localStorage.getItem("cp-theme")` in **wikiB** | `"dark"` |

Chrome collapses every `file://` document into **one shared origin** regardless
of directory, so all local wikis share a single `localStorage`. A naive global
key such as `codepedia-theme` would therefore let any two wikis silently
overwrite each other's preference — a direct violation of FR-007, which requires
that separate wikis "remember their own choices independently and MUST NOT
overwrite one another". The bug would never appear in a single-wiki test and
would be reported later as "my theme keeps changing on its own".

`wiki_id` is derived from `DocumentationWriter.repositoryId` (already plumbed
through the generator), hashed the same way `src/cli/paths.py`'s `state_id` hashes
it. Hashing matters: `repositoryId` is literally `repo::/abs/posix/path`, and
embedding a raw filesystem path into every generated HTML page would leak the
author's directory layout into an artifact meant to be shared.

**Alternatives considered**:

- *Derive identity at runtime from `new URL(home_href, location.href)`.* Needs no
  Python plumbing and is genuinely elegant, but the key changes the moment the
  reader moves or renames the wiki folder, silently resetting their preference.
  Rejected for that; the generated id survives relocation, which US4 explicitly
  cares about.
- *`sessionStorage`.* Fails FR-007 — does not survive closing the browser.
- *A cookie.* Blocked entirely for `file://` documents.

---

## §3 Delivering the brand marks

**Decision**: Inline **both** the light and dark mark SVGs into the page shell,
and let CSS decide which is visible using the same three-state selectors the
palette already uses. Strip each SVG's `role`, `aria-label` and `<title>` and mark
the wrappers `aria-hidden="true"`.

**Rationale**: The two marks are 965 and 964 bytes; inlining both costs under 2 KB
per page and buys three things at once. It satisfies constitution 2.2 and FR-022
absolutely — there is nothing to fetch, so nothing can be fetched. It makes the
theme swap work with **no JavaScript at all**, since visibility is decided by the
same CSS that decides the palette, which means the mark is correct even before
the bundle loads and correct forever if it never loads. And it sidesteps the fact
that an `<img src>` cannot respond to a `data-theme` attribute on an ancestor.

The accessibility stripping is required by FR-019. Both files ship with
`role="img" aria-label="Codepedia"` and a `<title>` element, and the brand slot
already contains a *visible* `codepedia` wordmark
(`layout.html.jinja` line 14). Inlined as-published, a screen reader would
announce "Codepedia" twice — once for the graphic, once for the text. The
existing placeholder is already `aria-hidden="true"`; that treatment carries over.

**Alternatives considered**:

- *One SVG using `currentColor`.* Rejected outright: the brand README forbids
  recolouring the lens, and the two-tone contrast is the whole point of the mark.
- *`<img src="assets/brand-mark-light.svg">` with a JS swap.* Two extra files, a
  flash before JS runs, and a swap that fails without the bundle.
- *CSS `background-image` with a `data:` URI.* Works, but buries brand artwork
  inside a stylesheet where nobody will find it to update.

---

## §4 Delivering the favicon

**Decision**: Copy `docs/brand/favicon.ico` into the generated wiki's `assets/`
directory and reference it with a page-relative
`<link rel="icon" href="{{ favicon_href }}">`.

**Rationale**: `favicon.ico` is 5,543 bytes — around 7.4 KB as base64, on every
page — so unlike the marks it is not worth inlining. Copying satisfies FR-020 and
FR-021 (the wiki must not reference `docs/brand/`), and `DocumentationWriter`
already has exactly the right mechanism in `_copy_if_changed`, used today for
`mermaid.min.js`, `wiki-ui.js` and `wiki-ui.css`. The href is computed with
`relative_output_link` alongside the existing `ui_style_href` and
`mermaid_script_href`, which is what makes it correct on diagram pages that sit a
directory deeper.

**Alternatives considered**:

- *A `data:` URI in `<link>`.* Rejected on weight, repeated on every page.
- *Referencing `docs/brand/favicon.ico` directly.* Violates FR-021 and breaks the
  moment the wiki is copied anywhere.

---

## §5 Re-rendering diagrams on a theme change

**Decision**: Before the first `mermaid.run()`, stash each diagram's source text
in a `data-diagram-source` attribute. On a theme change, re-initialize Mermaid
with the matching built-in theme, re-render from the stashed source into a
detached element, and swap only the resulting `<svg>` into the existing viewport
wrapper — leaving the wrapper's CSS transform untouched.

**Rationale**: This is the largest item in the feature and the design turns on
one fact: `mermaid.run({ querySelector: '.mermaid' })` **replaces the
`<pre class="mermaid">` element's text content with the rendered SVG**. After the
first render the diagram source no longer exists in the DOM, so there is nothing
left to re-render from. Stashing the source first is not an optimisation, it is a
precondition.

Swapping only the `<svg>` is what satisfies FR-013a for free. `diagramViewport.ts`
holds `{ scale, offsetX, offsetY }` in a closure and writes it to the wrapper as
`transform: translate(...) scale(...)` (line 201); it is not exposed and there is
no API to read it back. Tearing down and re-enhancing the diagram would reset it
to `INITIAL_STATE` (line 58) and throw away the reader's position. Replacing the
inner `<svg>` while leaving the transformed wrapper in place means the zoom and
pan survive because they were never touched — no state needs to be captured,
serialized or restored at all.

The existing `data-viewport-enhanced` marker (line 46) already guards the sweep
against double-enhancement, so a swapped-in SVG inside an already-enhanced
wrapper will not be re-processed.

**Alternatives considered**:

- *Expose get/set state on `diagramViewport` and restore after a full re-enhance.*
  More moving parts, and a restore that has to survive a changed SVG size.
- *Theme-neutral diagram colours with no re-render* (option B at clarification).
  Cheapest, but the user chose full fidelity.
- *Re-render on next page load only.* Rejected at clarification.

---

## §6 Keeping regenerated wikis consistent

**Decision**: Rely on the existing `template_fingerprint()` mechanism. Put all new
brand markup inside `layout.html.jinja` (or another `*.jinja` file in the same
directory), never in a `.svg` sidecar or a subdirectory.

**Rationale**: FR-023 requires that regenerating a wiki brings it up to date, and
there was a plausible failure here — an incremental re-index refreshes assets but
would leave already-written HTML alone, producing a wiki with the new stylesheet
but no theme control and no favicon. It turns out this is already solved:
`generator.py` (lines 766-776) compares `template_fingerprint()` against the
stored value and forces a **complete** rebuild when templates change, treating an
unknown fingerprint as stale. Editing the layout therefore rebuilds every page
automatically. Nothing new is needed.

**The constraint this imposes**: `template_fingerprint()` hashes
`TEMPLATES_DIR.glob("*.jinja")` — non-recursive, and `.jinja` only
(`markdown_render.py` line 54). Brand SVGs placed in a subdirectory, or as
standalone `.svg` files, would be **invisible to the fingerprint**, and editing
one would leave every existing page stale with no signal. Keeping the markup in a
`.jinja` file in `TEMPLATES_DIR` keeps the existing guarantee intact. If a future
change does need a new asset directory, `template_fingerprint()` must be extended
in the same commit.

This also keeps constitution 2.5 satisfied: the rebuild re-renders HTML from
already-stored Markdown and metadata. It triggers no re-parsing, no
re-summarization and no model calls, so it is not the full re-analysis that 2.5
prohibits.

---

## §7 Print output

**Decision**: One `@media print` block in `@layer base` that pins the light
palette tokens.

**Rationale**: FR-026, scoped minimal at clarification. It must be a token
override rather than a set of colour rules so it inherits everything the palette
already defines.

**Constraint**: it must go **in a layer**. Per the repository's own hard-won note
in `styles.css`, unlayered CSS outranks every cascade layer, so an unlayered print
block would win against utilities in ways that are painful to debug.

---

## §8 Styling constraints inherited from the Tailwind v4 migration

These are existing repository invariants, restated because this feature touches
exactly the files they govern. All were verified in `frontend/src/styles.css`.

| Constraint | Consequence here |
|---|---|
| Preflight is deliberately not imported | An inlined `<svg>` gets no reset; size it explicitly rather than relying on one. |
| `@source "../../src/doc_generator/templates/"` (line 24) | Already covers `layout.html.jinja`, so new shell classes are picked up. A **new** template directory would need its own `@source` or its classes get tree-shaken. |
| Tokens map through `@theme inline` (line 113) | The `inline` is required; without it utilities snapshot the light palette and dark mode half-breaks. Do not touch. |
| Retained CSS lives in `@layer base` / `@layer components` | The print block and any new element rules go in a layer. |
| Semantic class names are hooks that JS and tests query | Keep the hook first in the class list — `.brand-mark`, and a new `.theme-toggle`. |
| Three theme states already defined (lines 60, 82) | Reuse the exact selector shape for the brand swap; do not invent a fourth state. |

---

## §9 Verification approach

**Decision**: Assert in `pytest` and `vitest` as usual, and verify the two
properties that neither can see — no-flash and true offline rendering — in real
Chrome over CDP.

**Rationale**: jsdom has no paint, so FR-008 is invisible to `vitest` by
construction; and jsdom does not model `file://` origins, which is the exact thing
§2 turned up. Chrome is at
`/c/Program Files/Google/Chrome/Application/chrome.exe` and drives headless over
CDP with no Playwright and no new dependency — Node has global `WebSocket` and
`fetch`, which is all the probe in §2 used.

Existing markup assertions match on hooks rather than whole class attributes
(e.g. `tests/integration/test_feature_pages.py`), so growing the brand slot from
`size-5` to 24 px should not break them — but `tests/unit/test_page_toc.py` and
`tests/integration/test_doc_generator_cross_references.py` both assert on the
shell and must be re-run.
