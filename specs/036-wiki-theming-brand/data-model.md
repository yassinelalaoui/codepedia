# Phase 1 Data Model: Wiki Theming and Brand Identity

**Feature**: `036-wiki-theming-brand` | **Date**: 2026-09-04

Nothing here is persisted server-side. The only durable state this feature
creates is a single string in the reader's browser; everything else is derived at
render time or at page load. See `research.md` §2 for why the storage key is
shaped the way it is.

---

## ThemePreference

What the reader chose. The only writable state in the feature.

| Field | Type | Notes |
|---|---|---|
| value | `"system"` \| `"light"` \| `"dark"` | The three choices of FR-001. `"system"` is the default (FR-003). |
| storageKey | string | `codepedia:theme:<wikiId>` — see **WikiIdentity**. |

**Where it lives**: `localStorage`, on the reader's machine, per browser.

**Validation rules**

- Any value that is not one of the three literals is treated as `"system"`
  (FR-009). This covers a missing key, a hand-edited value, and a value written
  by a future version.
- Reads and writes are both wrapped in `try`/`catch` and every failure degrades
  to `"system"` with no error surfaced (FR-010). A throwing accessor is a real
  case, not a defensive flourish: private browsing and locked-down profiles both
  produce one.
- Absence is not an error state. It is the normal condition for a first-time
  reader and must be indistinguishable from an explicit `"system"`.

**Lifecycle**

```text
(no key)  --reader picks Light/Dark-->  "light" | "dark"
   ^                                          |
   |                                          |
   +---------- reader picks System -----------+
              (key set to "system")
```

Choosing System writes `"system"` rather than deleting the key. Both behave
identically on read, but writing makes the reader's choice explicit and
inspectable, and avoids a delete path that can fail separately.

---

## WikiIdentity

Distinguishes one generated wiki from another so their preferences cannot
collide.

| Field | Type | Notes |
|---|---|---|
| wikiId | string, 16 hex chars | `sha256(repositoryId)[:16]` |

**Derivation**: from `DocumentationWriter.repositoryId`, which is
`stable_repository_id(root)` — literally `repo::/abs/posix/path`. Hashed with the
same construction `src/cli/paths.py` already uses for `state_id`.

**Why it exists at all**: Chrome collapses every `file://` document into the
single origin `file://` regardless of directory — measured, not assumed
(`research.md` §2). All local wikis therefore share one `localStorage`, so
without a per-wiki key any two wikis would overwrite each other's preference,
violating FR-007.

**Validation rules**

- Stable across runs for a given repository path: the same repository must
  produce the same `wikiId` on every regeneration, or readers lose their
  preference each time the wiki is rebuilt.
- Stable across relocation: moving or renaming the generated wiki folder must not
  change it, which is why it is baked in at generation time rather than derived
  from the page URL.
- Must be a hash, never the raw `repositoryId`. That value contains an absolute
  filesystem path, and it would otherwise be embedded in every page of an
  artifact intended to be shared.

---

## EffectiveTheme

What the reader actually sees. Derived, never stored.

| Field | Type | Notes |
|---|---|---|
| value | `"light"` \| `"dark"` | Only two values — there is no "system" appearance. |

**Derivation**

```text
preference == "light"   ->  light
preference == "dark"    ->  dark
preference == "system"  ->  whatever prefers-color-scheme reports, live
```

**Representation in the DOM**: `data-theme` on the `<html>` element.

| Preference | `data-theme` | Resolved by |
|---|---|---|
| `"system"` | *attribute absent* | `@media (prefers-color-scheme: dark)` |
| `"light"` | `"light"` | `:root:not([data-theme="light"])` guard excludes it from the dark rule |
| `"dark"` | `"dark"` | `:root[data-theme="dark"]` |

Leaving the attribute **absent** for System is the load-bearing choice, and it is
what makes FR-011 work: with scripting unavailable nothing stamps the attribute,
the page lands in exactly the System state, and the CSS behaves as it does today.
The existing selectors in `frontend/src/styles.css` (lines 60, 82) already
implement this table — no CSS state is added.

**State transitions**: on any change to preference or, while System is in effect,
to the OS setting, the wiki must re-derive and re-apply. The OS case requires a
live `matchMedia` listener, not a load-time read (FR-005).

---

## BrandAssetSet

The published artwork. Read-only input, owned by `docs/brand/`.

| Asset | Delivery | Minimum size | Used for |
|---|---|---|---|
| `codepedia-mark-light.svg` | inlined into the shell | 24 px | brand slot, light theme |
| `codepedia-mark-dark.svg` | inlined into the shell | 24 px | brand slot, dark theme |
| `favicon.ico` | copied to `assets/favicon.ico` | — | browser tab |

**Validation rules**

- The brand slot renders at **24 px**, up from today's `size-5` (20 px). Below
  24 px the brand policy forbids the full mark because the magnifier handle
  disappears (FR-017).
- Fills stay exactly as published — `#14274A` and `#FFFFFF` and their inverse. No
  recolouring, drop shadow, gradient or outline (FR-018).
- Inlined copies are stripped of `role`, `aria-label` and `<title>` and marked
  `aria-hidden="true"`, because the brand slot already carries a visible
  "codepedia" wordmark and FR-019 allows exactly one announcement.
- Exactly one variant is visible at a time, decided by CSS rather than script, so
  the correct mark shows before the bundle loads and forever if it never loads.
- Generated output must not reference `docs/brand/` (FR-021).

**Constraint on placement**: the inlined markup must live in a `*.jinja` file
directly in `src/doc_generator/templates/`. `template_fingerprint()` globs that
directory non-recursively for `*.jinja` only, and anything outside that glob is
invisible to the staleness check — a later edit to the artwork would leave every
existing page stale with no signal (`research.md` §6).

---

## DiagramRenderState

Per-diagram state that has to survive a theme change (FR-013, FR-013a).

| Field | Type | Owner | Notes |
|---|---|---|---|
| source | string | `data-diagram-source` on `pre.mermaid` | The original fence text. |
| scale / offsetX / offsetY | numbers | `diagramViewport.ts` closure | Never read by this feature. |
| enhanced | boolean | `data-viewport-enhanced` attribute | Existing double-enhancement guard. |

**Why `source` must be captured before the first render**: `mermaid.run()`
replaces the `<pre class="mermaid">` element's text content with the rendered
SVG. Once it has run, the diagram source is gone from the DOM and there is
nothing left to re-render from. The stash is a precondition, not an optimisation.

**Why the viewport state is listed but never touched**: `{ scale, offsetX,
offsetY }` lives in a closure in `diagramViewport.ts` with no accessor, and is
applied to the wrapper as a CSS transform. Re-rendering by swapping only the
inner `<svg>` leaves that wrapper untouched, so zoom and pan survive *because
nothing captures or restores them*. This satisfies FR-013a with no new state at
all; a full re-enhance would instead reset to `INITIAL_STATE` and lose the
reader's position.

---

## Entities deliberately absent

- **No server-side record.** Nothing about a reader's theme reaches the FastAPI
  app, the SQLite stores, or `~/.codepedia/`.
- **No cross-wiki registry.** Per-wiki independence was confirmed at
  clarification; wikis do not coordinate.
- **No new manifest field.** Page staleness is already handled by
  `template_fingerprint()`; this feature adds nothing to `doc-manifest.sqlite`.
