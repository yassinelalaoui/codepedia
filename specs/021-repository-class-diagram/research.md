# Phase 0 Research: Repository Class Diagram

## Decision 1 — Class diagram omits attributes and composition edges

**Decision**: Render the repository-wide class diagram with class name and
methods, and inheritance edges only. Do not attempt attributes or
composition/aggregation edges.

**Rationale**: `ClassSymbol` (both the `parser_engine.symbols` and
`repository_metadata.models` versions) has fields `id`, `name`, `lineStart`,
`lineEnd`, `docstring`, `generatedSummary`, `parentClass`, `methods`,
`nestedSymbols` — no attribute/field list anywhere. There is consequently no
data to detect "one class's attribute typed as another known class" for
composition/aggregation either. The spec's FR-003 already directs this
explicitly as an accepted limitation, not a gap for this feature to close.

**Alternatives considered**:
- *Extend the AST symbol extractor to capture class fields* — rejected: this
  touches 002/003 across every supported language grammar, which the spec's
  Assumptions explicitly rule out ("does not introduce new source-level
  static analysis beyond what those already capture").
- *Approximate attributes from constructor parameters* (e.g., Python
  `__init__` parameters) — rejected: `FunctionSymbol.parameters` exists, but
  treating a constructor's parameters as the class's fields is unreliable
  (not every parameter becomes a stored field, and languages differ widely
  in constructor conventions) and would silently fabricate structure that
  isn't verified against the actual source, which cuts against this
  project's traceability principle (constitution 2.4, applied by analogy).

## Decision 2 — Major-class selection heuristic and cap

**Decision**: A class is included in the repository-wide class diagram if
either:
1. it participates in at least one inheritance edge (parent or child), or
2. it ranks among the top classes by total dependency-graph edge count
   (`len(graph.dependencies(class_id)) + len(graph.dependents(class_id))`,
   across all edge types),

capped at a fixed maximum of **40** included classes total. If inheritance
participants alone exceed 40, take the 40 with the highest edge count among
them (deterministic tie-break: edge count descending, then class name
ascending, then id ascending).

**Rationale**: Matches the spec's FR-005 priority order exactly
(inheritance participants first, then edge-count ranking) and mirrors this
very repository's own hand-curated `docs/diagrams/class-diagram.md`, which
keeps "only the classes and relationships that matter." Inheritance
participants are guaranteed inclusion because an inheritance edge with only
one side shown is a broken/misleading diagram. Edge count is a reasonable,
already-available proxy for "structurally central" that needs no new
analysis — it's exactly the same `dependencies()`/`dependents()` machinery
`DocGenerator._related_modules` already uses.

**Alternatives considered**:
- *Fixed percentage of total class count* — rejected: unpredictable on very
  small or very large repositories (a 3-class repo would show ~1 class; a
  2,000-class repo would still show hundreds).
- *No cap, always inheritance participants only* — rejected: a repository
  with no inheritance at all would render an empty class diagram even though
  it may have plenty of standalone, structurally significant classes;
  doesn't fulfill "major classes" for that common case.

## Decision 3 — Extending incremental impact tracking to the new page kind

**Decision**: Extend `compute_regeneration_impact` (doc_generator/impact.py)
rather than adding a parallel impact-computation path: the class diagram
page (`diagram:class-overview`) is added to `impactedPageIds` whenever this
run has *any* `direct_symbol_ids` or `changed_dependency_edge_ids` at all —
it's a repository-wide view whose content (which classes rank as "major")
can change from a single edit anywhere in the repository, so it cannot be
scoped more narrowly the way a per-module page can.

**Rationale**: Reuses the existing, already-tested impact-propagation
machinery (`_add_referrers_of`, `removed_page_ids` handling in
`DocumentationWriter.remove_page`) instead of inventing a second
regeneration path. This broader trigger condition is deliberately simpler
than the per-page precision the rest of the system has for module/diagram
pages, but it's the *safer* choice given spec SC-003 explicitly requires the
diagram to update after any qualifying change — the existing home page's
narrower `requiresHomePageRegeneration` trigger (only on module set changes)
is a known, accepted staleness window for its own repository-wide
`architecture_summary`, and this feature deliberately doesn't inherit that
same staleness for the class diagram.

Recomputing the full major-class ranking on every incremental run is a
bounded, in-memory graph scan (not a source re-parse, LLM call, or
re-embedding), so it does not conflict with the "never re-analyze the whole
repository" incremental principle (2.5) the same way 004's existing
`_related_modules`-style per-page graph queries don't.

**Alternatives considered**: a wholly separate impact-tracking module for
the new page kind — rejected as needless duplication of logic
`compute_regeneration_impact` already owns end-to-end.

## Decision 4 — Mermaid label text must not contain a bare `;`

**Decision**: Every string interpolated into a Mermaid `classDiagram` label
(class name, method name) is sanitized by replacing `;` with `,` (same
spirit as the existing `mermaid_diagram._escape_label`, which already
replaces `"` with `'`).

**Rationale**: Directly learned from this repository's own hand-authored
diagrams: `docs/diagrams/sequence-diagrams/01-full-indexing.md` and
`03-chat-rag.md` both failed to parse in Mermaid because a bare `;` inside
unquoted text is a statement separator in Mermaid's grammar, silently
truncating content and desyncing the rest of the parse (verified directly
against `mermaid@11`'s parser). Class and method names are free text and
could in principle contain a `;` in some languages/naming conventions, so
the generator must guard against it rather than relying on source text
never containing one.

## Decision 5 — Mirror the existing selection/rendering module split

**Decision**: Implement this feature as two separate functions in two
separate places, not one combined module:
- `class_diagram.select_major_classes(bundle, graph) -> ClassDiagramSelection`
  (new file `doc_generator/class_diagram.py`) — pure selection/ranking, no
  Mermaid text.
- `mermaid_diagram.build_class_diagram_mermaid_source(selection) -> ClassDiagramSource`
  (new function added to the existing `doc_generator/mermaid_diagram.py`) —
  pure rendering, no graph queries.

**Rationale**: This is exactly how the existing dependency diagram is
already split: `diagrams.py::build_module_diagram` selects/queries the graph
and returns a plain data shape (`DiagramExport`), and
`mermaid_diagram.py::build_mermaid_source` separately turns that data shape
into Mermaid text (`MermaidDiagramSource`) — `generateDependencyDiagramPage`
calls them as two explicit steps. Mirroring that split (rather than one
module doing both, as an earlier draft of this plan had) keeps "which
classes are major" and "how a selection renders as Mermaid" independently
testable, matches the codebase's existing convention exactly, and lets
`build_class_diagram_mermaid_source` live next to `build_mermaid_source`
where the shared label-sanitization helper (Decision 4, mirroring
`_escape_label`) can be reused directly instead of duplicated.

**Alternatives considered**: one combined `class_diagram.py` module doing
both selection and rendering — rejected because it doesn't match the
established pattern this feature was explicitly asked to follow, and
bundles two independently-testable concerns into one.
