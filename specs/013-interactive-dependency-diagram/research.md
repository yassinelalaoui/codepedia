# Research: Interactive Dependency Diagram

## Decision 1: Represent each diagram as Mermaid flowchart syntax generated from `DiagramExport`

Decision: Generate a Mermaid `flowchart` text block from the existing
`DiagramExport` returned by `DependencyGraph.exportDiagram()` (already used by
`doc_generator.diagrams.build_module_diagram` since 012), rather than building
a bespoke SVG/canvas renderer.

Rationale: Mermaid is a mature, pure client-side JS/SVG diagramming library
with native support for directed graphs and, critically, a `click NodeId href
"url"` directive that satisfies the node-click-to-navigate requirement (US2)
without any hand-written JS event handling. Emitting it as a fenced
` ```mermaid ` block also means the committed Markdown renders as a real
diagram on GitHub/GitLab for free, consistent with 012's "Markdown is the
canonical, versionable artifact" design.

Alternatives considered: A hand-built SVG renderer was rejected as
reimplementing a well-tested library for no benefit. Graphviz/DOT was
rejected because producing a viewable diagram from DOT needs either a native
rendering step at generation time or a WASM build in the browser, both
heavier than embedding one JS file.

## Decision 2: Vendor the Mermaid UMD (classic script) browser bundle locally instead of loading it from a CDN

Decision: Ship a local copy of Mermaid's classic UMD build as
`src/doc_generator/assets/mermaid.min.js`, and have the documentation writer
copy it into `outputRoot/assets/mermaid.min.js` for every generated
documentation set. Every page's HTML layout loads it via a relative,
non-module `<script src="…assets/mermaid.min.js">` tag.

Rationale: The spec requires zero network requests to an external rendering
service and correct rendering when the generated documentation is opened
directly from local files. A CDN script tag would violate both. Just as
importantly, Mermaid's ES-module build cannot be used here: browsers treat
`file://` as an opaque origin and block `type="module"` script loading under
it, so only the classic (non-module) UMD bundle renders correctly without a
local web server. Vendoring that build keeps the whole documentation set
self-contained and offline, consistent with the project's local-only
constitution.

Alternatives considered: Loading Mermaid from a CDN was rejected outright.
Pre-rendering diagrams to static SVG at generation time (e.g., shelling out
to a Node-based `mermaid-cli`) was rejected because it would add a Node.js
toolchain dependency to a pure-Python project, contradicting the "minimal
infrastructure" principle, and would also lose the click-to-navigate
interactivity unless hand-rolled back in as custom SVG `<a>` wrapping.

## Decision 3: Add the Mermaid diagram alongside the existing static edge/link content, not instead of it

Decision: Keep `diagram.md.jinja`'s existing "Related modules" link list and
"Edges" table from 012, and add the Mermaid flowchart block above them.

Rationale: The spec's edge case requires a fallback when JavaScript is
unavailable. Keeping the pre-existing plain Markdown content means that
fallback exists for free, and a Mermaid-unaware Markdown viewer (or a user
reading the raw `.md` file) still gets a usable page.

Alternatives considered: Replacing the table entirely with only the Mermaid
block was rejected because it would leave no fallback for the no-JS/edge case
and would make the committed Markdown less self-sufficient outside a
Mermaid-aware renderer.

## Decision 4: Turn the rendered fenced code block into a Mermaid-recognized element with a small, targeted HTML post-processing step

Decision: After `html_render.py` converts `contentMarkdown` to HTML via
`python-markdown`'s `fenced_code` extension (which emits
`<pre><code class="language-mermaid">…</code></pre>`), apply one targeted
string transform that rewrites that specific block to
`<pre class="mermaid">…</pre>` — the element shape Mermaid's default
`startOnLoad` auto-discovery scans for.

Rationale: This avoids writing and maintaining a custom `python-markdown`
extension for a single, mechanical rewrite, and keeps `DocPage.contentMarkdown`
as plain, portable Markdown with no HTML-specific authoring concessions.

Alternatives considered: A custom Markdown extension was rejected as more
code and surface area than a one-block substitution. Rendering the Mermaid
block outside the Markdown pipeline entirely was rejected because it would
break 012's "Markdown is canonical, HTML is derived from it" rule.

## Decision 5: Resolve each Mermaid node's click href with the existing generic relative-path helper, targeted at HTML output paths

Decision: Compute every `click` directive's href using
`doc_generator.links.relative_output_link()` (already used for `PageLink`
resolution since 012), pointed at each target's `outputPathHtml` instead of
its `outputPathMarkdown`, since the interactive diagram only exists inside
the rendered HTML page.

Rationale: Reusing the existing, already-tested relative-path helper keeps
click hrefs consistent with the rest of the link-resolution logic and
guarantees the same "does this target still exist" resolution rule already
enforced for `PageLink`s (dropping a click target instead of emitting a
directive for a symbol that no longer resolves).

Alternatives considered: A second, independent path-resolution
implementation just for Mermaid hrefs was rejected as duplicating already-
correct logic for no benefit.

## Decision 6: Give each Mermaid node a short synthetic id, scoped to one diagram

Decision: Assign each node in a diagram a simple synthetic id (`n0`, `n1`, …)
for use inside that one Mermaid block, instead of reusing the existing
stable page-id string (e.g. `module:repo::…::file::…`) as the Mermaid node
identifier.

Rationale: Mermaid node identifiers must be simple tokens; the existing
stable page ids contain characters (`:`, `/`) the Mermaid grammar does not
accept as bare identifiers. A synthetic id local to one diagram avoids
sanitizing/escaping the real id while keeping the diagram's own node-to-page
mapping (needed for the `click` directives) entirely local and easy to
regenerate deterministically on every render.

Alternatives considered: Hashing the real page id into a Mermaid-safe token
was considered and rejected as harder to read in the generated Markdown than
a plain incrementing id, with no benefit since the mapping never needs to be
stable across runs (it is recomputed fresh every time the diagram page is
generated).

## Decision 7: Load the Mermaid script and initialize it once, from the shared HTML layout, on every page

Decision: Add the `<script src="…assets/mermaid.min.js">` tag and a single
`mermaid.initialize({ startOnLoad: true })` call to `layout.html.jinja` (the
layout every generated page already shares), rather than conditionally
injecting it only on diagram pages.

Rationale: Mermaid's `startOnLoad` scan is a no-op (and cheap) on pages with
no `.mermaid` elements, so sharing one layout change is simpler and more
robust than threading a per-page "does this page need Mermaid" flag through
`html_render.py`, and it means any future page that wants to embed a diagram
gets the capability for free.

Alternatives considered: Conditionally including the script only on diagram
pages was rejected as an optimization that adds branching logic for
negligible benefit at this documentation's scale (a handful to a few dozen
pages).