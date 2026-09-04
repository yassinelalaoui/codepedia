# Quickstart: Validating Wiki Theming and Brand Identity

**Feature**: `036-wiki-theming-brand` | **Date**: 2026-09-04

How to prove this feature works end to end. Run these after `/speckit-implement`.

Details live elsewhere and are not repeated here: the DOM and storage contracts
are in [contracts/wiki-theme-shell.md](./contracts/wiki-theme-shell.md), the
derivation rules in [data-model.md](./data-model.md), the reasoning in
[research.md](./research.md).

---

## Prerequisites

- `.venv` on Python 3.11–3.13. **Not 3.14** — Pydantic's schema generation hangs
  there, and the failure looks like a stall, not an error.
- Node available (`node --version`). The bundle builds with the pinned Vite.
- Chrome at `/c/Program Files/Google/Chrome/Application/chrome.exe` for the two
  checks that need a real browser.
- A generated wiki to look at. Any previously indexed repository under
  `~/.codepedia/repos/<state_id>/docs/` works.

---

## 1. Build the bundle — do this first

```bash
cd frontend && npx vite build
```

`src/doc_generator/assets/wiki-ui.{js,css}` are **committed artifacts**. Every
check below reads the built bundle, so a stale build silently invalidates all of
them. Confirm both files show as modified afterwards.

---

## 2. Automated suites

```bash
.venv/Scripts/python.exe -m pytest tests/ \
  --basetemp=<scratchpad>/pytest -p no:cacheprovider

cd frontend && npx vitest run
```

Baselines before this feature: **130 pytest**, **97 vitest**, both green. Pass
`--basetemp` into the scratchpad — a bare `pytest` run produces around 17 spurious
`PermissionError`s on this machine that have nothing to do with the code.

Expect to have touched shell assertions in `tests/unit/test_page_toc.py`,
`tests/integration/test_feature_pages.py` and
`tests/integration/test_doc_generator_cross_references.py`. Those already match on
hooks rather than whole class attributes, so growing the brand slot should not
break them — if one does break, fix the assertion to match on the hook, not by
pinning the new class string.

---

## 3. Regenerate a wiki and inspect the output

```bash
.venv/Scripts/python.exe -m cli.main index <path-to-any-repo>
```

Then, in the generated `docs/` directory:

| Check | Expectation |
|---|---|
| `assets/favicon.ico` exists | Copied, byte-identical to `docs/brand/favicon.ico` |
| `grep -c 'rel="icon"' **/*.html` | Every page, no exceptions |
| `grep -rn 'docs/brand' .` | **No matches** — FR-021 |
| `grep -c 'data-brand-variant' index.html` | Two: the light and dark marks |
| Inline `<head>` script present | Before any `<link>`/body content, no `defer` |
| Every page rebuilt | `template_fingerprint()` changed, so all pages regenerate — not just the ones whose source changed |

That last row is the one worth confirming deliberately: a wiki where some pages
have the new shell and some the old is the exact failure the fingerprint exists to
prevent (`research.md` §6).

---

## 4. Real-browser checks

jsdom cannot see either of these. It has no paint, so the no-flash requirement is
invisible to `vitest` by construction; and it does not model `file://` origins,
which is where the storage-key requirement came from in the first place.

Drive Chrome headless over CDP — no Playwright, no new dependency. Node has global
`WebSocket` and `fetch`, which is all that is needed:

```bash
"/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --headless=new --remote-debugging-port=9333 \
  --allow-file-access-from-files \
  --user-data-dir=<scratchpad>/chrome-profile --no-first-run about:blank &
```

| # | Check | Method | Passes when |
|---|---|---|---|
| 4.1 | No flash on navigation | Pin Dark, navigate 10 pages capturing screenshots at first paint | Zero frames show the light background — **SC-002** |
| 4.2 | Applied before paint | `Runtime.evaluate` on `document.documentElement.dataset.theme` at `Page.domContentEventFired` | Already correct, not set later — **FR-008** |
| 4.3 | Per-wiki isolation | Generate two wikis; set Dark in one, open the other | The second is unaffected — **FR-007**. This is the check that fails with a global key. |
| 4.4 | Offline, relocated | Copy a wiki to an unrelated directory, disconnect, open from `file://` with `Network.enable` | Brand and favicon render; zero network requests — **SC-005, SC-006** |
| 4.5 | Scripting disabled | `Emulation.setScriptExecutionDisabled`, under both OS colour schemes via `Emulation.setEmulatedMedia` | Page renders fully and matches the OS — **SC-007, FR-011** |
| 4.6 | OS change while System | `Emulation.setEmulatedMedia` flips `prefers-color-scheme` with System selected | Theme follows without reload — **FR-005** |
| 4.7 | Diagram re-theme keeps zoom | On a diagram page, zoom and pan, then switch theme | Diagram redraws in the new theme at the same zoom and position — **FR-013a, SC-011** |
| 4.8 | Storage unavailable | Pick a theme in a context where `localStorage` throws | Theme still applies to the page; no error shown — **FR-010** |

4.3 and 4.7 are the two most likely to fail. 4.3 is the one a single-wiki test
cannot catch, and 4.7 is the only place the diagram work can go wrong invisibly.

---

## 5. Manual review

- **Brand slot ≥ 24 px** (FR-017, SC-008). Measure it; do not eyeball it. The
  slot was `size-5` (20 px) and the policy floor is 24 px.
- **Artwork unmodified** (FR-018) — published fills, no shadow, gradient or
  outline, clear space intact.
- **Announced once** (FR-019) — a screen reader should say "codepedia" once, not
  twice. The inlined marks are `aria-hidden`; the visible wordmark carries it.
- **Print preview in dark theme** (FR-026) — dark text on a light background.
- **Keyboard only** (SC-009) — reach all three states with Tab and arrows, no
  mouse.

---

## 6. Regression guard on the CLI

FR-024 says the existing flows behave exactly as before.

```bash
.venv/Scripts/python.exe -m cli.main scan <repo>
.venv/Scripts/python.exe -m cli.main serve <repo>
.venv/Scripts/python.exe -m cli.main provider mode full-local
```

No new prompt, no new required argument, no changed output. `serve` still mounts
the wiki at `/`, and the theme control works there as it does over `file://`.

---

## Done when

- Both suites green, at or above the 130 / 97 baseline.
- Every check in §3 and §4 passes, 4.3 and 4.7 included.
- `wiki-ui.js` and `wiki-ui.css` rebuilt and committed, not drifted from source.
- A wiki opened from `file://` with no network shows the brand, the favicon, a
  working three-state control, and no flash on navigation.
