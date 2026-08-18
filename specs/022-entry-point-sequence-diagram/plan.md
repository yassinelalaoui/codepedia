# Implementation Plan: Entry Point Sequence Diagrams

**Branch**: `022-entry-point-sequence-diagram` | **Date**: 2026-08-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/022-entry-point-sequence-diagram/spec.md`

## Summary

Add one new Mermaid diagram *per identified entry point* (a CLI command, an
API route handler, or any public function/method nothing else in the
repository calls) to the generated wiki, extending `doc_generator` the same
way `013` added the per-module dependency diagram and `021` added the
repository-wide class diagram — but keyed per-entry-point rather than
per-module or repository-wide.

This reuses data the pipeline already has: the existing
`DependencyGraph.functions_calling`/`.functions_called_by` helpers (no
`dependency_graph` code changes) for both entry-point qualification and
bounded traversal, and each call edge's already-captured
`metadata["lineStart"]` to reconstruct real call order (the raw helper
result order is not call order — see Research Decision 4). One real, scoped
data gap was closed rather than routed around: CLI-command/API-route
detection needs each function's decorators, which the existing Python
extraction path (`parser_engine/extractor.py`, which already parses via
Python's own `ast` module) already has available on every `ast.FunctionDef`
node but currently discards — this feature captures and unparses it into a
new `FunctionSymbol.decorators` field (Python-only; Research Decision 3).

Structurally, this is a new module (`entry_point_diagram.py`) following the
same two-stage split `class_diagram.py`/`mermaid_diagram.py` already
establish for the class diagram: a selection step (which functions qualify,
what their bounded call sequence is) and a separate rendering step
(selection → Mermaid `sequenceDiagram` text). It renders through the same
already-vendored, offline `mermaid.min.js` every other diagram in this
project uses — no new asset, no new dependency. Output paths reuse the
existing generic `diagrams/{slug}.md`/`.html` convention unmodified; each
entry point gets its own dedicated page this way (satisfying spec FR-009
literally), discoverable via a link from that entry point's existing
per-function section on its owning module's page — the same
page-plus-discoverability-link pattern the existing per-module dependency
diagram already uses (Research Decision 7).

One material gap is carried forward, not closed: CLI/API-route detection via
decorators only works for the Python extraction path; the brace-language
path (JS/TS/Java/Go/Rust) has no decorator/annotation capture. Functions in
those languages can still become entry points via the "never called"
branch, just never via the CLI-command/API-route branches. See Complexity
Tracking.

## Technical Context

**Language/Version**: Python 3.11+, extending the existing `doc_generator`
package plus a small, scoped addition to `parser_engine`'s Python extraction
path and `repository_metadata`'s symbol conversion; no new client-side asset
(reuses the vendored Mermaid classic UMD bundle from
`src/doc_generator/assets/mermaid.min.js`, added in 013)

**Primary Dependencies**: Existing `doc_generator`, `dependency_graph`,
`repository_metadata`, and `parser_engine` packages (reused/lightly
extended, no new Python dependency)

**Storage**: No new persistence. `FunctionSymbol.decorators` is threaded
into the already-generic, already-persisted `metadata` JSON column (no
schema migration). Sequence-diagram pages reuse 012's
`DocPageManifestStore` for the new page kind; each entry point's bounded
call sequence is recomputed from the already-loaded, in-memory
`RepositoryBundle` + `DependencyGraph` on every generation run rather than
being separately stored (mirrors 021 Research Decision 3's precedent for
major-class ranking).

**Testing**: pytest, asserting: generated Markdown/HTML contains the
expected `sequenceDiagram` fenced block with the correct participants and
message order on fixture repositories with known call chains spanning
multiple modules (spec SC-001); a leaf entry point (no outgoing calls)
renders a minimal, single-participant diagram (SC-004); a recursive/cyclic
fixture terminates at the fixed depth cap (SC-003); correct incremental
add/update/remove behavior for the new page kind — no headless-browser
rendering test, consistent with 013/021.

**Target Platform**: Any standard web browser with JavaScript enabled,
opening the generated documentation from local files or a static host;
generation runs on Windows/macOS/Linux like the rest of the toolchain

**Project Type**: Extension of the existing internal documentation-generation
library (`doc_generator`, feature 012), with a small, scoped extension of
`parser_engine`'s Python extraction path and `repository_metadata`'s symbol
conversion; no new top-level package

**Performance Goals**: Entry-point identification is a single linear pass
over the repository's functions/methods plus, per candidate, one
`functions_calling` lookup (O(1) amortized against the graph's edge index);
each qualifying entry point's traversal is bounded to at most
`MAX_CALL_DEPTH` (6) hops, so total work across all entry points is linear
in (entry point count × a small constant), not proportional to overall
repository size — expected to add no perceptible overhead to a
documentation regeneration run of any size, consistent with 021's
performance profile for its own bounded selection step.

**Constraints**: Zero network requests at view time (unchanged — same
vendored Mermaid asset as 013/021); Mermaid label text must never contain a
literal, unescaped `;` or `"` (same sanitization standard 021 held itself
to); read-only analysis only, no new writes outside the existing
`outputRoot`; no changes to `dependency_graph`'s public shape
(`DependencyNode`/`DependencyEdge`) — traversal and attribution work
entirely through its existing, unmodified helpers plus data `doc_generator`
already has loaded (Research Decisions 2, 4, 5).

