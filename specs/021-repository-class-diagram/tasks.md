# Tasks: Repository Class Diagram

## Phase 1: Setup

**Goal:** N/A for this feature — no new package, dependency, or vendored asset is needed. The `doc_generator` package, its test directories, and the vendored `mermaid.min.js` (013) already exist and are reused as-is.

*(No tasks in this phase.)*

## Phase 2: Foundational

**Goal:** Add the one new `PageKind` value and the page id/output-path helpers every other task needs to address the class-diagram page, per `data-model.md`'s `PageKind` extension and `plan.md`'s `links.py` change.

**Independent test criteria:** `links.class_diagram_page_id()` and `links.class_diagram_output_paths()` return the fixed id/paths from `contracts/class-diagram.md` (`diagram:class-overview`, `diagrams/class-overview.md`/`.html`); `"class-diagram"` is a valid `DocPage.kind`.

- [X] T001 [P] Extend the `PageKind` literal in `src/doc_generator/models.py` to include `"class-diagram"`, per `data-model.md`'s `PageKind extension`.
- [X] T002 [P] Add `class_diagram_page_id()` (returns the fixed id `"diagram:class-overview"`) and `class_diagram_output_paths()` (returns the fixed pair `("diagrams/class-overview.md", "diagrams/class-overview.html")`) to `src/doc_generator/links.py`, mirroring the existing `module_page_id`/`diagram_page_id`/`module_output_paths`/`diagram_output_paths` helpers, per `contracts/class-diagram.md`.

**Checkpoint**: Foundation ready - user story implementation can now begin.

## Phase 3: User Story 1 - View the repository's class diagram

**Goal:** Generate a single, repository-wide class diagram (major classes, methods, inheritance only) and link it from the wiki's overview page, fully wired into incremental regeneration.

**Independent test criteria:** `quickstart.md` "Validate the class diagram" — against a repository with classes across multiple modules including a cross-module inheritance relationship, the overview page links to exactly one class diagram showing the major classes, their methods, and that relationship (SC-002).

