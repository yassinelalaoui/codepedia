# Feature Specification: Diagrams Navigation Hub

**Feature Branch**: `024-diagrams-navigation-hub`

**Created**: 2026-08-18

**Status**: Draft

**Input**: User description: "Construire une section de navigation dédiée, accessible depuis n'importe quelle page
du wiki généré, qui liste exclusivement tous les diagrammes produits par l'outil — le diagramme
de classes (8.1), tous les diagrammes de séquence par point d'entrée (8.2), le diagramme de cas
d'utilisation (8.3), et l'ensemble des diagrammes de dépendances par module déjà existants — sans
mélanger cette liste avec les pages de documentation textuelle des modules. L'utilisateur doit pouvoir,
depuis n'importe quelle page du wiki, atteindre cette section en un clic, et depuis cette section ouvrir
n'importe quel diagramme du dépôt sans avoir à naviguer module par module. Cette section doit
rester à jour automatiquement après une ré-indexation incrémentale, au même titre que le reste du
wiki. Critère de succès : depuis n'importe quelle page du wiki généré, un clic sur l'onglet « Diagrammes
» affiche la liste complète et à jour de tous les diagrammes du dépôt, chacun ouvrable en un clic."

**Note**: This feature surfaces and links to diagrams already produced by
prior features — the repository class diagram (`021-repository-class-diagram`,
"8.1"), the per-entry-point sequence diagrams
(`022-entry-point-sequence-diagram`, "8.2"), the repository use-case diagram
(`023-repository-use-case-diagram`, "8.3"), and the existing per-module
dependency diagrams (`013-interactive-dependency-diagram`). It introduces no
new diagram type of its own — only a dedicated, always-reachable page that
aggregates links to every diagram the wiki already generates.

## Clarifications

### Session 2026-08-18

- Q: Should the diagrams navigation section be a persistent panel that opens in place on any page, or a dedicated page the user navigates to (like Home/Class Diagram/Use Case Diagram)? → A: A dedicated page. The nav bar present on every page gets a new "Diagrams" link that navigates to a new, separate page listing every diagram.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Find any diagram without navigating module by module (Priority: P1)

As a developer exploring a generated wiki, I want a single, dedicated page
that lists every diagram in the repository, reachable in one click from
wherever I am in the wiki, so that I can jump straight to any diagram — the
class diagram, any entry point's sequence diagram, the use-case diagram, or
any module's dependency diagram — without first finding and opening that
module's own documentation page.

**Why this priority**: This is the only user story in this feature; it
delivers the complete, standalone value of the feature by itself.

**Independent Test**: Open any page of a generated wiki for a repository
containing several modules, at least one class, and at least one identified
entry point (so every diagram category exists). From that page, open the
Diagrams page and confirm every diagram in the repository is listed there,
and that selecting any one of them opens it directly.

**Acceptance Scenarios**:

1. **Given** a generated wiki open on any page (the home page, a module page,
   or a diagram page itself), **When** the user clicks the "Diagrams" link in
   the wiki's persistent navigation, **Then** the user is taken to a
   dedicated page listing every diagram in the repository, without needing
   to return to the home page first.
2. **Given** the Diagrams page, **When** it is displayed, **Then** it
   contains exactly: the repository class diagram (if one exists), one entry
   per identified entry point's sequence diagram, the repository use-case
   diagram (if one exists), and one entry per module's dependency diagram —
   and no entry for any module's text-documentation page.
3. **Given** the Diagrams page, **When** the user selects any listed
   diagram, **Then** that diagram's own page opens directly, without
   navigating through any module's documentation page or any other
   intermediate page first.
4. **Given** a repository that has just been incrementally re-indexed after a
   change that added, removed, or altered a diagram (e.g., a new entry point
   was added, a class was removed), **When** the Diagrams page is next
   viewed, **Then** it reflects exactly the current set of diagrams, with no
   stale or missing entries.
5. **Given** a repository with no classes and no identifiable entry points
   (so neither the class diagram nor the use-case diagram exist), **When**
   the Diagrams page is displayed, **Then** it lists only the diagram
   categories that actually exist for that repository (e.g., only per-module
   dependency diagrams), with no broken or empty entries for the categories
   that don't.

