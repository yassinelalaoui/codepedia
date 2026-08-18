# Feature Specification: Entry Point Sequence Diagrams

**Feature Branch**: `022-entry-point-sequence-diagram`

**Created**: 2026-08-18

**Status**: Draft

**Input**: User description: "Construire la génération automatique d'un diagramme de séquence pour chaque point d'entrée identifié du dépôt (commande CLI, gestionnaire de route API, ou toute fonction publique jamais appelée par une autre fonction du dépôt analysé), montrant l'ordre des appels qu'il déclenche, à partir des arêtes d'appel déjà capturées dans le graphe de dépendances. Chaque diagramme doit être borné à une profondeur maximale fixe depuis le point d'entrée, pour qu'une chaîne d'appels contenant une récursion ou un cycle produise malgré tout un diagramme fini et lisible plutôt que de boucler indéfiniment. Un point d'entrée qui n'appelle aucune autre fonction doit produire un diagramme minimal (lui seul), jamais une interaction inventée. Critère de succès : sur un dépôt de test avec un point d'entrée appelant deux fonctions ou plus à travers plusieurs modules, le diagramme de séquence généré montre les appels dans leur ordre réel, avec le bon module/classe d'origine pour chaque appel."

**Note**: This feature was promised as a follow-up when
`021-repository-class-diagram` was split out of the originally broader "wiki
diagram types" feature ("The sequence-diagram and use-case-diagram
capabilities that were previously bundled with this one will be specified
separately"). This spec covers only the sequence-diagram capability; the
use-case-diagram capability remains a separate, not-yet-specified feature.

## Clarifications

### Session 2026-08-18

- Q: When the same entry point calls the same function more than once from different call sites, should the diagram show each call as its own separate step, or collapse repeated calls to the same target into a single step? → A: Collapse repeated calls into a single step, matching what the existing call edges already capture today (one edge per caller/callee pair, deduplicated); no changes to the dependency graph's call-edge capture.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View an entry point's call sequence (Priority: P1)

As a developer orienting myself in an unfamiliar repository, I want to see,
for each way the system can be triggered from the outside (a CLI command, an
API route, or any other public function nothing else in the repository
calls), a diagram of the calls it makes and the order it makes them in, so
that I can understand what actually happens when that entry point runs
without tracing the call chain by hand through the source.

**Why this priority**: This is the only user story in this feature; it
delivers the complete, standalone value of the feature by itself.

**Independent Test**: Run the tool against a repository containing an entry
point that calls two or more functions across multiple modules. Open the
documentation page for that entry point and confirm a sequence diagram is
present showing the calls in the order they actually happen, each attributed
to the correct originating module/class, matching the real source.

**Acceptance Scenarios**:

1. **Given** a repository containing a CLI command, an API route handler,
   and a plain public function that nothing else in the repository calls,
   **When** the wiki is generated, **Then** each of the three is treated as
   an entry point and gets its own sequence diagram.
2. **Given** an entry point that calls two or more functions spread across
   multiple modules, **When** its sequence diagram is opened, **Then** the
   calls are shown in the same order they actually occur, each one
   attributed to the correct originating module or class.
3. **Given** an entry point whose call chain is deeper than the fixed
   maximum depth this feature bounds diagrams to, **When** its sequence
   diagram is generated, **Then** the diagram stops at that depth and still
   renders as a complete, readable diagram rather than an error or a
   truncated/broken one.
4. **Given** an entry point that calls no other function in the repository,
   **When** its sequence diagram is generated, **Then** the diagram shows
   only that entry point acting alone, with no invented calls or
   interactions.
5. **Given** a function that is called by at least one other function in the
   analyzed repository and is not a CLI command or an API route handler,
   **When** entry points are identified, **Then** that function is not
   treated as an entry point and does not get its own sequence diagram.

---

### Edge Cases

- What happens when an entry point's call chain contains recursion (a
  function calling itself) or a cycle (A calls B calls A)? The diagram must
  still terminate at the fixed maximum depth and render as a finite,
  readable diagram instead of looping indefinitely or failing to generate.
- What happens when an entry point calls no other function at all? The
  diagram must show only that entry point, never a fabricated interaction
  with another symbol.
- What happens when the same function is called more than once, from
  different points in the same entry point's call chain? The repeated calls
  to that target are shown as a single step, using the one call site the
  dependency graph's existing call edges already record for that
  caller/callee pair (see Clarifications) — this is an existing limitation
  of the already-captured data, not a gap this feature needs to close.
- What happens when a call in the chain targets a function whose defining
  module or class cannot be resolved from the dependency graph (e.g. an
  external/unresolved dependency)? The call step must still appear in the
  diagram without breaking generation, using the best available identification
  for its origin.
- What happens when a repository has no identifiable entry points at all? No
  sequence diagrams are generated, and nothing broken or empty is shown in
  their place.
