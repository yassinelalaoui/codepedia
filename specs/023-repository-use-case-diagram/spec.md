# Feature Specification: Repository Use Case Diagram

**Feature Branch**: `023-repository-use-case-diagram`

**Created**: 2026-08-18

**Status**: Draft

**Input**: User description: "Construire la génération d'un diagramme de cas d'utilisation unique, à l'échelle
du dépôt, montrant les acteurs externes et les capacités (cas d'usage) du dépôt analysé auxquelles
ils accèdent, à partir des mêmes points d'entrée identiés en 8.2. L'acteur associé à chaque point
d'entrée doit être déduit de la façon dont il est exposé : un acteur distinct pour les commandes CLI,
un acteur distinct pour les routes d'API HTTP, avec repli sur un acteur générique unique lorsque
cette distinction n'est pas détectable. Chaque point d'entrée apparaît comme son propre cas d'usage
relié à son acteur. Aucun diagramme ne doit être généré si le dépôt n'expose aucun point d'entrée
externe identiable (ex. bibliothèque interne pure). Critère de succès : sur un dépôt de test exposant
au moins une commande CLI et une route API, le diagramme montre un acteur distinct pour chacune,
chacun relié à ses cas d'usage respectifs"

**Note**: This feature was promised as a follow-up when
`021-repository-class-diagram` was split out of the originally broader "wiki
diagram types" feature ("The sequence-diagram and use-case-diagram
capabilities that were previously bundled with this one will be specified
separately"). The sequence-diagram capability was covered by
`022-entry-point-sequence-diagram`, which also introduced the entry-point
identification (CLI command / API route handler / uncalled public function)
this spec's diagram is built from ("les mêmes points d'entrée identifiés en
8.2" refers to that same identification). This spec covers only the
use-case-diagram capability, the last of the three originally bundled
diagram types.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View the repository's use-case diagram (Priority: P1)

As a developer or stakeholder orienting myself in an unfamiliar repository, I
want to see a single diagram of the external actors that can interact with
the system and the capabilities (use cases) each actor can access, so that I
can understand who or what uses this system and how, without tracing every
entry point by hand through the source.

**Why this priority**: This is the only user story in this feature; it
delivers the complete, standalone value of the feature by itself.

**Independent Test**: Run the tool against a repository exposing at least one
CLI command and one API route handler. Open the wiki's overview page and
confirm a single use-case diagram is present showing a distinct actor for
the CLI command and a distinct actor for the API route, each connected to
its own use case, matching the actual source.

**Acceptance Scenarios**:

1. **Given** a repository exposing a CLI command and an API route handler,
   **When** the wiki is generated, **Then** the use-case diagram shows two
   distinct actors — one for the CLI command, one for the API route — each
   connected to its own use case.
2. **Given** a repository exposing a plain public function entry point that
   is neither a CLI command nor an API route handler, **When** the use-case
   diagram is generated, **Then** that entry point's use case is connected to
   a single generic fallback actor instead of a CLI- or API-specific one.
3. **Given** a repository exposing multiple entry points of the same kind
   (e.g. several CLI commands), **When** the use-case diagram is generated,
   **Then** each entry point appears as its own separate use case, and all of
   them connect to the one shared actor for that kind.
4. **Given** a repository that exposes no identifiable entry point at all
   (e.g. a pure internal library), **When** the wiki is generated, **Then**
   no use-case diagram is generated or shown.
5. **Given** a repository exposing entry points of a detectable kind (CLI or
   API) alongside entry points whose exposure kind cannot be determined,
   **When** the use-case diagram is generated, **Then** the detectable ones
   connect to their specific actor and the rest connect to the single generic
   fallback actor.

---

### Edge Cases

- What happens when a repository exposes entry points of only one kind (e.g.
  only CLI commands)? Only that one actor appears on the diagram — no empty
  or unused actors for kinds that have no entry points.
- What happens when the repository changes such that an entry point is
  added, removed, or reclassified (e.g. a plain function becomes a CLI
  command)? The next regeneration must update the diagram — actors and use
  cases — rather than leaving it stale.
- What happens when a repository has entry points but none of a detectable
  kind (i.e. every entry point falls back to the generic actor)? The diagram
  still generates normally, showing every entry point as a use case
  connected to the single generic actor.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST generate a single, repository-wide use-case
  diagram derived from the same entry points identified for the sequence-
  diagram feature (a CLI command, an API route handler, or any other public
  function never called by another function in the analyzed repository).
- **FR-002**: Each identified entry point MUST appear on the diagram as its
  own use case.
- **FR-003**: The actor connected to each entry point's use case MUST be
  derived from how that entry point is exposed: every CLI-command entry
  point connects to one shared "CLI" actor, and every API-route entry point
  connects to one shared "API" actor, each distinct from the other.
- **FR-004**: An entry point whose exposure kind cannot be determined as a
  CLI command or an API route handler (i.e. a plain public function) MUST
  connect to a single shared generic actor, distinct from the CLI and API
  actors.
- **FR-005**: The system MUST NOT generate a use-case diagram when the
  analyzed repository exposes zero identifiable entry points.
- **FR-006**: The system MUST render the use-case diagram using the same
  diagramming technology already used for the existing dependency, class,
  and sequence diagrams, so it renders fully offline with no external
  network requests.
- **FR-007**: The system MUST wire the use-case diagram into the wiki's
  existing overview page.
- **FR-008**: The system MUST update or remove the use-case diagram when the
  wiki is regenerated after a repository change that adds, removes, or
  reclassifies an entry point, consistent with the existing incremental
  regeneration behavior.

### Key Entities

- **Actor**: Represents one of the (at most three) external actor
  categories that can access the repository's capabilities — CLI, API, or
  the single generic fallback — shared by every entry point of that kind.
- **UseCase**: Represents one identified entry point's capability, shown as
  its own use case connected to its actor.
- **UseCaseDiagramView**: Represents the single, repository-wide use-case
  diagram, composed of the actors, their use cases, and the associations
  between them. (The implementation plan realizes this as a plain selection
  — see `data-model.md`'s `UseCaseDiagramSelection` — separate from its
  rendering to diagram text, mirroring `021-repository-class-diagram`'s
  `ClassDiagramView`/`ClassDiagramSelection` split.)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a test repository exposing at least one CLI command and one
  API route, the generated diagram shows a distinct actor for each, each
  connected to its respective use case(s).
- **SC-002**: For any scanned repository exposing at least one entry point, a
  developer opening the wiki's overview page can see which external actors
  can access the system and what each can do, without reading the source
  code.
- **SC-003**: On a test repository exposing zero identifiable entry points,
  no broken or empty use-case diagram is shown.
- **SC-004**: The use-case diagram opens and remains fully usable when the
  generated wiki is opened directly from local files, with zero network
  requests to an external service.
- **SC-005**: After a repository change that adds, removes, or reclassifies
  an entry point, regenerating the wiki updates the use-case diagram without
  requiring a full from-scratch reindex of the repository.

## Assumptions

- This feature reuses the entry-point identification (CLI command / API
  route handler / uncalled public function) already established by
  `022-entry-point-sequence-diagram`; it does not introduce new detection
  logic beyond what that feature already captures.
- There are exactly three possible actor categories — CLI, API, and one
  generic fallback for entry points whose kind cannot be determined — with
  one shared actor instance per category, not one actor per individual
  entry point, consistent with standard use-case-diagram convention.
- The use-case diagram is a single, repository-wide page reachable from the
  wiki's overview page, rather than one per module or per entry point —
  consistent with how `021-repository-class-diagram` is scoped as one
  repository-wide page rather than per-module.
- The diagram renders using the same diagramming technology already used for
  the existing dependency, class, and sequence diagrams, including the same
  offline-rendering and incremental-regeneration expectations already
  established for the wiki. The exact diagram syntax is an implementation
  detail to be finalized during planning, not fixed by this spec.
