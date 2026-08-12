# Data Model: Interactive Dependency Diagram

This feature adds one new entity and reuses several existing ones unchanged.

## Reused entities

- **`DiagramExport`** (`dependency_graph`, feature 004): the node/edge data
  for one module's direct-dependency neighborhood, produced by
  `DependencyGraph.exportDiagram()`. This feature only reads it; it does not
  change its shape.
- **`DependencyNode` / `DependencyEdge`** (`dependency_graph`, feature 004):
  the individual nodes and directed edges inside a `DiagramExport`.
- **`DocPage`** (`doc_generator`, feature 012), `kind="diagram"`: the
  existing diagram page. This feature extends its `contentMarkdown` to
  include a Mermaid fenced block; its identity, output paths, and links are
  unchanged.
- **`PageLink`** (`doc_generator`, feature 012): the existing module/diagram
  page links. This feature's Mermaid `click` hrefs are resolved through the
  same relative-path helper `PageLink` uses, targeted at HTML output paths
  instead of Markdown ones.

## MermaidDiagramSource

Represents the rendered Mermaid flowchart text embedded in one diagram
page's `contentMarkdown`, plus the bookkeeping needed to emit correct
`click` navigation directives.

Fields:
- `diagramPageId` — the owning diagram `DocPage.id`.
- `sourceText` — the full Mermaid flowchart text (node declarations, edges,
  and `click` directives) embedded verbatim inside the page's
  ` ```mermaid ` fenced block.
- `nodeIdMap` — mapping from each `DiagramExport` node's real id (a
  `DependencyNode.id`) to the short synthetic id used for that node inside
  this one Mermaid block (e.g. `n0`, `n1`, …).
- `clickTargets` — for each node that resolves to an existing documentation
  page, the synthetic node id, the target `DocPage.id`, and the HTML-relative
  href used in that node's `click` directive.

Relationships:
- Built from one `DiagramExport` plus the same page-existence/link-resolution
  rules `doc_generator.links` already applies to `PageLink`s.
- Embedded into the owning diagram `DocPage.contentMarkdown`; not persisted
  separately (no new manifest table — it is fully reconstructed from the
  `DiagramExport` and the current documentation set on every render, exactly
  like the rest of a diagram page's content).

Validation:
- `nodeIdMap` must assign exactly one synthetic id per distinct node in the
  source `DiagramExport`, scoped to this one diagram (ids are not required to
  be stable across regenerations).
- `clickTargets` must never reference a synthetic id that is not present in
  `nodeIdMap`.
- A node whose real id does not resolve to a current documentation page must
  be present in `nodeIdMap` (so it still renders) but absent from
  `clickTargets` (so it emits no `click` directive), matching the existing
  "drop unresolved links" rule from 012.

## VendoredMermaidAsset

Represents the local, offline copy of the Mermaid browser library shipped
with the tool and copied into every generated documentation output.

Fields:
- `sourcePath` — the vendored file's path inside the `doc_generator` package
  (`src/doc_generator/assets/mermaid.min.js`).
- `outputPath` — its copied location inside a generated documentation set
  (`outputRoot/assets/mermaid.min.js`).

Relationships:
- Copied once per `outputRoot` by the documentation writer; referenced by a
  relative `<script>` tag from the shared HTML layout every generated page
  uses.

Validation:
- `outputPath` must always resolve inside the configured `outputRoot`,
  subject to the same containment guard as every other generated file.
- The asset is treated as a writer-managed file like any generated page: it
  is created if missing and left untouched (not re-copied/rewritten) once
  present with matching content, so it participates correctly in the
  "writer only touches its own managed files" guarantee from 012.