- What happens when the repository changes such that an entry point's call
  chain, or the entry point itself, no longer exists? The next regeneration
  must update or remove the affected sequence diagram(s) rather than leaving
  a stale one.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST identify every entry point in the analyzed
  repository, where an entry point is any of: a CLI command, an API route
  handler, or any other public function that is never called by another
  function in the analyzed repository (per the existing call edges in the
  dependency graph).
- **FR-002**: A symbol recognized as a CLI command or an API route handler
  MUST always be treated as an entry point regardless of whether other
  functions in the repository call it; the "never called by another
  function" condition applies only to the third category (plain public
  functions).
- **FR-003**: The system MUST generate one sequence diagram per identified
  entry point, showing the calls that entry point triggers in the actual
  order they occur, derived solely from the call edges already captured in
  the dependency graph — no new interactions may be inferred or invented
  beyond what those edges represent. Because the dependency graph records at
  most one call edge per (caller, callee) pair, repeated calls from the same
  caller to the same target are shown as a single step (see Clarifications),
  not one step per call site.
- **FR-004**: Each call step shown in a sequence diagram MUST be attributed
  to the correct originating module or class, as recorded in the dependency
  graph (or the best available identification when the target cannot be
  resolved — see Edge Cases).
- **FR-005**: Each sequence diagram MUST be bounded to a fixed maximum call
  depth measured from its entry point, so that a call chain containing
  recursion or a cycle still produces a finite, readable diagram instead of
  looping indefinitely.
- **FR-006**: An entry point that calls no other function MUST produce a
  minimal sequence diagram containing only that entry point, never a
  fabricated call or interaction.
- **FR-007**: The system MUST NOT generate a sequence diagram for a function
  that does not qualify as an entry point under FR-001/FR-002.
- **FR-008**: The system MUST render each sequence diagram using the same
  diagramming technology already used for the existing dependency and class
  diagrams, so it renders fully offline with no external network requests.
- **FR-009**: The system MUST wire each entry point's sequence diagram into
  that entry point's own page in the generated wiki.
- **FR-010**: The system MUST update or remove an entry point's sequence
  diagram when the wiki is regenerated after a repository change that
  affects that entry point or its call chain, consistent with the existing
  incremental regeneration behavior.

### Key Entities

- **EntryPoint**: Represents one identified entry point (a CLI command, an
  API route handler, or an uncalled public function) in the analyzed
  repository — the root from which one sequence diagram is generated.
- **SequenceDiagramSelection**: Represents one entry point's sequence
  diagram, composed of the ordered, depth-bounded sequence of call steps
  reachable from that entry point via existing call edges.
- **CallStep**: Represents one call shown within a sequence diagram — the
  calling symbol, the called symbol, its originating module/class, and its
  position in the call order. One CallStep exists per distinct (caller,
  callee) pair, not per call site (see Clarifications).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a test repository containing an entry point that calls two
  or more functions across multiple modules, the generated sequence diagram
  shows the calls in their real order, each with the correct
  originating module/class.
- **SC-002**: For any scanned repository, a developer opening an entry
  point's documentation page can see a sequence diagram of the calls it
  triggers without reading the source code or tracing the call chain by hand.
- **SC-003**: On a test repository containing an entry point whose call
  chain includes recursion or a cycle, the generated sequence diagram is
  still finite and fully renders, bounded at the fixed maximum depth.
- **SC-004**: On a test repository containing an entry point that calls
  nothing else, the generated sequence diagram shows only that entry point,
  with zero invented calls.
- **SC-005**: After a repository change that adds, removes, or alters an
  entry point's call chain, regenerating the wiki updates the affected
  sequence diagram(s) without requiring a full from-scratch reindex of the
  repository.
- **SC-006**: Every generated sequence diagram opens and remains fully
  usable when the generated wiki is opened directly from local files, with
  zero network requests to an external service.

## Assumptions

- This feature reuses the call edges already captured by the existing
  dependency graph; it does not introduce new source-level static analysis
  to discover calls beyond what that graph already records.
- The exact fixed maximum call depth is an implementation detail to be
  finalized during planning, not fixed by this spec.
- Each entry point's sequence diagram is shown on that entry point's own
  page in the generated wiki (one diagram per entry point), rather than
  collected onto a single shared page — consistent with how the existing
  per-module dependency diagram is scoped one-per-page rather than
  repository-wide.
- "Public function" follows this project's existing convention elsewhere in
  the pipeline: a function/method whose name does not start with an
  underscore.
- The diagram renders as Mermaid, consistent with the existing dependency
  and class diagrams, including the same offline-rendering and
  incremental-regeneration expectations already established for the wiki.
- Detecting which symbols are CLI commands vs. API route handlers vs. plain
  functions is an implementation detail (e.g. recognizing this project's own
  CLI/route registration patterns) to be finalized during planning, not
  fixed by this spec.
