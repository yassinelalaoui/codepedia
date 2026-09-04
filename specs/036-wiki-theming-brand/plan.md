# Implementation Plan: Wiki Theming and Brand Identity

**Branch**: `036-wiki-theming-brand` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/036-wiki-theming-brand/spec.md`

## Summary

Give the generated wiki a reader-facing System/Light/Dark control and the real
Codepedia brand, without breaking the guarantee that a wiki renders completely
from `file://` with no network.

The palette work is already done — `frontend/src/styles.css` defines all three
states and they are verified working. Nothing in the shipped output has ever
written `data-theme`, which is the entire functional gap. The approach is
therefore small and deliberately split in two: a dependency-free inline script in
`<head>` stamps the stored preference onto `<html>` **before first paint**, and
the segmented control ships in the existing React bundle alongside the search,
chat and TOC widgets. That split is what makes the no-flash requirement (FR-008)
and the scripting-unavailable fallback (FR-011) fall out of the design rather
than needing to be engineered.

Both brand marks are inlined into the shell and swapped by CSS, so the brand is
correct with no JavaScript and nothing is ever fetched. The favicon is copied
into the wiki's own `assets/` through the same `_copy_if_changed` path that
already ships `mermaid.min.js`.

The one substantial piece of work is diagrams. `mermaid.run()` destroys the
diagram source when it renders, so re-theming a rendered diagram requires
stashing that source up front; the reader's zoom and pan are preserved by
swapping only the inner `<svg>` and never touching the transformed wrapper.

## Technical Context

**Language/Version**: Python 3.13 (`.venv`; must stay 3.11–3.13, Pydantic's schema
generation hangs on 3.14) and TypeScript 5 / React 18 for the wiki bundle

**Primary Dependencies**: Jinja2 (page shell), Tailwind CSS v4 (no Preflight),
Vite 5 building a classic IIFE, vendored Mermaid 10. No new dependency is added
by this feature.

**Storage**: Browser `localStorage` on the reader's own machine, one key per
wiki. Nothing is persisted into the generated output, and no server-side or
project storage is involved.

**Testing**: `pytest` for the generator and page shell, `vitest` for the bundle,
plus headless Chrome over CDP for the two properties neither can observe
(pre-paint theming, real `file://` behaviour)

**Target Platform**: A static wiki opened directly from the filesystem in a
desktop browser, with no server and no network. Also served over `localhost` by
`codepedia serve`.

**Project Type**: Static site generator with a small embedded frontend bundle

**Performance Goals**: Zero frames painted in the wrong theme (FR-008); the
pre-paint script must be trivial enough to run synchronously in `<head>` without
being a perceptible cost on every page load.

**Constraints**: No CDN, no webfont, no runtime fetch of any kind — constitution
2.2 and FR-022. Under 2 KB of inlined brand markup per page. The existing CLI
flows must behave identically (FR-024).

**Scale/Scope**: One shared page shell, one new React component, one new inline
script, one asset copy, and a diagram re-render path. Every generated page in
every wiki is affected, which is why the template fingerprint rebuild in §6 of
research matters.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against `.specify/memory/constitution.md` v3.0.0.

| Principle | Applies? | Verdict |
|---|---|---|
| **2.1** Remote engine by default, local mode on explicit choice | No | This feature touches none of the three AI-consuming stages (embeddings, summarization, chat). It adds no engine call and reads no provider configuration. |
| **2.2** Zero network exposure by default | **Yes — the governing principle** | **PASS.** Both brand marks are inlined into the HTML; the favicon is copied into the wiki's own `assets/`; nothing is fetched at runtime, and no CDN or webfont is introduced. The feature moves in the *strengthening* direction: it adds a favicon that a naive implementation would have pulled from a CDN, and inlines it instead. FR-021 additionally forbids referencing `docs/brand/` from generated output, so a wiki stays complete when copied away. |
| **2.3** Automatic fallback only within a configured chain | No | No engine chain is read or modified. |
| **2.4** Traceability of AI answers | No | No AI-generated content is added or altered. Existing citations are untouched. |
| **2.5** Incremental re-indexing | **Yes** | **PASS.** Editing the shared layout makes every written page stale, which `template_fingerprint()` already detects, forcing one complete rebuild (`generator.py` 766-776). That rebuild re-renders HTML from stored Markdown and metadata — no re-parsing, no re-summarization, no model calls — so it is not the full re-analysis 2.5 prohibits. **Binding constraint**: `template_fingerprint()` globs `TEMPLATES_DIR` for `*.jinja` non-recursively, so all new brand markup must live in a `.jinja` file in that directory, or the guarantee silently lapses (research §6). |
| **2.6** Minimal infrastructure, local storage | **Yes** | **PASS.** The only new persistence is a single browser `localStorage` string on the reader's machine. No database, no service, no new file in `~/.codepedia/`. |
| **2.7** Analyzed repository is read-only | **Yes** | **PASS.** No new write path. Generation continues to write only under the documentation output root, which `_ensure_output_root_is_separate` already enforces (`generator.py:739`). FR-025 restates this. |

