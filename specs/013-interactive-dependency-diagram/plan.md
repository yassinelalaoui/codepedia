# Implementation Plan: Interactive Dependency Diagram

Branch: `013-interactive-dependency-diagram` | Date: 2026-08-12 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/013-interactive-dependency-diagram/spec.md`

## Summary

Turn each module's existing diagram page (produced by the `doc_generator`
package since feature 012) from a static Markdown table of edges into an
interactive, click-navigable diagram, rendered entirely client-side in the
browser with Mermaid.js. The diagram is generated directly from the same
`DiagramExport` that `DependencyGraph.exportDiagram()` already produces — no
new dependency analysis is introduced. A vendored, local copy of Mermaid's
classic (non-module) browser bundle is copied into every generated
documentation output so the diagram renders with zero network requests, even
when the page is opened directly from local files.

Each diagram node gets a `click` directive pointing at its module's HTML
page, resolved through the same relative-link machinery `doc_generator`
already uses for `PageLink`s. The existing static "Related modules" list and
"Edges" table stay in place alongside the new diagram, so there is a working
fallback whenever interactive rendering is unavailable.

## Technical Context

Language/Version: Python 3.11+ (generation side, extending the existing
`doc_generator` package); vendored Mermaid.js classic UMD browser bundle
(client-side JavaScript, no build step, no bundler) for the rendered diagram

Primary Dependencies: Existing `doc_generator` and `dependency_graph`
packages (reused, no new Python dependency); a vendored, offline Mermaid.js
browser bundle checked into `src/doc_generator/assets/` and copied into each
generated documentation output as a static asset

Storage: No new persistence; reuses 012's existing page manifest. The
vendored Mermaid asset is a static file copied into `outputRoot/assets/`, not
tracked as a per-page manifest entry

Testing: pytest, asserting the generated Markdown/HTML contains the expected
Mermaid fenced block, the `<pre class="mermaid">` element, correct `click`
hrefs, and the presence of the local (non-CDN) script reference; no
headless-browser rendering test (out of scope for this local Python suite)

Target Platform: Any standard web browser with JavaScript enabled, opening
the generated documentation from local files or a static host; generation
itself runs on Windows/macOS/Linux like the rest of the toolchain

Project Type: Extension of the existing internal documentation-generation
library (`doc_generator`, feature 012); adds a browser-side rendering asset
bundled with its output

Performance Goals: A module's direct-dependency diagram (typically a handful
to a few dozen nodes) renders instantly in-browser; no attempt to render
repository-scale graphs

Constraints: Zero network requests at view time (Mermaid is vendored, not
CDN-loaded); must render correctly opened via `file://` with no local web
server, which rules out Mermaid's ES-module build (blocked by browser CORS
policy under `file://`) in favor of its classic script build; the existing
static edge listing remains as a no-JS fallback; `DocPage.contentMarkdown`
stays the canonical, versionable Markdown source, now including a
` ```mermaid ` fenced block, with HTML still fully derived from it per 012's
Decision 2

Scale/Scope: One Mermaid diagram embedded per existing diagram page (one per
module), each scoped to that module's direct dependencies only

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentiality absolute: pass; the diagram is built only from already-local
  dependency-graph data, and the vendored Mermaid script makes no network
  calls
- Zero exposure network by default: pass; every generated page renders with
  zero runtime network requests, verified by vendoring instead of CDN-loading
  the rendering library
- Never reply silently with a cloud service: pass; not applicable — no
  inference happens here, and there is no CDN fallback path to silently
  degrade into
- Traceability of AI responses: pass; not applicable, the diagram renders
  structural dependency data only, already covered by 004/012's traceability
- Incremental local operation: pass; reuses 012's existing incremental
  diagram-page regeneration unchanged; the diagram is recomputed as part of
  that same page's content on every (re)generation
- Minimal infrastructure and local storage: pass; adds one static local JS
  file and no new service, database, or build toolchain
- Repository analysis read-only: pass; unaffected — still only writes inside
  the existing documentation output folder

## Project Structure

### Documentation for this feature

`specs/013-interactive-dependency-diagram/`
- `spec.md`
- `research.md`
- `data-model.md`
- `quickstart.md`
- `contracts/`
  - `mermaid-diagram-render.md`

### Source Code

`src/`
- `doc_generator/`
  - `mermaid_diagram.py` (new: builds `MermaidDiagramSource` from a
    `DiagramExport`)
  - `assets/`
    - `mermaid.min.js` (new: vendored Mermaid classic UMD browser bundle)
  - `generator.py` (modified: wire `MermaidDiagramSource` into
    `generateDependencyDiagramPage`)
  - `html_render.py` (modified: rewrite the mermaid fenced block into a
    `<pre class="mermaid">` element; pass the assets-relative script path to
    the layout)
  - `writer.py` (modified: ensure `outputRoot/assets/mermaid.min.js` exists,
    as a writer-managed non-page file)
  - `templates/`
    - `diagram.md.jinja` (modified: embed the ` ```mermaid ` fenced block
      above the existing links/table)
    - `layout.html.jinja` (modified: load the vendored script and call
      `mermaid.initialize({ startOnLoad: true })`)
