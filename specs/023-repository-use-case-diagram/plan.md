# Implementation Plan: Repository Use Case Diagram

**Branch**: `023-repository-use-case-diagram` | **Date**: 2026-08-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/023-repository-use-case-diagram/spec.md`

## Summary

Add one new, single, repository-wide use-case diagram page to the generated
wiki, extending `doc_generator` the same way `013` added the per-module
dependency diagram, `021` added the repository-wide class diagram, and `022`
added per-entry-point sequence diagrams — but this feature adds no new
entry-point detection of its own. It consumes `022`'s already-built
`entry_point_diagram.identify_entry_points()` unmodified (same
CLI-command/API-route/uncalled-public-function identification, "8.2" in the
brief) and renders it from a different angle: instead of "what does this
entry point call" (022's per-entry-point sequence diagrams), this shows "who
can reach the system, and through what" — one shared actor per exposure kind
(CLI, API, or a generic fallback for everything else), each linked to every
entry point of that kind, shown as its own use case.

Mermaid has no native UML use-case-diagram grammar. This project already
solved that for its own hand-authored documentation
(`docs/diagrams/use-case-diagram.md`): a `flowchart` where actor nodes and
oval-shaped use-case nodes (inside a system-boundary `subgraph`) stand in for
UML actors/use-cases, linked by plain arrows. This feature reuses that exact
workaround for the *generated* diagram, giving the generated wiki a
use-case diagram that looks and reads like the one already maintained for
this project itself.

Structurally, this follows the same two-stage split established by
`class_diagram.py`/`mermaid_diagram.py` (021) and
`entry_point_diagram.py`/`mermaid_diagram.py` (022): a new, small selection
module (`use_case_diagram.py`) turns the entry points 022 already identifies
into a plain `UseCaseDiagramSelection` (actors + use cases, no Mermaid
syntax), and a new rendering function in the existing `mermaid_diagram.py`
turns that selection into the flowchart-workaround Mermaid text. The
resulting single page is wired into the wiki the same way `021`'s class
diagram is: computed once per run, written only if it has at least one use
case, and linked from the wiki's overview/home page — never from a
per-module or per-entry-point page.

## Technical Context

**Language/Version**: Python 3.11+, extending the existing `doc_generator`
package only; no changes to `parser_engine`, `repository_metadata`, or
`dependency_graph` (unlike 022, this feature needs no new symbol-level data —
it only reuses `entry_point_diagram.identify_entry_points()`'s already-built
output)

**Primary Dependencies**: Existing `doc_generator`,
`entry_point_diagram.identify_entry_points()` (022), `dependency_graph`, and
`repository_metadata` packages (reused unmodified); no new Python dependency;
reuses the vendored Mermaid classic UMD bundle from
`src/doc_generator/assets/mermaid.min.js` (013) — no new client-side asset

**Storage**: No new persistence. The use-case selection (which entry points
qualify, and as what kind) is recomputed from the already-loaded
`RepositoryBundle` + `DependencyGraph` on every generation run, exactly like
021's major-class ranking and 022's entry-point set — never separately
stored. The single generated page reuses 012's `DocPageManifestStore` for the
new page kind.

**Testing**: pytest, asserting: a fixture repository exposing a CLI command
and an API route handler produces a use-case diagram with two distinct actor
nodes, each linked to its own use-case node (spec SC-001); a plain function
entry point connects to a single shared generic actor; multiple entry points
of the same kind share one actor node instead of duplicating it; a
repository with zero identifiable entry points produces no use-case-diagram
page and no broken home-page link; correct incremental add/update/remove
behavior for the new page kind — no headless-browser rendering test,
consistent with 013/021/022.

**Target Platform**: Any standard web browser with JavaScript enabled,
opening the generated documentation from local files or a static host;
generation runs on Windows/macOS/Linux like the rest of the toolchain

**Project Type**: Extension of the existing internal documentation-generation
library (`doc_generator`, feature 012); no new top-level package, no changes
outside `doc_generator`

**Performance Goals**: A single linear pass over `identify_entry_points()`'s
already-computed result (itself linear in repository symbol count, per 022);
building the actor/use-case selection and rendering it is O(entry point
count) with no further graph traversal — expected to add no perceptible
overhead to a documentation regeneration run of any size, consistent with
021/022's performance profile for their own selection steps.

**Constraints**: Zero network requests at view time (unchanged — same
vendored Mermaid asset as 013/021/022); Mermaid label text must never contain
a literal, unescaped `"` (same sanitization standard 021/022 held themselves
to, reusing the existing `_escape_label` helper); read-only analysis only, no
new writes outside the existing `outputRoot`; no changes to
`entry_point_diagram.identify_entry_points()`'s public shape or behavior —
this feature only calls it, per the brief's explicit framing ("Consomme la
même identification de points d'entrée que 8.2").