**Gate result: PASS — no violations, and the Complexity Tracking table below is
therefore empty.**

Two notes worth carrying into implementation:

- 2.2 is not merely satisfied but *load-bearing on a detail*: the inlined SVGs
  must keep their literal `#14274A` / `#FFFFFF` fills. A refactor toward
  `currentColor` would also break the brand README's rule against recolouring the
  lens.
- 2.5's guarantee depends on a non-obvious glob. This is called out in
  `data-model.md` and must appear as an explicit task.

**Post-Phase 1 re-check**: unchanged. The Phase 1 design introduces no new
storage, no new network path, no new engine call, and no write outside the
documentation output root. Gate still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/036-wiki-theming-brand/
├── plan.md              # This file
├── spec.md              # Feature specification (clarified 2026-09-04)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── wiki-theme-shell.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/doc_generator/
├── templates/
│   └── layout.html.jinja        # theme <head> script, theme mount point,
│                                # inlined brand marks, favicon <link>
├── assets/
│   ├── favicon.ico              # NEW — copied from docs/brand/
│   ├── wiki-ui.js               # rebuilt artifact (committed)
│   └── wiki-ui.css              # rebuilt artifact (committed)
├── writer.py                    # FAVICON_* constants + ensure_brand_assets()
├── html_render.py               # favicon_href, wiki_id into template context
├── generator.py                 # pass wiki_id through to the renderer
└── markdown_render.py           # template_fingerprint() — read, not changed

frontend/src/
├── components/
│   └── ThemeToggle.tsx          # NEW — segmented System/Light/Dark control
├── lib/
│   ├── theme.ts                 # NEW — read/write/apply, all in try/catch
│   └── diagramViewport.ts       # SVG swap that preserves zoom/pan
├── main.tsx                     # mount ThemeToggle, wire theme-change event
└── styles.css                   # brand visibility rules, print block

tests/
├── unit/test_page_toc.py             # shell assertions — re-run
├── integration/
│   ├── test_feature_pages.py         # shell assertions — re-run
│   └── test_doc_generator_cross_references.py
└── (new) generator tests for favicon copy, wiki_id, brand markup

frontend/src/**/*.test.ts(x)          # theme lib + ThemeToggle tests
```

**Structure Decision**: Single project, using the directories that already exist.
This feature adds no new top-level structure — deliberately, because a new
template directory would need its own Tailwind `@source` entry (research §8) and a
new asset directory would silently escape `template_fingerprint()` (research §6).
Both are traps the existing layout avoids.

## Implementation Notes

Ordering that matters for `/speckit-tasks`:

1. **The inline `<head>` script and the storage key come first.** Everything else
   depends on `data-theme` actually being stamped, and the key shape (research §2)
   is the thing a later change cannot cheaply undo.
2. **Brand and favicon are independent** of the theme work except for the CSS
   visibility swap, so they can land in parallel.
3. **Diagrams come last** and are the only genuinely risky part. The source-stash
   must be in place before the first `mermaid.run()`, which means editing the
   inline bootstrap in `layout.html.jinja`, not the bundle.
4. **`npx vite build` is not optional.** `src/doc_generator/assets/wiki-ui.{js,css}`
   are committed artifacts; leaving them stale would ship a wiki whose shell and
   bundle disagree.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

No violations. The Constitution Check passes on every applicable principle, so
this table is intentionally empty.
