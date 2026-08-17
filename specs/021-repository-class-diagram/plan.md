# Implementation Plan: Repository Class Diagram

**Branch**: `021-repository-class-diagram` | **Date**: 2026-08-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/021-repository-class-diagram/spec.md`

## Summary

Add one new Mermaid diagram to the generated wiki, extending the existing
`doc_generator` package the same way 013 added the interactive per-module
dependency diagram: a single, repository-wide **class diagram** (curated to
structurally major classes), linked from the wiki's overview page.

This reuses data the pipeline already has — `ClassSymbol` (`id`, `name`,
`parentClass`, `methods`; no attributes) from the symbol inventory (003) and
the already-typed `"inheritance"` edges in the in-memory `DependencyGraph`
(004) — with no new source-level analysis. Structurally, it's a new module
built on the same two-stage model as the existing `diagrams.py` /
`mermaid_diagram.py` pair: a selection step (which classes make the cut) and
a separate rendering step (selection → Mermaid text), rather than one module
doing both. It renders as Mermaid `classDiagram`, embedded exactly like the
existing dependency diagram: a fenced ` ```mermaid ` block, rewritten to
`<pre class="mermaid">` by the unmodified `html_render.py`, rendered by the
same already-vendored, offline `mermaid.min.js` used for the dependency
diagrams — no new asset, no new dependency.

One material data gap surfaced during research: the symbol inventory has no
concept of a class *attribute* (`ClassSymbol` carries only `methods`, not
fields), so the class diagram can show class names, methods, and
inheritance, but **not** attributes or composition/aggregation edges. The
spec (FR-003) treats this as an accepted limitation, not a gap to close as
part of this feature; see Research Decision 1.

