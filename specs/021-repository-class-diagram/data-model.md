# Data Model: Repository Class Diagram

## Reused entities (unchanged)

- **`ClassSymbol` / `FunctionSymbol` / `ModuleSymbol`** (`repository_metadata`,
  feature 003): source of class names, methods, module ownership. No new
  fields — notably, `ClassSymbol` has no attribute/field data (Research
  Decision 1).
- **`DependencyNode` / `DependencyEdge`** (`dependency_graph`, feature 004):
  inheritance edges drive the class-diagram relationships shown; all edge
  types feed the major-class edge-count ranking.
- **`DependencyGraph`** (feature 004): queried read-only via its existing
  public `dependencies()`/`dependents()`; no new method added to this
  package (Structure Decision).
- **`DocPage` / `PageLink` / `PageManifestEntry`** (`doc_generator`, feature
  012): the new page kind reuses these unchanged, except `DocPage.kind`
  (`PageKind`) gains one new literal value.
- **`RegenerationImpactSet`** (`doc_generator`, feature 018): reused and
  extended in place (Research Decision 3) — same shape, broader coverage.

## PageKind extension

`doc_generator/models.py`'s `PageKind` grows from
`Literal["home", "module", "diagram"]` to
`Literal["home", "module", "diagram", "class-diagram"]`. Kept distinct from
the existing `"diagram"` kind (the per-module dependency diagram) so
incremental-impact logic and the manifest can tell them apart without
inspecting content.

## ClassDiagramSelection

Represents *which* classes and relationships make the cut — the selection
stage's output, built by `class_diagram.select_major_classes`. Plays the
same role for the class diagram that `DiagramExport` (004) plays for the
dependency diagram: a plain data shape with no Mermaid text in it (Research
Decision 5).

Fields:
- `includedClasses` — ordered tuple of `SelectedClass` (below), the classes
  chosen per Decision 2's heuristic and cap.
- `inheritanceEdges` — ordered tuple of `(childClassId, parentClassId)`
  pairs, both ids drawn from `includedClasses` only (an edge to an excluded
  class is dropped at this stage, not carried through as a dangling
  reference).
- `omittedClassCount` — total repository class count minus
  `len(includedClasses)`.

Relationships:
- Built from every `SourceFileBundle.classes` across the current
  `RepositoryBundle`, plus `DependencyGraph.dependencies()`/`.dependents()`
  for both the inheritance edges shown and the edge-count ranking.
- Not persisted — reconstructed fully on every generation run the
  class-diagram page regenerates, exactly like `DiagramExport` is for the
  dependency diagram.

Validation:
- `len(includedClasses) <= 40` (Decision 2's cap).
- Every `(childClassId, parentClassId)` pair in `inheritanceEdges` has both
  ids present in `includedClasses`.

### SelectedClass

One class chosen for inclusion.

Fields:
- `classId` — the `ClassSymbol.id`.
- `name` — the class's raw (unsanitized) name.
- `methods` — ordered tuple of `SelectedMethod` (below).

### SelectedMethod

One method shown on a `SelectedClass`.

Fields:
- `name` — the method's raw (unsanitized) name.

Sanitization (Decision 4, `;` → `,`) is a rendering-stage concern, applied
when a name is written into `ClassDiagramSource.sourceText`, not stored on
the selection itself — matching how `DiagramExport` node names are also
unsanitized until `build_mermaid_source` renders them.

## ClassDiagramSource

Represents the single repository-wide class diagram's rendered Mermaid
text — the rendering stage's output, built by
`mermaid_diagram.build_class_diagram_mermaid_source(selection)`. Plays the
same role for the class diagram that `MermaidDiagramSource` (013) plays for
the dependency diagram.

Fields:
- `sourceText` — full `classDiagram` Mermaid text: one `class` block per
  `SelectedClass` (name + sanitized method names, no attributes — Decision
  1) and one `<|--` line per entry in `inheritanceEdges`.
- `includedClassIds` — carried through from `ClassDiagramSelection`, in the
  same order used to build `sourceText`.
- `omittedClassCount` — carried through from `ClassDiagramSelection`,
  surfaced in the page so a reader knows the diagram is intentionally
  partial rather than assuming completeness.

Relationships:
- Built from exactly one `ClassDiagramSelection`; does not itself query
  `RepositoryBundle` or `DependencyGraph`.
- Not persisted separately — reconstructed fully on every generation run
  the class-diagram page regenerates, exactly like the existing per-module
  `MermaidDiagramSource`.

Validation:
- Every label in `sourceText` is free of an unescaped `;` (Decision 4).
- `includedClassIds` has exactly one entry per `SelectedClass` in the
  source `ClassDiagramSelection`, same order.

## RegenerationImpactSet extension

No new fields on the existing dataclass. `impactedPageIds` and
`removedPageIds` are populated with the new page kind's id following
Research Decision 3's rules; `changedSymbolIds`/`changedDependencyEdgeIds`
inputs are unchanged — the new logic only reads them, matching how diagram
pages are already handled today.