- [X] T003 [P] [US1] Create `src/doc_generator/class_diagram.py` with the `ClassDiagramSelection`, `SelectedClass`, and `SelectedMethod` dataclasses (per `data-model.md`) and `select_major_classes(bundle, graph) -> ClassDiagramSelection`, implementing the inheritance-first, then edge-count ranking heuristic capped at 40 (deterministic tie-break: edge count descending, class name ascending, id ascending), per `research.md` Decision 2 and `contracts/class-diagram.md`. Mirrors `diagrams.py::build_module_diagram`'s role exactly (selection only, no Mermaid text) per Decision 5.
- [X] T004 [US1] Add the `ClassDiagramSource` dataclass and `build_class_diagram_mermaid_source(selection: ClassDiagramSelection) -> ClassDiagramSource` to the existing `src/doc_generator/mermaid_diagram.py`, emitting one `classDiagram` node per `SelectedClass` (name + methods, no attributes) and one `ChildClass <|-- ParentClass` line per `selection.inheritanceEdges`, sanitizing every label by also replacing `;` with `,` (extend `_escape_label` or add a sibling sanitizer used by both), per `research.md` Decision 4 and `contracts/class-diagram.md`. Depends on T003 for the `ClassDiagramSelection` shape.
- [X] T005 [P] [US1] Add a unit test `tests/unit/test_class_diagram.py` for `select_major_classes`: hand-built classes/graph (no fixture files, mirroring `tests/unit/test_mermaid_diagram.py`'s style) asserting inheritance participants are always included, remaining slots fill by edge count with the documented tie-break, the result is capped at 40 for a 45-class input, a class with zero methods is still included with an empty method list, and a zero-class repository yields `includedClasses == ()`. Depends on T003.
- [X] T006 [P] [US1] Add unit tests to `tests/unit/test_mermaid_diagram.py` for `build_class_diagram_mermaid_source`: valid non-empty `classDiagram` text, one node per included class with its methods and no attribute lines (FR-003), a `SelectedClass` with an empty `methods` tuple still renders as a valid (not malformed) `classDiagram` node per spec.md's "class with no methods" edge case, one `<|--` line per inheritance edge, an inheritance edge referencing an excluded class is silently dropped rather than rendered dangling, and a class/method name containing a literal `;` is rendered with `,` instead so the output stays parseable. Depends on T004.
- [X] T007 [US1] Create `src/doc_generator/templates/class_diagram.md.jinja` embedding the ` ```mermaid ` fenced block (`class_diagram_source.sourceText`) plus a note stating how many classes were omitted (`omittedClassCount`) when it's greater than zero, mirroring `diagram.md.jinja`'s structure. Depends on T004.
- [X] T008 [US1] Implement `DocGenerator.generateClassDiagramPage() -> DocPage | None` in `src/doc_generator/generator.py`: calls `class_diagram.select_major_classes` then, only if `includedClasses` is non-empty, `mermaid_diagram.build_class_diagram_mermaid_source` (the same two-step call shape `generateDependencyDiagramPage` already uses), returning `None` for an empty selection; otherwise builds a `DocPage` of kind `"class-diagram"` at `links.class_diagram_page_id()`/`links.class_diagram_output_paths()`, rendered via `class_diagram.md.jinja` (T007), per `contracts/class-diagram.md`. Depends on T001, T002, T003, T004, T007.
- [X] T009 [US1] Wire `generateClassDiagramPage()` into `DocGenerator.generateRepositoryDocumentation` in `src/doc_generator/generator.py` (called once per run, not per module; written only when it returns a page) and into `DocGenerator.generateOverviewPage`/`src/doc_generator/templates/home.md.jinja` to add a link to it only when the page exists, per spec FR-007. Once this page is included in `doc_set.pages`, the existing generic `tests/integration/test_mermaid_diagram.py::test_no_cdn_reference_and_classic_script_tag` (which iterates `for page in doc_set.pages`, not a fixed page-kind list) automatically asserts it has zero `http://`/`https://` references and a local, non-module Mermaid script tag — this is what satisfies spec SC-004 for the new page kind; no new network-check test is needed. Depends on T008.
- [X] T010 [US1] Extend `compute_regeneration_impact` in `src/doc_generator/impact.py` per `research.md` Decision 3: add `links.class_diagram_page_id()` to `impactedPageIds` whenever `direct_symbol_ids` or `changed_dependency_edge_ids` is non-empty this run, so the repository-wide page always refreshes on any qualifying change (already-generic `removedPageIds` handling covers the "repo went from having classes to having none" case with no further change needed). Depends on T002.
- [X] T011 [US1] Add an integration test `tests/integration/test_class_diagram.py` (new file, reusing `_doc_generator_support.build_indexed_repo`'s alpha/beta/gamma fixture, which already has `Child(BaseThing)` as a cross-module inheritance pair) asserting a full generation run produces a class-diagram page containing `Child`, `BaseThing`, and the inheritance edge between them, and that the overview page links to it — mirroring `test_doc_generator_export.py`'s `_build_generator` helper pattern (US1 acceptance scenarios 1 & 2, SC-002). Depends on T009.
- [X] T012 [US1] Add an integration test (same file) asserting a repository with zero classes produces no class-diagram page and the overview page contains no broken/dead link to it (acceptance scenario 4, FR-004). Depends on T009.
- [X] T013 [US1] Add an integration test (same file) asserting incremental regeneration: after a full run, an edit unrelated to any class in the fixture followed by `generateRepositoryDocumentation(incremental=True, ...)` still regenerates the class-diagram page (per Decision 3's broad trigger, SC-003), mirroring `test_doc_generator_links.py`'s `test_incremental_regeneration_touches_only_impacted_pages_and_keeps_links_valid` pattern. Depends on T010, T011.

**Checkpoint**: At this point, User Story 1 (the only story in this feature) is fully functional and independently testable — this is also the complete feature.

## Phase 4: Polish & Cross-Cutting Concerns

**Goal:** Confirm the Mermaid output is actually parseable (not just plausible-looking), the quickstart passes end to end, and this repository's own documentation stays in sync with the new capability.

**Independent test criteria:** The generated `classDiagram` block for a label containing `;` parses cleanly under a real Mermaid parser; `quickstart.md` passes end to end; `docs/diagrams/class-diagram.md`, `docs/architecture.md`, and `README.md` accurately describe the new capability.

- [X] T014 [P] Add an integration test (`tests/integration/test_class_diagram.py`) asserting the Mermaid output for a class/method name containing `;` is well-formed (no bare `;`, balanced braces, valid `classDiagram` header). **Deviation from the original task wording**: no real Python (or any supported language) identifier can contain a literal `;`, so this can't be exercised through a parsed fixture file - it's tested at the same hand-built-selection level as T006. Shelling out to a Node/mermaid parser (as used ad hoc during planning/implementation to diagnose the original `;`-in-message-text bug and to validate this feature's Mermaid syntax choices) was judged not worth adding as a permanent test-suite dependency for a pure-Python project, per the constitution's "Infrastructure minimale" principle - see the test's own docstring for the full rationale.
- [X] T015 Validate the end-to-end flow against `specs/021-repository-class-diagram/quickstart.md` and fix any mismatches across `src/doc_generator/`.
- [X] T016 Update `docs/diagrams/class-diagram.md` (add `ClassDiagramSelection`/`SelectedClass`/`SelectedMethod`/`ClassDiagramSource` and their relationships to the `DocGeneratorPackage` namespace), `docs/architecture.md` (note the new repository-wide class-diagram capability in the `doc_generator` layer's description), and `README.md` (if the wiki's feature list is documented there) per this project's diagrams-maintenance convention (root `README.md`, `docs/architecture.md`, `docs/stack.md`, `docs/diagrams/` must stay in sync with every implemented feature).

## Dependencies

- `T001` and `T002` have no dependencies and can start immediately, in parallel (different files).
- `T003` has no dependency on T001/T002 — `class_diagram.py`'s selection logic needs only `RepositoryBundle`/`DependencyGraph`, not the page-id plumbing.
- `T004` depends on `T003` for the `ClassDiagramSelection` shape it consumes.
- `T005` depends on `T003`; `T006` depends on `T004` — both are pure unit tests and can run in parallel with each other.
- `T007` depends on `T004` (needs `ClassDiagramSource`'s field names).
- `T008` depends on `T001`, `T002`, `T003`, `T004`, and `T007` (assembles all of them into one page).
- `T009` depends on `T008`.
- `T010` depends on `T002` only (needs the page id, not the page itself).
- `T011` and `T012` depend on `T009`; they can run in parallel (independent test functions in the same new file, though as tasks they touch the same file so treat as sequential edits).
- `T013` depends on `T010` and `T011` (needs both the impact-tracking change and the base fixture-driven test setup already in the file).
- `T014` depends on `T006` (label sanitization) and `T011` (a working generation pipeline to source real output from).
- `T015` is a final validation after `T007` through `T014`.
- `T016` can start once the feature's shape is stable (after `T009`) and has no code dependency.

## Parallel Execution Examples

### Foundational

```text
Task: T001 -> extend PageKind in src/doc_generator/models.py
Task: T002 -> add page id/path helpers in src/doc_generator/links.py
```

### User Story 1

```text
Task: T005 -> unit test select_major_classes in tests/unit/test_class_diagram.py
Task: T006 -> unit test build_class_diagram_mermaid_source in tests/unit/test_mermaid_diagram.py
```

## Implementation Strategy

1. Complete the two tiny Foundational tasks (PageKind, page id/path helpers) — nothing else is blocked long by them, but the final page-assembly step (T008) needs both.
2. Build the selection/rendering pair (T003, T004) and their unit tests (T005, T006) first — this is the feature's actual logic and is fully testable without touching `generator.py` at all, exactly like `diagrams.py`/`mermaid_diagram.py` already are for the dependency diagram.
3. Add the template (T007) and wire everything into `DocGenerator` (T008, T009) — this is the only slice needed to make the feature visible in a generated wiki, and is this feature's entire MVP (there is only one user story).
4. Extend incremental regeneration (T010) and verify it, along with the zero-classes and cross-module-inheritance acceptance scenarios, with integration tests (T011-T013).
5. Finish with real-parser Mermaid validation (T014), a full quickstart pass (T015), and the repository's own documentation sync (T016).