(Note: this feature was split out of a broader "wiki diagram types" spec
that originally also covered sequence and use-case diagrams. Those two
capabilities will be planned separately, each reusing the pattern
established here the same way this feature reuses 013's.)

## Technical Context

**Language/Version**: Python 3.11+, extending the existing `doc_generator`
package; no new client-side asset (reuses the vendored Mermaid classic UMD
bundle from `src/doc_generator/assets/mermaid.min.js`, added in 013)

**Primary Dependencies**: Existing `doc_generator`, `dependency_graph`, and
`repository_metadata` packages (reused, no new Python dependency)

**Storage**: No new persistence. Reuses 012's `DocPageManifestStore` for the
new page kind; the major-class ranking is recomputed from the already-loaded,
in-memory `DependencyGraph` on every generation run rather than being
separately stored

**Testing**: pytest, asserting generated Markdown/HTML contains the expected
`classDiagram` fenced block, correct class/method/inheritance-edge counts on
fixture repositories with known symbol inventories, and correct incremental
add/update/remove behavior for the new page kind — no headless-browser
rendering test, consistent with 013

**Target Platform**: Any standard web browser with JavaScript enabled,
opening the generated documentation from local files or a static host;
generation runs on Windows/macOS/Linux like the rest of the toolchain

**Project Type**: Extension of the existing internal documentation-generation
library (`doc_generator`, feature 012); no new package

**Performance Goals**: The class diagram is built with a single linear pass
over the repository's classes plus an O(n log n) ranking step over at most
that same class count; for a repository with on the order of a few thousand
classes (well beyond the 40-class inclusion cap this diagram renders), this
selection step is expected to complete in well under a second, so it adds
no perceptible overhead to a documentation regeneration run of any size

**Constraints**: Zero network requests at view time (unchanged — same
vendored Mermaid asset as 013); Mermaid class-diagram label text must never
contain a literal, unescaped `;` (see Research Decision 4 — a real Mermaid
parser gotcha hit and fixed elsewhere in this repository's own
hand-authored diagrams); read-only analysis only, no new writes outside the
existing `outputRoot`

**Scale/Scope**: Exactly one class-diagram page per repository (not per
module), capped at a fixed maximum number of included classes (Research
Decision 2)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Confidentialite absolue**: pass — every input (symbol inventory,
  dependency graph) is already local; no new network call is introduced.
- **Zero exposition reseau par defaut**: pass — no new server surface; the
  new page is a static file served the same way existing pages are.
- **Jamais de repli silencieux vers le cloud**: pass — not applicable, no
  inference is involved in building this diagram.
- **Traçabilite des reponses IA**: pass — not applicable, this diagram
  renders structural data only (already-extracted symbols and graph edges),
  not AI-generated text.
- **Re-indexation incrementale**: pass — no full reindex is introduced.
  Major-class ranking is recomputed from the already-in-memory
  `DependencyGraph` on each run (a cheap structural scan, not a source
  re-parse), and impacted-page tracking is extended, not replaced, so the
  class diagram regenerates only when relevant (Research Decision 3).
- **Infrastructure minimale et stockage local**: pass — no new storage, no
  new service; reuses the existing manifest store and static file writer.
- **Depot analyse en lecture seule**: pass — unaffected; still only writes
  inside the existing documentation `outputRoot`.

## Project Structure

### Documentation (this feature)

```text
specs/021-repository-class-diagram/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── class-diagram.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── doc_generator/
│   ├── class_diagram.py      (new: major-class selection only, mirroring
│   │                          diagrams.py's build_module_diagram — produces
│   │                          a plain ClassDiagramSelection, no Mermaid text)
│   ├── mermaid_diagram.py    (modified: add build_class_diagram_mermaid_source,
│   │                          mirroring the existing build_mermaid_source —
│   │                          renders a ClassDiagramSelection to Mermaid
│   │                          classDiagram text as ClassDiagramSource)
│   ├── generator.py          (modified: generateClassDiagramPage; wire it
│   │                          into generateRepositoryDocumentation and link
│   │                          it from generateOverviewPage)
│   ├── impact.py              (modified: extend RegenerationImpactSet
│   │                          coverage to the new repo-wide page)
│   ├── links.py               (modified: page id/output path for the new
│   │                          page kind)
│   ├── models.py              (modified: extend `PageKind` with
│   │                          "class-diagram")
│   └── templates/
│       ├── class_diagram.md.jinja     (new)
│       └── home.md.jinja              (modified: link to the new repo-wide
│                                        page)
├── dependency_graph/    (reused, unmodified: DependencyGraph.dependencies(),
│                        .dependents())
└── repository_metadata/ (reused, unmodified: ClassSymbol, FunctionSymbol)
```

**Structure Decision**: Same as 013 — keep this feature entirely inside the
existing `doc_generator` package. It is one more page-generation concern
added to the package that already owns page modeling, templating, link
resolution, incremental-impact tracking, and file writing end-to-end (012's
Structure Decision). No new package, no change to `dependency_graph` or
`repository_metadata`.

Within the package, mirror the existing two-stage split between selection
and rendering that `diagrams.py`/`mermaid_diagram.py` already establish for
the dependency diagram (`build_module_diagram` → `DiagramExport`, then
`build_mermaid_source` → `MermaidDiagramSource`), rather than one module
doing both: `class_diagram.py` selects/ranks classes into a plain
`ClassDiagramSelection`; `mermaid_diagram.py` gains a sibling function that
renders that selection into Mermaid text as `ClassDiagramSource`. This keeps
"what classes are major" and "how a selection becomes Mermaid text"
independently testable, exactly like the existing pair already is (Research
Decision 5).

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

No constitution violations. One spec-level gap is carried forward instead of
silently worked around:

| Gap | Why it exists | Why not closed here |
|-----|----------------|----------------------|
| Class diagram omits attributes and composition/aggregation edges (spec FR-003) | `ClassSymbol` (repository_metadata/parser_engine) has no attribute/field data — only `id`, `name`, `parentClass`, `methods`, `nestedSymbols` | Adding attribute extraction means extending the AST symbol extractor (002/003) across every supported language, which the spec's Assumptions explicitly place out of scope for this feature ("does not introduce new source-level static analysis beyond what those already capture") |

This should be flagged back to the spec owner: either accept the class
diagram as name+methods+inheritance only (this plan's approach, and what the
spec's FR-003 explicitly directs), or open a follow-up feature to add
attribute extraction first.

## Constitution Check After Design

Re-checked against `research.md` and `data-model.md`: no new violations.
Every new read (symbol inventory, dependency-graph edges) is already-local
data; the one new analysis step (major-class ranking) is a bounded,
in-memory graph scan, not new source parsing or a network call; incremental
regeneration is extended, not bypassed (Research Decision 3); no new storage
or service is introduced.
