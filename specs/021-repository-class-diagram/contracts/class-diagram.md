# Repository Class Diagram Contract

## Purpose

Define the new `doc_generator` functions that turn the already-available
symbol inventory and dependency-graph inheritance edges into the
repository-wide class diagram, the page it's embedded in, and how it
participates in incremental regeneration — the same role 013's
`mermaid-diagram-render.md` contract plays for the existing per-module
dependency diagram. As with that existing diagram, this is two functions in
two places (selection, then rendering), not one (Research Decision 5).

## Core functions

### `class_diagram.select_major_classes`

Inputs:
- `bundle` (`RepositoryBundle`)
- `graph` (`DependencyGraph`)

Output: `ClassDiagramSelection`

Expected behavior:
- Selects classes per Research Decision 2 (inheritance participants +
  top-by-edge-count, capped at 40), deterministic ordering.
- Populates `includedClasses` with each selected class's raw `id`, `name`,
  and its methods' raw names (from `ClassSymbol.methods` resolved against
  the owning file's `FunctionSymbol`s) — unsanitized; sanitization is the
  rendering function's job (Research Decision 4).
- Populates `inheritanceEdges` with only the pairs where both the child and
  parent class ids are present in `includedClasses`; drops (does not carry
  through) an inheritance edge to an excluded class.
- Mirrors `diagrams.py::build_module_diagram`'s shape and role exactly: a
  pure data-selection function with no Mermaid text in its output.
- Returns a `ClassDiagramSelection` with `includedClasses == ()` (not an
  error) for a repository with zero classes; the caller
  (`generateClassDiagramPage`) is responsible for not emitting a page in
  that case, per spec FR-004.

### `mermaid_diagram.build_class_diagram_mermaid_source`

Inputs:
- `selection` (`ClassDiagramSelection`)

Output: `ClassDiagramSource`

Expected behavior:
- Emits one `classDiagram` Mermaid node per `SelectedClass` with its
  methods listed, no attributes.
- Emits `ParentClass <|-- ChildClass`-direction inheritance edges (Mermaid's
  `<|--` hollow arrowhead points at the parent/base class, matching UML
  convention and this repo's own `docs/diagrams/class-diagram.md`, e.g.
  `Symbol <|-- ModuleSymbol`) for every entry in `selection.inheritanceEdges`.
  **Correction found during implementation**: an earlier draft of this
  contract had this direction backwards (`ChildClass <|-- ParentClass`);
  verified against a real Mermaid parser and against this repo's own
  existing diagram before implementing.
- Sanitizes every label (class name, method name) per Research Decision 4,
  reusing the same escaping approach as the existing
  `mermaid_diagram._escape_label` (extended to also replace `;`, or called
  alongside a new sibling sanitizer — implementation detail for
  `/speckit-tasks`).
- Added to the existing `doc_generator/mermaid_diagram.py` module (not a new
  file), mirroring how `build_mermaid_source` already lives there for the
  dependency diagram.
- Deterministic: the same `ClassDiagramSelection` always produces
  byte-identical `sourceText`.

## `DocGenerator` page method

### `generateClassDiagramPage() -> DocPage | None`

- Calls `class_diagram.select_major_classes` then, if non-empty,
  `mermaid_diagram.build_class_diagram_mermaid_source` — the same two-step
  call shape `generateDependencyDiagramPage` already uses for
  `build_module_diagram` → `build_mermaid_source`.
- Returns `None` when the selection's `includedClasses` is empty (no page
  written, no link emitted from the overview page). Otherwise builds and
  returns a `DocPage` of kind `"class-diagram"` at a fixed page id
  (`diagram:class-overview`) and fixed output path
  (`diagrams/class-overview.md`/`.html`), linked from the overview page.

## Incremental regeneration expectations

- `compute_regeneration_impact` (extended per Research Decision 3): adds
  `diagram:class-overview` to `impactedPageIds` whenever `direct_symbol_ids`
  or `changed_edges` is non-empty this run.
- A full, from-scratch run (`incremental=False`, or no previous manifest
  entries) regenerates the class-diagram page unconditionally, same as
  every existing page kind.

## Failure expectations

- A repository with zero classes: no class-diagram page is written; the
  overview page must not contain a broken/dead link to it (mirrors spec
  FR-004 and US1 acceptance scenario 4).
- A Mermaid label containing a literal `;` must never reach `sourceText`
  unsanitized (Research Decision 4) — this is asserted directly in tests
  against a fixture symbol/method name containing `;`, not just trusted to
  not occur in practice.