**Scale/Scope**: One sequence-diagram page per identified entry point (not
per module, not repository-wide) — count varies with the repository; each
individual diagram is capped at `MAX_CALL_DEPTH` (6) hops from its entry
point, not by a total-entry-point-count cap (unlike 021's 40-class cap,
there is no shared page these diagrams compete for space on, so no
analogous inclusion cap is needed).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Confidentialite absolue**: pass — every input (symbol inventory,
  dependency-graph call edges) is already local; no new network call is
  introduced.
- **Zero exposition reseau par defaut**: pass — no new server surface; the
  new pages are static files served the same way existing pages are.
- **Jamais de repli silencieux vers le cloud**: pass — not applicable, no
  inference is involved in building these diagrams.
- **Traçabilite des reponses IA**: pass — not applicable, these diagrams
  render structural data only (already-extracted symbols and call edges),
  not AI-generated text.
- **Re-indexation incrementale**: pass — no full reindex is introduced.
  Entry-point identification and traversal are recomputed from the
  already-in-memory bundle/graph on each run (a cheap structural scan, not
  a source re-parse); impacted-page tracking is extended, not replaced,
  so sequence-diagram pages regenerate only when relevant (Research
  Decision 8).
- **Infrastructure minimale et stockage local**: pass — no new storage, no
  new service; reuses the existing manifest store, the existing generic
  `metadata` JSON column, and the existing static file writer.
- **Depot analyse en lecture seule**: pass — unaffected; still only writes
  inside the existing documentation `outputRoot`.

## Project Structure

### Documentation (this feature)

