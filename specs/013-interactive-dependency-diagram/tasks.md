# Tasks: Interactive Dependency Diagram

## Phase 1: Setup

**Goal:** Vendor the Mermaid rendering library locally so no part of this feature ever depends on a CDN.

**Independent test criteria:** `src/doc_generator/assets/mermaid.min.js` exists and is the classic (non-module) UMD browser build, not the ES-module build.

- [X] T001 [P] Vendor the Mermaid classic (non-module) UMD browser bundle at `src/doc_generator/assets/mermaid.min.js`, per `research.md` Decision 2 (must be the classic script build — the ES-module build is blocked by browser CORS policy under `file://`).

## Phase 2: Foundational

**Goal:** Build the Mermaid-source generator, the local-asset writer support, and the shared rendering/layout plumbing every diagram page depends on.

**Independent test criteria:** Given a hand-built `DiagramExport`, `build_mermaid_source(...)` returns valid, deterministic Mermaid flowchart text with resolved click hrefs; a rendered page's HTML contains a working `<pre class="mermaid">` element and loads the local script.

- [X] T002 Create `src/doc_generator/mermaid_diagram.py` with a `MermaidDiagramSource` dataclass (`diagramPageId`, `sourceText`, `nodeIdMap`, `clickTargets`) per `data-model.md`.
- [X] T003 Implement `build_mermaid_source(...)` in `src/doc_generator/mermaid_diagram.py` per `contracts/mermaid-diagram-render.md`: emit one Mermaid `flowchart` node per `DiagramExport` node and one directed edge per `DiagramExport` edge, assign short synthetic node ids (`n0`, `n1`, …) per `research.md` Decision 6, resolve each node's owning module page the same way `DocGenerator._resolve_module_key_by_path` does, and produce a valid, non-blank flowchart block even when `diagram.edges` is empty (rendering at least the focused node) per `spec.md` Edge Cases.
- [X] T004 Extend `src/doc_generator/writer.py` with an `ensure_mermaid_asset(outputRoot)` method on `DocumentationWriter` that copies `src/doc_generator/assets/mermaid.min.js` into `outputRoot/assets/mermaid.min.js` through the existing containment guard, creating it if missing and leaving it untouched when already present and unchanged.
- [X] T005 Update `src/doc_generator/html_render.py` to rewrite a rendered ```` ```mermaid ```` fenced code block (`<pre><code class="language-mermaid">…</code></pre>`) into `<pre class="mermaid">…</pre>` per `research.md` Decision 4, and to compute/pass an assets-relative script path into the layout template.
- [X] T006 [P] Update `src/doc_generator/templates/layout.html.jinja` to load the vendored script via a page-relative, classic `<script src="…assets/mermaid.min.js">` tag and call `mermaid.initialize({ startOnLoad: true })` once per page, per `research.md` Decision 7.

**Checkpoint**: Foundation ready - user story implementation can now begin.

## Phase 3: User Story 1 - View a module's dependencies as an interactive diagram

**Goal:** Embed a real, rendered Mermaid diagram of a module's outgoing and incoming dependencies into its existing diagram page.

**Independent test criteria:** Opening a generated diagram page's HTML directly (no server) shows a rendered diagram of that module's real dependencies, with outgoing and incoming edges visually distinguishable, and zero network requests.

- [X] T007 [P] [US1] Update `src/doc_generator/templates/diagram.md.jinja` to embed the ```` ```mermaid ```` fenced block (`mermaid_source.sourceText`) above the existing "Related modules" links and "Edges" table from 012, per `research.md` Decision 3.
- [X] T008 [US1] Wire `build_mermaid_source(...)` into `DocGenerator.generateDependencyDiagramPage` in `src/doc_generator/generator.py`, passing the resulting `MermaidDiagramSource.sourceText` into the `diagram.md.jinja` render context.
- [X] T009 [US1] Wire `DocumentationWriter.ensure_mermaid_asset(...)` into `DocGenerator.generateRepositoryDocumentation` in `src/doc_generator/generator.py` so `outputRoot/assets/mermaid.min.js` exists after any full or incremental generation run that writes at least one page of **any** kind (home, module, or diagram) — not diagram pages only, since `research.md` Decision 7 loads the script from the shared layout every page uses, so a module-only or home-only incremental run must not leave that reference broken.

**Checkpoint**: At this point, opening a generated diagram page in a browser shows a real interactive diagram of that module's real dependencies, independently of navigation (US2) or large-repo scoping (US3).

## Phase 4: User Story 2 - Navigate to a symbol's documentation from the diagram

**Goal:** Make every diagram node a working link to its own documentation page.

**Independent test criteria:** Every node that resolves to a current documentation page carries a Mermaid `click` directive with the correct HTML-relative href; clicking it in a browser opens that exact page.

- [X] T010 [US2] Ensure `build_mermaid_source(...)` in `src/doc_generator/mermaid_diagram.py` emits a `click NodeId href "…"` directive with the correct HTML-relative href (via `links.relative_output_link`, per `research.md` Decision 5) for every node that resolves to a current documentation page.
- [X] T011 [US2] Handle nodes that do not resolve to a current documentation page in `src/doc_generator/mermaid_diagram.py`: still render the node (unclickable) but omit its `click` directive, per `spec.md` Edge Cases and `contracts/mermaid-diagram-render.md` Failure expectations.
- [X] T012 [US2] Add an integration test in `tests/integration/test_mermaid_diagram.py` that generates documentation for the sample repository and asserts every resolvable node's `click` href in each diagram page's HTML points at the correct target module's HTML output path.