---

### Edge Cases

- What happens when the analyzed repository produces zero diagrams of any
  kind? The Diagrams page still opens and shows an empty list, never a
  broken page.
- What happens on a repository with many modules and many entry points? The
  page must remain a single, flat, directly clickable list — the user must
  never be required to drill down module by module to find a specific
  diagram.
- What happens when a module (and therefore its dependency diagram) is
  removed from the repository? The next regeneration removes that entry from
  the page, consistent with how the diagram's own page is already removed.
- What happens when the Diagrams page is reached from a diagram page itself
  (e.g., a module's dependency diagram)? It still lists every diagram,
  including the one currently open.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a single, dedicated page that lists
  every diagram generated for the analyzed repository.
- **FR-002**: This page MUST be reachable via a link in a persistent
  navigation element present on every page of the generated wiki, with
  exactly one user action, regardless of which page the user is currently
  viewing.
- **FR-003**: This page MUST include: the repository class diagram (when
  one exists), every identified entry point's sequence diagram, the
  repository use-case diagram (when one exists), and every module's
  dependency diagram.
- **FR-004**: This page MUST NOT include any module's text-documentation
  page, or any page that is not itself a diagram.
- **FR-005**: Each listed diagram MUST be openable with exactly one further
  user action from within this page, without navigating through a module's
  documentation page or any other intermediate page first.
- **FR-006**: The system MUST omit a diagram category entirely, rather than
  show an empty or broken placeholder for it, when that category currently
  produces no pages for the analyzed repository (e.g., a repository with no
  classes has no class-diagram entry).
- **FR-007**: The system MUST keep this page's contents current
  automatically whenever the wiki is regenerated, including after an
  incremental re-index, consistent with the existing incremental
  regeneration behavior of the rest of the wiki.
- **FR-008**: Each entry on this page MUST clearly identify what diagram
  it links to (e.g., which module, which entry point, or that it is the
  repository-wide class/use-case diagram) so a user can choose the right one
  without opening it first.

### Key Entities

- **DiagramsIndexPage**: Represents the single, dedicated page listing every
  diagram in the repository, reachable via a link in the persistent
  navigation present on every other wiki page.
- **DiagramCatalogEntry**: Represents one diagram listed on the
  DiagramsIndexPage — what kind of diagram it is, what it is about (a
  module, an entry point, or the repository as a whole), and a way to open
  it directly.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From any page of the generated wiki, one click on the
  "Diagrams" link displays the complete, up-to-date list of every diagram in
  the repository, each openable with one further click.
- **SC-002**: A developer can reach any diagram in the repository from any
  starting page in at most two actions total (one to open the Diagrams page,
  one to open the diagram), regardless of how many modules or entry points
  the repository has.
- **SC-003**: After an incremental re-index that changes the repository's
  diagram set, the Diagrams page reflects the change without requiring a
  full from-scratch reindex of the repository.
- **SC-004**: The Diagrams page never lists a module's text-documentation
  page, and never omits a diagram that currently exists for the repository.

## Assumptions

- The "Diagrams" link is added to the persistent navigation element already
  present on every generated page (the existing top navigation, which today
  provides only a link back to the home page); it navigates to a new,
  dedicated page listing every diagram (Clarifications, 2026-08-18).
- This feature aggregates and links to diagrams already produced by
  `013-interactive-dependency-diagram` (per-module dependency diagrams),
  `021-repository-class-diagram`, `022-entry-point-sequence-diagram`, and
  `023-repository-use-case-diagram`; it does not change what any of those
  diagrams contain or how each is individually generated.
- Diagram categories not currently populated for a given repository (e.g.,
  no classes, no identifiable entry points) are simply absent from the
  page's list, not shown as empty/placeholder groups — consistent with how
  those diagrams' own pages already don't exist in that case.
- The internal ordering or grouping of entries within the page (e.g.,
  grouped by diagram type) is an implementation detail to be finalized
  during planning, not fixed by this spec.