- `dependency_graph/`
  - `graph.py` (reused, unmodified: `DependencyGraph.exportDiagram()`)

Structure Decision: keep this feature entirely inside the existing
`doc_generator` package rather than introducing a new one. It is a rendering
enhancement of the diagram pages that package already owns end-to-end (page
modeling, templating, link resolution, and file writing per 012's own
Structure Decision), so it adds one more templating/asset concern to that
same package instead of a new dependency between packages.

## Phase 0: Research

### Decision 1

Represent each diagram as Mermaid `flowchart` syntax generated from the
existing `DiagramExport`, using Mermaid's native `click NodeId href "url"`
directive for navigation instead of hand-written JS event handling.

### Decision 2

Vendor Mermaid's classic (non-module) UMD browser bundle locally and copy it
into every generated documentation output, rather than loading it from a
CDN — required both by the no-network constraint and because ES-module
scripts are blocked by browser CORS policy under `file://`.

### Decision 3

Add the Mermaid diagram alongside the existing static edge/link content from
012 rather than replacing it, so the no-JS fallback required by the spec's
edge case exists for free.

### Decision 4

Turn the Markdown-rendered mermaid fenced code block into a
`<pre class="mermaid">` element with one small, targeted HTML post-processing
step, instead of writing a custom `python-markdown` extension.

### Decision 5

Resolve every Mermaid node's `click` href with the existing generic
`links.relative_output_link()` helper, targeted at HTML output paths, reusing
the same "drop unresolved targets" rule already enforced for `PageLink`s.

### Decision 6

Give each Mermaid node a short synthetic id (`n0`, `n1`, …) scoped to one
diagram, since Mermaid identifiers cannot contain the characters in the
existing stable page-id scheme.

### Decision 7

Load and initialize the vendored Mermaid script once from the shared HTML
layout on every page, rather than conditionally on diagram pages only —
`startOnLoad` is a cheap no-op on pages with no `.mermaid` elements.

## Phase 1: Design

### Data model

Define the new `MermaidDiagramSource` (rendered flowchart text, node-id
mapping, click targets) and `VendoredMermaidAsset` (the local script file and
its copied location) entities; reuse `DiagramExport`, `DependencyNode`,
`DependencyEdge` (004) and `DocPage`, `PageLink` (012) unchanged.

### Contracts

Document the `build_mermaid_source` function contract, the Markdown/HTML
embedding expectations (fenced block → `<pre class="mermaid">`, script
loading, initialization), the local-asset guarantees the writer must uphold,
and failure behavior when the vendored asset is missing or a diagram's nodes
cannot all be resolved to current pages.

### Quickstart

Provide validation steps that prove a diagram renders interactively with
zero network requests, that every node navigates to the correct page, that
diagrams stay scoped to direct dependencies even in a larger repository, that
the static fallback remains available without JavaScript, and that the
vendored asset is present, locally referenced, and not needlessly rewritten.

## Constitution Check After Design

No violations introduced by the chosen design.