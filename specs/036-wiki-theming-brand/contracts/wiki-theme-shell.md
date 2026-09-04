# Contract: Wiki Theme and Brand Shell

**Feature**: `036-wiki-theming-brand` | **Date**: 2026-09-04

The generated wiki exposes no network API — this contract is the **page shell**:
the markup, attributes and events that the Jinja template, the React bundle, the
stylesheet and the tests all agree on. Anything named here is depended upon by
more than one component, so changing it is a breaking change.

Existing shell contracts live in earlier features' `contracts/`; this one extends
the same shell.

---

## 1. Template context

`render_page_html` passes these to `layout.html.jinja`, alongside the existing
`title`, `home_href`, `ui_style_href`, `ui_script_href`, `mermaid_script_href`,
`search_index_href`, `nav_features`, `page_toc`, `generated_at` and `commit_sha`.

| Name | Type | Contract |
|---|---|---|
| `wiki_id` | `str` | 16 lowercase hex chars. Stable per repository, stable across regeneration and across relocation of the output folder. Never the raw `repositoryId`. |
| `favicon_href` | `str` | Page-relative link to `assets/favicon.ico`, computed with `relative_output_link` so it is correct from diagram pages one directory deeper. |

---

## 2. DOM contract

### 2.1 Theme attribute

`data-theme` on the `<html>` element is the single source of truth for the
applied theme.

| Value | Meaning |
|---|---|
| *absent* | Follow the OS preference. **This is the System state.** |
| `"light"` | Pinned light. |
| `"dark"` | Pinned dark. |

**Rules**

- System MUST be represented by the attribute's *absence*, never by
  `data-theme="system"`. The stylesheet's dark rule is guarded on
  `:root:not([data-theme="light"])`, and a `"system"` value would satisfy that
  guard while also failing to match `[data-theme="dark"]` — leaving a state the
  CSS cannot express. Absence is also what makes the no-JavaScript fallback
  correct by construction (FR-011).
- Only the inline `<head>` script and `lib/theme.ts` write this attribute.
- No component may infer the theme by reading colours; read the attribute, or
  `matchMedia` when it is absent.

### 2.2 Required elements

| Selector | Owner | Contract |
|---|---|---|
| `script` in `<head>`, inline, no `src`/`defer`/`async` | `layout.html.jinja` | Applies the stored preference before first paint. Must be dependency-free and must never throw. |
| `link[rel="icon"]` | `layout.html.jinja` | Points at `favicon_href`. Present on every page. |
| `.brand-mark` | `layout.html.jinja` | Wraps the inlined marks. Renders at 24 px. Hook name is retained and MUST stay first in the class list. |
| `.brand-mark [data-brand-variant="light"]` | `layout.html.jinja` | Inlined `codepedia-mark-light.svg`. `aria-hidden="true"`, no `role`/`aria-label`/`<title>`. |
| `.brand-mark [data-brand-variant="dark"]` | `layout.html.jinja` | Inlined `codepedia-mark-dark.svg`, same stripping. |
| `#wiki-theme-root` | `layout.html.jinja` | Empty mount point in the sidebar. Matches the existing `#wiki-search-root` / `#wiki-toc-root` / `#wiki-chat-root` convention. |
| `.theme-toggle` | `ThemeToggle.tsx` | The segmented control. Hook name queried by tests; MUST stay first in the class list. |

**Brand visibility** is decided by CSS only — exactly one variant visible per
theme, using the same three-state selector shape as the palette. No script
participates, so the correct mark is showing before the bundle loads.

### 2.3 Theme control

| Requirement | Contract |
|---|---|
| Options | Exactly three, in order: System, Light, Dark. |
| Current state | Conveyed without interaction (FR-002) and programmatically via `aria-checked` / `aria-pressed` on the selected option. |
| Accessible name | The control carries one describing its purpose (FR-012). |
| Keyboard | Every option reachable and operable by keyboard alone (FR-012, SC-009). |
| Interaction cost | Any state reachable in one interaction from any other (FR-001). |

