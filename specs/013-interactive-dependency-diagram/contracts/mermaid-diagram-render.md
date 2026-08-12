# Interactive Dependency Diagram Contract

## Purpose

Define how a module's `DiagramExport` becomes an interactive, click-navigable
Mermaid diagram embedded in its existing `doc_generator` diagram page, and
what the documentation writer guarantees about the local Mermaid asset the
diagram depends on.

## Core function

### `build_mermaid_source`

Inputs:

- `diagram` (`DiagramExport`)
- `diagram_page_id` (the owning diagram page's stable id)
- `diagram_output_path_html` (the owning diagram page's HTML output path)
- a page-resolution callback equivalent to `DocGenerator`'s existing
  `_resolve_module_key_by_path`, used to map each node to its module page's
  id/name/output paths

Output: `MermaidDiagramSource`

Expected behavior:

- Emits one Mermaid `flowchart` declaration containing one node per
  `DiagramExport` node (including the focused/root node) and one directed
  edge per `DiagramExport` edge, direction preserved exactly as stored
  (`sourceId -> targetId`).
- Assigns every node a synthetic, diagram-local id and never reuses a real
  page id as a Mermaid identifier.
- Emits a `click` directive for every node that resolves to a current
  documentation page, using an HTML-relative href to that page.
- Emits no `click` directive for a node that does not resolve to a current
  page; the node still renders (unclickable) rather than being dropped from
  the diagram entirely.
- Produces deterministic output for a given `DiagramExport` and current
  documentation set (stable node ordering), so repeated generation without
  underlying changes yields byte-identical Mermaid source.

## Markdown/HTML embedding expectations

- The diagram page's `contentMarkdown` embeds `MermaidDiagramSource.sourceText`
  inside a ` ```mermaid ` fenced code block, in addition to (not replacing)
  the existing "Related modules" links and "Edges" table already produced by
  012.
- The HTML rendering step converts that fenced block into a
  `<pre class="mermaid">…</pre>` element (Mermaid's default auto-discovery
  target), without altering how any other fenced code block is rendered.
- The shared HTML layout loads the vendored Mermaid script via a page-relative,
  classic (non-module) `<script src="…assets/mermaid.min.js">` tag and calls
  `mermaid.initialize({ startOnLoad: true })` once per page.

## Local asset expectations

- The documentation writer ensures `outputRoot/assets/mermaid.min.js` exists
  before/alongside writing any page that could reference it, copying it from
  the vendored copy shipped inside the `doc_generator` package.
- The writer never fetches the asset from a network location; it is copied
  from a local file shipped with the tool.
- Copying the asset obeys the same `outputRoot` containment guard as every
  other file the writer creates, and the writer does not rewrite the asset
  file on every run once it is already present with matching content.

## Failure expectations

- If the vendored Mermaid asset is missing from the `doc_generator` package
  itself (a packaging error), diagram generation must fail with a clear,
  local error rather than silently omitting the script tag or falling back
  to a CDN reference.
- If a `DiagramExport` cannot resolve any of its nodes to current
  documentation pages (e.g., an entirely orphaned module), the Mermaid
  diagram must still render with plain, unclickable nodes rather than
  failing generation of the page.