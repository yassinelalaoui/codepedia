# Implementation Plan: Wiki Web Interface

Branch: `016-wiki-web-interface` | Date: 2026-08-12 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/016-wiki-web-interface/spec.md`

## Summary

Add the browser-side presentation layer the spec describes — a richer
architecture overview on the home page, symbol/function search, and a chat
panel with clickable citation links — without regenerating wiki content,
without changing how the chat API answers, and without changing how the
combined server (015) serves anything. React + TypeScript is used to build
two small, self-contained UI components (a search widget and a chat panel),
compiled at development time into a single vendored, classic-script JS/CSS
bundle checked into the repository exactly like Mermaid's vendored bundle
(013) — not a full single-page app, and not a replacement for
`doc_generator`'s server-rendered pages. The bundle mounts itself into two
container elements added to the shared `layout.html.jinja` (013's pattern),
so every generated page gets the search widget and chat panel for free.

Symbol search and citation-link resolution both read one new generated
artifact, `search-index.json` — a static JSON manifest of every documented
symbol/function name and its wiki page URL, produced by `doc_generator` and
served as a static asset by the existing local server (015). The chat panel
calls the existing chat API (014) with same-origin relative requests, since
015 already serves the wiki and the chat API from one address. The home
page's architecture overview is enhanced server-side, in `home.md.jinja`,
with no new client-side code. Dependency-diagram click navigation (US3) is
reused entirely unchanged from 013.

## Technical Context

Language/Version: Python 3.11+ (generation side, extending `doc_generator`
and `chat_api`); TypeScript 5.x + React 18, compiled with Node.js/npm at
development time only (new — see Constraints)

Primary Dependencies: New development-time-only toolchain — `react`,
`react-dom`, `typescript`, `vite` (build), `vitest` + `@testing-library/react`
(component tests) in a new `frontend/` npm project; no new Python runtime
dependency. Reuses `doc_generator` (012/013), `chat_api` (014/015)
unchanged as the data/API source

Storage: No new persistence. `search-index.json` is a generated,
writer-managed file (like a `DocPage`, regenerated each run — not a static
vendored asset); the compiled UI bundle (`wiki-ui.js`/`wiki-ui.css`) is a
committed, vendored static asset, exactly like `mermaid.min.js` (013)

Testing: Vitest + React Testing Library for the search widget and chat
panel's component logic (fast, jsdom-based, no real browser); pytest for
`search-index.json`'s generated shape/content and for the presence and
non-CDN nature of the vendored bundle references in generated HTML
(mirroring 013's asset-presence tests); no real-browser end-to-end test,
consistent with 013's precedent

Target Platform: The compiled bundle runs in any standard browser, served
by the existing local server (015); Node.js/npm are needed only by someone
building this feature's frontend source, never by someone running the
already-built `repo-scanner`/`chat_api` tools

Project Type: Extension of the existing internal pipeline — a new
`frontend/` npm project (source only) whose committed build output extends
`doc_generator`'s vendored assets, plus small `doc_generator` additions
(search index generation, home page content, shared layout mount points)

Performance Goals: Interactive, single-user local browsing; search
operates over a single repository's symbol index (typically hundreds to a
few thousand entries) entirely client-side, with no perceptible delay

Constraints: The vendored bundle MUST be a classic (non-`type="module"`)
script, consistent with 013's Decision 2 vendoring convention; the search
widget and chat panel both require the wiki to be served over HTTP (015) —
`fetch()` calls to `search-index.json` and to the chat API do not work when
a page is opened directly via `file://`, which is a new, explicit
narrowing of scope for these two specific widgets (not for the rest of the
wiki, whose existing file://-compatibility per 012/013 is unaffected);
Node.js/npm are a development-time dependency only and MUST NOT become a
runtime requirement for the shipped tool

Scale/Scope: One search index and one chat panel per generated wiki,
shared across every page via the shared layout; no per-page bundle
duplication

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentialite absolue: pass; the search widget and chat panel only
  fetch already-local data (`search-index.json`, the already-local chat
  API) from the same origin; no new outbound network calls
- Zero exposition reseau par defaut: pass; no change to 015's bind
  behavior — the new UI is static assets served by the existing local-only
  server
- Jamais de repli silencieux vers le cloud: pass; not applicable — the chat
  panel surfaces 014's existing local-only error responses unchanged, with
  no new inference path
- Tracabilite des reponses IA: pass; the chat panel renders every citation
  from 014's response (`citedSymbolIds`/`citedFilePaths`) as a visible,
  clickable link rather than hiding or summarizing them away
- Re-indexation incrementale: not applicable; this feature does not touch
  indexing
- Infrastructure minimale et stockage local: pass, with an explicit note —
  Node.js/React/Vite are introduced for the first time in this project, but
  strictly as a *development-time* toolchain that produces a committed,
  vendored static bundle (`wiki-ui.js`/`wiki-ui.css`), exactly like
  Mermaid's vendored bundle (013 Decision 2). No Node process, build step,
  or new dependency is required to *run* the already-built tool; the
  runtime footprint is unchanged (still SQLite + files + the existing local
  server). This mirrors 013's own reasoning for rejecting a Node-based
  `mermaid-cli` at generation time — the distinction here is that this
  feature's own deliverable *is* browser-side UI code, which necessarily
  has a source language, and TypeScript/React was the tech direction given
  for that source, same as FastAPI was given for 014
- Depot analyse en lecture seule: pass; unaffected — `search-index.json`
  and the enhanced home page are written only inside the existing
  `outputRoot`, through the existing containment guard

## Project Structure

### Documentation for this feature

`specs/016-wiki-web-interface/`
- `spec.md`
- `plan.md`
- `research.md`
- `data-model.md`
- `quickstart.md`
- `contracts/`
  - `search-index.md`
  - `ui-mount-points.md`

### Source Code

`frontend/` (new npm project; source only — its build output is committed
separately into `src/doc_generator/assets/`, not this directory)
- `package.json`, `tsconfig.json`, `vite.config.ts`
- `src/`
  - `main.tsx` (entry point: mounts `SearchWidget` and `ChatPanel` into the
    layout's container elements)
  - `components/SearchWidget.tsx`
  - `components/ChatPanel.tsx`
  - `lib/searchIndex.ts` (fetches and queries `search-index.json`)
  - `lib/chatApiClient.ts` (same-origin `fetch` wrapper for 014's endpoints)
  - `styles.css`
- `tests/`
  - `SearchWidget.test.tsx`
  - `ChatPanel.test.tsx`

`src/`
- `doc_generator/`
  - `search_index.py` (new: builds `search-index.json`'s content from the
    current documentation bundle)
  - `assets/`
    - `wiki-ui.js`, `wiki-ui.css` (new: committed, vendored build output
      of `frontend/`)
  - `generator.py` (modified: enhance `generateOverviewPage`'s architecture
    summary; wire search-index generation into
    `generateRepositoryDocumentation`)
  - `writer.py` (modified: `ensure_wiki_ui_assets()` for the vendored
    bundle, alongside writing `search-index.json` as a regular
    writer-managed generated file)
  - `templates/`
    - `home.md.jinja` (modified: richer architecture overview content)
    - `layout.html.jinja` (modified: load the vendored bundle and add the
      search/chat mount-point `<div>`s)
- `chat_api/` (reused, unmodified: the chat panel calls its existing
  endpoints as-is)

`tests/`
- `unit/test_search_index.py` (new: `search_index.py`'s generated content)
- `integration/test_wiki_ui_assets.py` (new: vendored bundle presence,
  non-CDN/non-module script tag, mount points present in rendered HTML)

Structure Decision: keep `doc_generator`'s Python-side additions inside
that existing package (mirroring 013's own choice), and introduce exactly
one new top-level directory, `frontend/`, for the React/TypeScript source —
kept separate from `src/` because it is a different language toolchain
with its own dependency manifest, not because it is a different runtime
component. Its *build output* is what actually ships, committed into
`doc_generator/assets/` alongside the existing vendored Mermaid bundle.

## Phase 0: Research

### Decision 1

Build the search widget and chat panel as small, self-contained React
components compiled into one vendored bundle, rather than a full SPA that
replaces `doc_generator`'s server-rendered pages.

### Decision 2

Configure Vite to emit a classic (non-`type="module"`) IIFE bundle,
consistent with 013's Mermaid-vendoring convention, even though these new
widgets require HTTP serving (015) regardless of script type.

### Decision 3

Generate `search-index.json` as a plain static JSON file, listing every
documented symbol/function's name and wiki page URL, served by 015's
existing static mount; the search widget fetches and searches it entirely
client-side — no new backend search endpoint.

### Decision 4

The chat panel calls 014's chat API with same-origin relative `fetch`
requests, relying on 015 already serving the wiki and the chat API from one
address — no CORS configuration or configurable API base URL needed.

### Decision 5

Citation-link resolution in the chat panel reuses the same
`search-index.json` manifest as the search widget, rather than a second,
separate lookup structure.

### Decision 6

Enhance the home page's architecture overview server-side, in
`home.md.jinja`/`generateOverviewPage`, rather than as a React component —
it is static, generation-time content with no need for client-side
interactivity.

### Decision 7

Give each function/class/method heading in a module page an explicit
anchor id via python-markdown's built-in `attr_list` extension (already
available; `Markdown>=3.6` is an existing dependency), reusing each
symbol's existing stable id, rather than relying on the `toc` extension's
auto-generated heading slugs.

### Decision 8

Commit the compiled `wiki-ui.js`/`wiki-ui.css` bundle into
`src/doc_generator/assets/` as a vendored artifact, exactly like
`mermaid.min.js` (013) — Node.js/npm remain a development-time-only
dependency, never required to run the already-built tool.

### Decision 9

Test the React components with Vitest + React Testing Library (fast,
jsdom-based) instead of a real-browser end-to-end test, consistent with
013's own precedent of leaving headless-browser rendering out of scope for
this project's test suite.

## Phase 1: Design

### Data model

Define `SearchIndexEntry` / `SearchIndexDocument` (the generated JSON
manifest) and `WikiUiBundle` (the vendored build output, mirroring 013's
`VendoredMermaidAsset`); reuse every existing `doc_generator` and
`chat_api` entity unchanged. See `data-model.md`.

### Contracts

Document `search-index.json`'s schema in `contracts/search-index.md`, and
the shared layout's mount-point/script-loading contract in
`contracts/ui-mount-points.md`. The chat panel's API contract is 014's
existing `specs/014-local-chat-api/contracts/chat-api.md`, referenced
unchanged.

### Quickstart

Provide validation steps that generate a wiki with the enhanced home page
and search index, serve it via 015, confirm the search widget finds a real
function and navigates to its anchor, confirm the chat panel gets an answer
with working citation links, and confirm no CDN reference or `type="module"`
script appears anywhere.

## Constitution Check After Design

No violations introduced by the chosen design. The new development-time
npm toolchain produces a committed, vendored static artifact with no
runtime footprint change; no new outbound network path; no new persistent
storage beyond one generated JSON file already covered by `outputRoot`'s
existing containment guarantees.