```text
specs/022-entry-point-sequence-diagram/
├── plan.md               # This file (/speckit-plan command output)
├── research.md           # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── sequence-diagram.md
└── tasks.md               # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── parser_engine/
│   ├── symbols.py             (modified: add `decorators: tuple[str, ...] = ()`
│   │                            to FunctionSymbol)
│   └── extractor.py           (modified: build_function's Python path unparses
│                                node.decorator_list into FunctionSymbol.decorators;
│                                brace-language path unchanged, decorators stay ())
├── repository_metadata/
│   └── sqlite_store.py        (modified: _convert_function_symbol adds
│                                "decorators" to the metadata dict it already
│                                builds — no schema change)
├── doc_generator/
│   ├── entry_point_diagram.py  (new: identify_entry_points + 
│   │                            build_entry_point_call_sequence — selection
│   │                            only, mirroring class_diagram.py's role;
│   │                            produces EntryPoint/CallStep/
│   │                            SequenceDiagramSelection, no Mermaid text)
│   ├── mermaid_diagram.py      (modified: add
│   │                            build_sequence_diagram_mermaid_source,
│   │                            mirroring build_class_diagram_mermaid_source —
│   │                            renders a SequenceDiagramSelection to Mermaid
│   │                            sequenceDiagram text as SequenceDiagramSource)
│   ├── generator.py            (modified: generateEntryPointSequenceDiagramPages;
│   │                            wire into generateRepositoryDocumentation; add
│   │                            an optional per-function sequence-diagram link
│   │                            in generateModulePage)
│   ├── impact.py                (modified: extend RegenerationImpactSet
│   │                            coverage to entry-point pages, including
│   │                            propagation from a changed call-chain step)
│   ├── links.py                 (modified: sequence_diagram_page_id(key);
│   │                            reuses existing diagram_output_paths/page_slug
│   │                            unmodified)
│   ├── models.py                (modified: extend PageKind with
│   │                            "sequence-diagram")
│   └── templates/
│       ├── sequence_diagram.md.jinja  (new)
│       └── module.md.jinja            (modified: optional per-function
│                                        "[View call sequence]" link)
├── dependency_graph/    (reused, unmodified: .functions_calling(),
│                        .functions_called_by(), .edges)
└── repository_metadata/ (reused: RepositoryBundle, ClassSymbol.methods,
                          FunctionSymbol.owner/nestedSymbols)
```

**Structure Decision**: Same as 013/021 — keep this feature almost entirely
inside the existing `doc_generator` package (one more page-generation
concern added to the package that already owns page modeling, templating,
link resolution, incremental-impact tracking, and file writing end-to-end,
per 012's Structure Decision). The one deliberate exception is the small,
scoped decorator-capture addition to `parser_engine`'s Python extraction
path and `repository_metadata`'s symbol conversion (Research Decision 3) —
necessary because CLI-command/API-route classification is genuinely a
symbol-extraction concern, not a documentation-rendering one, and belongs in
the same layer `owner`/`returnType` already live in. No change to
`dependency_graph`.

Within `doc_generator`, mirror the existing two-stage split between
selection and rendering that `class_diagram.py`/`mermaid_diagram.py`
already establish: `entry_point_diagram.py` identifies entry points and
builds each one's bounded call sequence into a plain
`SequenceDiagramSelection`; `mermaid_diagram.py` gains a sibling function
that renders that selection into Mermaid text as `SequenceDiagramSource`.
Same reasoning as 021 Research Decision 5: keeps "which functions are entry
points, in what call order" and "how a selection becomes Mermaid text"
independently testable.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

No constitution violations. One spec-scoped gap is carried forward instead
of silently worked around:

| Gap | Why it exists | Why not closed here |
|-----|----------------|----------------------|
| CLI-command/API-route detection (spec FR-001/FR-002) only works for Python; JS/TS/Java/Go/Rust functions can only become entry points via the "never called" branch | Only the Python extraction path parses via a full AST (`ast` module) with `decorator_list` already available; the brace-language path (`_extract_brace_inventory`) is a line-pattern scanner with no equivalent decorator/annotation concept | Adding decorator/annotation capture to five more languages' brace-pattern extraction is a much larger, per-language static-analysis effort; the spec's own Assumptions already scope framework-pattern detection as "this project's own CLI/route registration patterns" (Python: Typer, FastAPI) — this plan satisfies that scope exactly, not a general multi-language one |

This should be flagged back to the spec owner: either accept
CLI/route-branch entry points as Python-only for now (this plan's approach),
or open a follow-up feature to extend decorator/annotation capture to the
brace-language extraction path first.

## Constitution Check After Design

Re-checked against `research.md` and `data-model.md`: no new violations.
Every new read (symbol decorators, call-edge `lineStart` metadata, class
method membership) is already-local data already produced by the existing
pipeline; the one new extraction step (decorator unparsing) reuses an
already-exercised helper (`_python_unparse`) on data the Python AST already
exposes, not new source parsing beyond what's already walked; incremental
regeneration is extended, not bypassed (Research Decision 8); no new
storage or service is introduced; `dependency_graph`'s public shape is
untouched (Research Decisions 2, 4, 5).