**Checkpoint**: At this point, every node in a generated diagram is clickable and opens the correct page (US1 and US2 both functional together).

## Phase 5: User Story 3 - Keep large diagrams readable via direct-dependency scoping

**Goal:** Guarantee a diagram never grows beyond one focused module's direct dependencies, however large the repository is.

**Independent test criteria:** In a repository with many modules, a single module's diagram contains only that module's direct (one-hop) neighbors, and a module with many direct dependencies still produces one well-formed diagram.

- [X] T013 [US3] Add an integration test in `tests/integration/test_mermaid_diagram.py` confirming a module's `MermaidDiagramSource` only ever contains that module's direct `DiagramExport` nodes/edges, never the full repository graph, even when the indexed repository has many unrelated modules.
- [X] T014 [US3] Add an integration test confirming a module with many direct dependencies still produces a single, well-formed Mermaid flowchart block (valid syntax, one node per dependency, no truncation or corruption) from `build_mermaid_source(...)`.

**Checkpoint**: All three user stories are independently functional; diagrams render, navigate, and stay scoped correctly.

## Phase 6: Polish & Cross-Cutting Concerns

**Goal:** Confirm the feature is fully self-contained, offline, and idempotent, handles the zero-dependency edge case, and matches the quickstart end to end.

**Independent test criteria:** No generated page references a CDN or external URL; the vendored asset is present and stable across regenerations; an isolated module still renders a valid diagram; the full quickstart flow works.

- [X] T015 [P] Add an integration test in `tests/integration/test_mermaid_diagram.py` asserting no `http://`/`https://` reference appears anywhere in generated page HTML, that `assets/mermaid.min.js` exists under `outputRoot` after generation, and that the `<script>` tag loading it carries no `type="module"` attribute (per `research.md` Decision 2 — a module script is blocked by browser CORS policy under `file://`, so a regression here would silently break local-file viewing).
- [X] T016 Add a test confirming a second, unchanged generation run does not rewrite `outputRoot/assets/mermaid.min.js` (writer idempotency for the vendored asset, per `data-model.md` Validation).
- [X] T017 Validate the end-to-end flow against `specs/013-interactive-dependency-diagram/quickstart.md` (diagram renders and is interactive, click navigation, direct-dependency scoping, no-JS fallback, self-contained asset) and fix any mismatches across `src/doc_generator/`.
- [X] T018 Add a unit test in `tests/unit/test_mermaid_diagram.py` confirming `build_mermaid_source(...)` produces a valid, non-empty Mermaid flowchart block for a `DiagramExport` with zero edges (e.g., an isolated module with no incoming or outgoing dependencies), rendering at least the focused node rather than an empty, blank, or malformed block, per `spec.md` Edge Cases (missing).

## Dependencies

- `T001` has no dependencies and can start immediately.
- `T002` depends on `T001` only for asset availability at runtime, not at authoring time; it can be written in parallel with `T001`.
- `T003` depends on `T002`.
- `T004` depends on `T001` (the asset must exist to be copied).
- `T005` does not depend on `T003`; it only needs the fenced-code-block HTML shape `python-markdown` already produces, so it can proceed independently.
- `T006` can run in parallel with `T002`-`T005` (different file).
- `T007` can run in parallel with `T008` and `T009` (different files).
- `T008` depends on `T003`.
- `T009` depends on `T004`.
- `T010` and `T011` depend on `T003`.
- `T012` depends on `T007`, `T008`, `T009`, `T010`, and `T011`.
- `T013` and `T014` depend on `T003`.
- `T015` depends on `T005`, `T006`, and `T009`.
- `T016` depends on `T004` and `T009`.
- `T017` is a final validation after `T007` through `T016`.
- `T018` depends on `T003`.

## Parallel Execution Examples

### Foundational

```text
Task: T002 -> create MermaidDiagramSource in src/doc_generator/mermaid_diagram.py
Task: T006 -> load the vendored script in src/doc_generator/templates/layout.html.jinja
```

### User Story 1

```text
Task: T007 -> embed the mermaid fenced block in src/doc_generator/templates/diagram.md.jinja
Task: T008 -> wire build_mermaid_source into generateDependencyDiagramPage in src/doc_generator/generator.py
Task: T009 -> wire ensure_mermaid_asset into generateRepositoryDocumentation in src/doc_generator/generator.py
```

### User Story 2

```text
Task: T010 -> emit click directives in src/doc_generator/mermaid_diagram.py
Task: T012 -> add navigation integration test in tests/integration/test_mermaid_diagram.py
```

## Implementation Strategy

1. Vendor the Mermaid asset and build the shared Mermaid-source/rendering/layout plumbing first (Setup + Foundational), since every user story renders through it.
2. Add User Story 1 (the diagram actually rendering) as the MVP slice - it proves the vendored asset and post-processing pipeline work end to end.
3. Add User Story 2 (click navigation) next, since it is the feature's explicit success criterion and builds directly on US1's rendered diagram.
4. Add User Story 3 (direct-dependency scoping) to lock in and verify the readability guarantee, which is largely already true by construction once `build_mermaid_source` only ever consumes one module's `DiagramExport`.
5. Finish with the self-containment/idempotency checks and a full quickstart pass.
