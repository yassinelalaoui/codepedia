# Research: Entry Point Sequence Diagrams

## Decision 1 — Entry-point candidate pool: functions AND methods, module-level and class-owned

**Decision**: An entry-point candidate is any `FunctionSymbol` in the
repository bundle (module-level function or class method) whose name does
not start with `_`, excluding nested/closure functions (tracked via each
owning function's `nestedSymbols`) — the same "public" definition
`_documented_functions` (`generator.py`) already applies to module-level
functions, broadened here to also include public class methods.

**Rationale**: The spec's entry-point definition ("any public function") is
not restricted to module-level functions; a CLI command or route handler
could in principle be a bound method, and a plain "public function nothing
else calls" is equally meaningful whether it's a module function or a public
method. Excluding nested functions matches the existing convention (a
closure isn't independently reachable/public) and keeps candidate discovery
consistent with how `_documented_functions` already filters for module
pages.

**Alternatives considered**: Restrict to module-level functions only,
matching `_documented_functions` exactly — rejected because it would silently
exclude a legitimate entry point implemented as a method (not the case in
this project's own CLI/API code today, but not something the spec excludes
either).

## Decision 2 — "Never called by another function" reuses `functions_calling` as-is

**Decision**: A candidate qualifies as an entry point under FR-001's third
branch when `graph.functions_calling(candidate.id) == []` — no new
`DependencyGraph` method needed.

**Rationale**: `functions_calling(focus)` (`dependency_graph/graph.py:195`)
already returns only `"call"`-type dependents whose `symbolType == "function"`
— i.e. it already excludes callers that are module-level top-level
statements (whose caller node is the *module*, not a function). This exactly
matches the spec's literal wording ("never called by **another function**"):
a function invoked only from module-level script code (e.g. an
`if __name__ == "__main__": main()` guard) still correctly qualifies as an
entry point, because it isn't called by another *function*. No change to
`dependency_graph` is needed for this branch.

**Alternatives considered**: Writing a bespoke "has any incoming call edge at
all" check — rejected: it would incorrectly disqualify a `main()` invoked
only from a module-level guard, which is precisely the shape of this
project's own CLI entry point (`cli/main.py`'s `if __name__ == "__main__":
app()`).

## Decision 3 — CLI/API-route detection: capture decorator text during Python extraction, pattern-match on it in `doc_generator`

**Decision**: Extend the Python extraction path only
(`parser_engine/extractor.py::build_function`, which already parses via
Python's own `ast` module) to also unparse each function's
`node.decorator_list` (using the existing `_python_unparse` helper already
used for type annotations) into a new `decorators: tuple[str, ...]` field on
`parser_engine.symbols.FunctionSymbol`. Thread it through
`repository_metadata.sqlite_store._convert_function_symbol` into the
already-generic, already-persisted `metadata` JSON column (alongside the
existing `owner`/`returnType` entries — no schema change, `metadata` is a
plain JSON blob column already). `doc_generator` then classifies a function
as a CLI command / API route handler by regex-matching the *attribute name*
in its decorator text against a fixed, scoped set:
`\.(command|callback)\(` for CLI, `\.(get|post|put|delete|patch)\(` for API
routes — matching on the attribute (`.command`, `.get`, ...) rather than the
decorated-with variable name (`app`), so it survives the instance being
renamed, while staying scoped to this project's own two frameworks (Typer,
FastAPI), consistent with spec Assumptions ("recognizing this project's own
CLI/route registration patterns").

**Rationale**: Confirmed by reading the actual extraction code
(`parser_engine/extractor.py`, not the separate, currently-unused
tree-sitter-based `parser_engine/parsers/` path) that Python symbol/call
extraction already runs on a full `ast.parse()` tree — `decorator_list` is
already sitting on every `ast.FunctionDef`/`AsyncFunctionDef` node the
extractor visits, just discarded today. Capturing and unparsing it is a
small, targeted, Python-only addition — not a new static-analysis subsystem
— and reuses a helper (`_python_unparse`) already exercised for a different
field on the same node. This is the same class of decision as spec FR-003 in
`021-repository-class-diagram` (a real, scoped data-capture gap, closed
rather than routed around) — except here the spec's own entry-point
definition requires the classification, so it cannot be deferred as an
accepted limitation.

**Scope carried forward (not closed here)**: The brace-language extraction
path (`_extract_brace_inventory`, covering JS/TS/Java/Go/Rust) has no
equivalent decorator/annotation capture and none is added by this feature —
those languages' functions can still qualify as entry points via the third
branch (uncalled public function), just never via the CLI-command/API-route
branches. This mirrors 021's accepted-limitation pattern; see Complexity
Tracking in `plan.md`.

**Alternatives considered**:
- Regex-scanning raw source text for `@app\.(get|post|...)` — rejected:
  fragile against multiline decorators, aliasing, and indentation, and this
  project already has a real AST available at the point decorators would be
  captured; using it is strictly more reliable for the same cost.
- Extending `dependency_graph`'s `DependencyNode.metadata` instead of the
  symbol layer — rejected: decorator text is a property of the *symbol*
  (`FunctionSymbol`), not a dependency relationship; the symbol layer is the
  correct owner, matching how `owner`/`returnType` are already stored there.

## Decision 4 — Bounded traversal reuses `functions_called_by` as-is; order is reconstructed via each call edge's `lineStart`

**Decision**: Build each entry point's ordered call sequence with a
depth-bounded, pre-order DFS over `graph.functions_called_by(focus)`
(`dependency_graph/graph.py:198`) — exactly the existing helper the feature
brief names, unmodified. Because `functions_called_by` returns nodes backed
by an internal `set` (`_SimpleDiGraph.outgoing`), its result order is not the
real call order; at each step, the returned callee nodes are re-sorted by
their originating call edge's `metadata["lineStart"]`
(`graph.edges[(focus_id, callee.id, "call")]`, already captured by
`_ingest_calls`) before recursing, to reconstruct the real order calls occur
in the caller's source.

**Rationale**: `_ingest_calls` (`dependency_graph/graph.py:284-308`) already
stores `lineStart`/`lineEnd` in each call edge's `metadata` — this data
already exists and needs no new extraction. `DependencyGraph.edges` is a
plain (non-underscore) instance attribute, so this is a same-package,
already-public read, not a new API surface. This also naturally satisfies
the Clarifications session's resolution: because `functions_called_by`
already returns at most one node per distinct callee (edges are deduplicated
by `(source, target, type)` — the same limitation the Clarifications session
documented), repeated calls to the same target are automatically collapsed
into a single step with no extra logic required.

**Termination**: A strictly-incrementing depth counter, capped at a fixed
`MAX_CALL_DEPTH`, guarantees termination on its own for recursion (a function
calling itself) and cycles (A calls B calls A) — every hop consumes one unit
of depth budget regardless of whether a node repeats, so no separate
"visited" tracking is required for termination (spec FR-005 / Edge Case 1).

**`MAX_CALL_DEPTH` value**: `6`. Chosen as an implementation default (per
spec's Assumptions: the exact cap is not fixed by the spec) — deep enough to
show a realistic multi-layer call chain (e.g. CLI command → orchestrator →
pipeline stage → helper → storage call), shallow enough to stay readable
and to bound worst-case diagram size to a small constant, consistent in
spirit with 021's `MAX_INCLUDED_CLASSES = 40` readability cap.

**Alternatives considered**: Tracking a per-path "visited" set to
additionally suppress revisiting the same node — rejected as unnecessary
scope: the spec only requires depth-bounding (FR-005), the depth cap alone
already guarantees termination, and a sequence diagram legitimately can show
the same participant invoked more than once (that's normal sequence-diagram
semantics, not a defect).

## Decision 5 — Call-step module/class attribution resolved from the already-loaded `RepositoryBundle`, not from `DependencyGraph`

**Decision**: A `DependencyNode` for a function carries `sourceFile` (usable
for module attribution via the existing `_resolve_module_key_by_path`
pattern) but not its owning class. Rather than extending
`DependencyNode`/`DependencyGraph` to carry class ownership, `doc_generator`
resolves each call step's originating class (when the callee is a method) by
looking it up in the already-loaded `RepositoryBundle`: a
`method_symbol_id -> (class_id, class_name)` map built once per generation
run by walking `bundle.files[*].classes[*].methods`, the same relationship
`ClassSymbol.methods` already encodes.

**Rationale**: This mirrors the existing precedent exactly — `generator.py`
already resolves module ownership by cross-referencing the loaded bundle
(`_resolve_module_key_by_path`) rather than by adding fields to
`DependencyNode`. Keeping class attribution at the same layer, resolved the
same way, avoids touching `dependency_graph` at all beyond calling its
existing, unmodified helpers — matching the feature brief's explicit framing
("parcours borné du graphe via les helpers existants").

**Alternatives considered**: Adding an `owner`/class-id field to
`DependencyNode.metadata` in `_ingest_inventory_nodes` — rejected: it would
touch `dependency_graph` (a package the brief scopes this feature to reuse,
not modify) for data `doc_generator` can already derive locally from data it
already loads.

## Decision 6 — Page identity uses a stable `(sourceFileId, owner, name)` key, not `FunctionSymbol.id`

**Decision**: Each entry point's sequence-diagram page is identified and
slugged using a stable key derived from `(module.sourceFileId, function.owner
or owning class name, function.name)` — not `FunctionSymbol.id`.

**Rationale**: `FunctionSymbol.id` is `stable_symbol_id(source_file_id, kind,
name, line_start, line_end)` (`repository_metadata/sqlite_store.py:138`) — a
content/position hash that shifts on *any* edit that moves the function's
line range (including edits to unrelated code earlier in the same file).
Using it as a page identity key would make "the same entry point's page"
look like a different page on almost every run, defeating incremental
regeneration (manifest diffing, stable output paths) — the exact problem
`generator.py`'s own docstring already documents and solves for module pages
via `sourceFileId` instead of `ModuleSymbol.id`. A name-based key changes
only on an actual rename/move, matching `sourceFileId`'s own stability
characteristics.

**Alternatives considered**: Using `FunctionSymbol.id` directly (simplest
code, but silently breaks incremental regeneration and produces page-identity
churn on unrelated edits) — rejected for the reason above.

## Decision 7 — One new page kind (`"sequence-diagram"`), output path via the existing generic `diagrams/{slug}.md` convention, linked from the entry point's existing module-page section

**Decision**: Add a new `PageKind` value `"sequence-diagram"`. Reuse
`links.diagram_output_paths(slug)` unmodified (`diagrams/{slug}.md`/`.html`
— already generic, not module-specific despite living next to
`diagram_page_id`) for the new page's output path, with
`links.page_slug(entry_point_name, entry_point_key)` for the slug (same
helper module pages already use). Add a new `sequence_diagram_page_id(key)
-> f"sequence:{key}"` id function (a new namespace prefix, distinct from
`diagram:` and `class-overview`, since a function's stable key and a
module's `sourceFileId` are drawn from different id spaces and must not
collide). The page is linked from the entry point's existing `###`/`####`
section on its *owning module's* page (the only page a function currently
appears on — functions have no page of their own today), the same way the
module page already links out to its dependency-diagram page.

**Rationale**: Directly reuses the exact convention the feature brief names
("réutilisant la convention diagrams/{slug}.md déjà en place"). This fully
satisfies spec FR-009 literally, not just approximately: each entry point
gets its own dedicated output page (`diagrams/{slug}.md`), the same way the
existing per-module dependency diagram is that module's own diagram page
despite living in a separate file from the module page itself. The
*discoverability* question — how a reader finds that page — is a separate
concern, answered the same way the existing dependency diagram already
answers it: linked from the section that documents the owning entity
(`module.md.jinja`'s per-function `###` block, mirroring the module page's
existing link to its own dependency diagram).

**Alternatives considered**: Giving every entry point its own full
module-level page just to host the link — rejected as unnecessary
duplication of `module.md.jinja`'s existing per-function section, which
already exists and already anchors each function by id.

## Decision 8 — Incremental regeneration: entry-point pages depend on their function symbol's identity *and* the reachable call subgraph

**Decision**: Extend `compute_regeneration_impact` so that a changed
function/class symbol invalidates:
1. any entry-point page rooted at that symbol (if it is itself an entry
   point), and
2. any entry-point page whose already-recorded call sequence *includes*
   that symbol as a step (tracked the same way page-to-page link impact is
   already tracked today via `PageManifestEntry.linkedPageIds` /
   `_add_referrers_of`-style reasoning), so a change three hops down an
   entry point's call chain still triggers that entry point's diagram to
   regenerate.
Entry-point *set membership* itself (which functions currently qualify)
is recomputed from the freshly-loaded bundle + graph on every run, the same
way 021's major-class ranking is recomputed every run rather than
incrementally diffed (021 Research Decision 3) — cheap, in-memory, no source
re-parse.

**Rationale**: Consistent with the existing incremental-impact model
(`impact.py`) and with 021's established precedent for a similarly
graph-derived, cheap-to-recompute selection.

## Decision 9 — Mermaid `sequenceDiagram` rendering

**Decision**: Render as Mermaid `sequenceDiagram` syntax: one `participant`
per distinct symbol appearing in the call sequence (entry point plus every
call-step target), each labeled `Module.Class.function` (module resolved via
the existing `_resolve_module_key_by_path` pattern, class via Decision 5,
falling back to just `Module.function` when the callee has no owning class,
and to the raw/unresolved callee name when the target's origin cannot be
resolved from the graph at all — Edge Case 4), followed by one `->>` message
per `CallStep` in traversal order. Labels are sanitized the same way
existing Mermaid label sanitizers already do (`_escape_label` /
`_sanitize_class_diagram_label` precedent) — participant names must not
contain a literal `;` or unescaped `"`.

**Rationale**: `sequenceDiagram` is Mermaid's dedicated syntax for showing
ordered messages between participants — the natural match for "ordered call
steps between symbols," and renders through the same already-vendored,
offline `mermaid.min.js` bundle every other diagram in this project already
uses (013/021), so no new asset or dependency is introduced.

**Alternatives considered**: Reusing `flowchart`/classDiagram-style rendering
— rejected: Mermaid's flowchart has no native notion of ordered
request/response messages between the same two participants, which is
exactly what a call sequence needs to express.