**Scale/Scope**: One single, repository-wide use-case-diagram page (not one
per module, not one per entry point) — its size grows with entry-point count
only, same as 022's per-diagram size, not with overall repository size; no
inclusion cap is needed (unlike 021's 40-class cap) because there is no
shared page these actors/use-cases compete with unrelated symbols for space
on — every node shown is, by construction, an entry point or one of at most
three actors.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Confidentialite absolue**: pass — every input (the entry-point list
  022 already derives from already-local symbol/graph data) is already
  local; no new network call is introduced.
- **Zero exposition reseau par defaut**: pass — no new server surface; the
  new page is a static file served the same way existing pages are.
- **Jamais de repli silencieux vers le cloud**: pass — not applicable, no
  inference is involved in building this diagram.
- **Traçabilite des reponses IA**: pass — not applicable, this diagram
  renders structural data only (already-identified entry points), not
  AI-generated text.
- **Re-indexation incrementale**: pass — no full reindex is introduced.
  The use-case selection is recomputed from the already-in-memory
  bundle/graph on each run (a cheap structural scan reusing 022's own
  entry-point computation, not a source re-parse); impacted-page tracking is
  extended, not replaced, so the page regenerates only when relevant.
- **Infrastructure minimale et stockage local**: pass — no new storage, no
  new service; reuses the existing manifest store and static file writer.
- **Depot analyse en lecture seule**: pass — unaffected; still only writes
  inside the existing documentation `outputRoot`.

## Project Structure

### Documentation (this feature)

```text
specs/023-repository-use-case-diagram/
├── plan.md               # This file (/speckit-plan command output)
├── research.md           # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── use-case-diagram.md
└── tasks.md               # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── doc_generator/
│   ├── use_case_diagram.py     (new: Actor, UseCase, UseCaseDiagramSelection
│   │                            dataclasses + select_use_cases(bundle, graph)
│   │                            — selection only, mirroring class_diagram.py's
│   │                            role; calls entry_point_diagram.identify_
│   │                            entry_points() unmodified, no new detection)
│   ├── mermaid_diagram.py      (modified: add
│   │                            build_use_case_diagram_mermaid_source,
│   │                            mirroring build_class_diagram_mermaid_source
│   │                            — renders a UseCaseDiagramSelection to the
│   │                            flowchart-workaround Mermaid text already
│   │                            used by docs/diagrams/use-case-diagram.md,
│   │                            as UseCaseDiagramSource)
│   ├── generator.py            (modified: generateUseCaseDiagramPage;
│   │                            wire into generateRepositoryDocumentation;
│   │                            pass the page into generateOverviewPage for
│   │                            the home-page link, mirroring
│   │                            classDiagramPage)
│   ├── impact.py                (modified: extend RegenerationImpactSet
│   │                            coverage to the use-case-diagram page,
│   │                            reusing the entry-point list impact.py
│   │                            already computes for 022's sequence-diagram
│   │                            invalidation — no duplicate computation)
│   ├── links.py                 (modified: use_case_diagram_page_id(),
│   │                            use_case_diagram_output_paths(), mirroring
│   │                            class_diagram_page_id()/
│   │                            class_diagram_output_paths())
│   ├── models.py                (modified: extend PageKind with
│   │                            "use-case-diagram")
│   ├── templates/
│   │   ├── use_case_diagram.md.jinja  (new, mirrors class_diagram.md.jinja)
│   │   └── home.md.jinja              (modified: optional
│   │                                    "[View the repository use-case
│   │                                    diagram]" link, mirroring the
│   │                                    existing class-diagram link)
│   └── entry_point_diagram.py   (reused, unmodified: identify_entry_points(),
│                                 EntryPoint, EntryPointKind — 022)
└── dependency_graph/, repository_metadata/, parser_engine/  (untouched)
```

**Structure Decision**: Same as 013/021/022 — keep this feature entirely
inside the existing `doc_generator` package, with zero changes outside it
(unlike 022, which needed one small, scoped `parser_engine`/
`repository_metadata` addition for decorator capture; this feature needs no
new symbol-level data, so it touches nothing outside `doc_generator`). Within
`doc_generator`, mirror the existing two-stage split between selection and
rendering that `class_diagram.py`/`entry_point_diagram.py` (paired with
`mermaid_diagram.py`) already establish: `use_case_diagram.py` decides which
actors/use-cases exist; `mermaid_diagram.py` gains a sibling function that
renders that selection into the flowchart-workaround Mermaid text. Page
placement mirrors 021 exactly (a single page linked from the wiki's overview/
home page), not 022 (one page per entry point) — this diagram is
repository-wide by definition, per spec FR-001.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

No constitution violations, and no accepted-limitation gaps to carry forward
(unlike 022's Python-only decorator detection, this feature introduces no new
detection logic of its own — it inherits 022's existing CLI/API-route
detection scope, including its existing Python-only limitation, without
changing it).

## Constitution Check After Design

Re-checked against `research.md` and `data-model.md`: no new violations.
The only new read is `entry_point_diagram.identify_entry_points()`'s
already-computed, already-local result; the one new extraction step (turning
entry points into an actor/use-case selection) is a pure, in-memory
transformation of data 022 already produces, not new source parsing;
incremental regeneration is extended, not bypassed; no new storage or
service is introduced; `entry_point_diagram`'s public shape is untouched.