---

## 3. Storage contract

| Property | Value |
|---|---|
| Mechanism | `localStorage` |
| Key | `codepedia:theme:<wiki_id>` |
| Values | `"system"` \| `"light"` \| `"dark"` |
| On unreadable / unknown value | Treat as `"system"` (FR-009) |
| On throw | Swallow, treat as `"system"`, surface nothing (FR-010) |

**The key MUST include `wiki_id`.** Chrome reports `location.origin` as `file://`
for every local document regardless of directory, so all wikis on a machine share
one `localStorage` (measured — `research.md` §2). An unscoped key would let any
two wikis silently overwrite each other's preference, breaking FR-007.

---

## 4. Event contract

| Event | Dispatched on | When | Payload |
|---|---|---|---|
| `wiki:theme-changed` | `document` | After `data-theme` is updated and the effective theme has actually changed | `{ theme: "light" \| "dark", preference: "system" \| "light" \| "dark" }` |
| `wiki:mermaid-rendered` | `document` | *(existing)* after the initial `mermaid.run()` settles | none |

`wiki:theme-changed` follows the existing `wiki:mermaid-rendered` convention: a
`CustomEvent` on `document`, so the diagram code and the bundle stay decoupled
from the control that caused the change. It fires for an OS-driven change while
System is in effect, not only for a click.

It MUST NOT fire when the effective theme is unchanged — re-selecting the active
option, or an OS change while Light or Dark is pinned — because each firing
re-renders every diagram on the page.

---

## 5. Diagram re-render contract

| Element / attribute | Contract |
|---|---|
| `pre.mermaid[data-diagram-source]` | Holds the original fence text, stashed **before** the first `mermaid.run()`. |
| `pre.mermaid[data-viewport-enhanced]` | *(existing)* guards against double-enhancement. |

**Required sequence on `wiki:theme-changed`:**

1. Re-initialize Mermaid with the theme matching the new effective theme.
2. Re-render each diagram from its stashed `data-diagram-source`, into a detached
   element.
3. Swap **only** the resulting `<svg>` into the existing viewport wrapper.

Step 3 is the contract, not an implementation detail. The wrapper carries the
reader's zoom and pan as a CSS transform, and its state lives in a closure with
no accessor; replacing the wrapper resets that state to `INITIAL_STATE` and loses
the reader's position, violating FR-013a. Replacing only the inner `<svg>`
preserves it without capturing anything.

A diagram with no stashed source, or one that fails to re-render, MUST be left
exactly as it is — a stale-but-readable diagram beats a blank space, and one
unparseable diagram must not abort the batch. This mirrors the existing
`suppressErrors: true` posture in the bootstrap.

---

## 6. Invariants

Any change violating one of these is a breaking change to the shell.

1. **No network.** No CDN, no webfont, no runtime `fetch`, no external reference
   of any kind. Constitution 2.2, FR-022.
2. **No reference outside the output root.** Generated pages never point at
   `docs/brand/` or anything else outside their own wiki. FR-021.
3. **Degrades without script.** With scripting unavailable the page renders
   completely and follows the OS preference. FR-011.
4. **Never paints the wrong theme.** The attribute is applied before first paint,
   from `<head>`, synchronously. FR-008.
5. **The brand is announced once.** Inlined marks are `aria-hidden`; the visible
   wordmark carries the name. FR-019.
6. **Brand artwork is unmodified.** Published fills, no shadow, gradient or
   outline, clear space preserved, never below 24 px. FR-017, FR-018.
7. **Brand markup stays in `*.jinja` in `TEMPLATES_DIR`.** `template_fingerprint()`
   globs that directory non-recursively for `*.jinja`; markup outside it escapes
   the staleness check and leaves regenerated wikis inconsistent. FR-023.
8. **Print uses the light palette**, whatever is on screen. FR-026.
