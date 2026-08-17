# Feature Specification: Repository Class Diagram

**Feature Branch**: `021-repository-class-diagram`

**Created**: 2026-08-17

**Status**: Draft

**Input**: User description: "Construire la génération d'un diagramme de classes unique, à l'échelle du dépôt entier, à partir de l'inventaire de symboles déjà produit par l'extracteur AST (partie 1.3). Le diagramme doit montrer, pour chaque classe structurellement significative, son nom, ses méthodes, et ses relations d'héritage avec les autres classes retenues, y compris lorsque la classe parente est définie dans un autre module. L'extracteur actuel ne capture que les méthodes des classes, pas leurs attributs/champs : le diagramme ne doit donc afficher ni attributs ni relations de composition tant que cette donnée n'existe pas dans le pipeline — ce n'est pas un manque à combler ici, c'est une limite assumée de cette fonctionnalité. Le nombre de classes incluses doit être plafonné à un maximum fixe, en priorisant les classes impliquées dans une relation d'héritage puis celles avec le plus de dépendances entrantes/sortantes dans le graphe existant, pour rester lisible sur un gros dépôt. Aucun diagramme ne doit être généré si le dépôt ne contient aucune classe. Critère de succès : sur un dépôt de test contenant plusieurs classes réparties sur plusieurs modules, dont au moins une relation d'héritage inter-module, le diagramme généré montre les classes principales, leurs méthodes, et la relation d'héritage, correctement."

**Note**: This feature was split out of the originally broader "wiki diagram
types" feature (formerly numbered 021, now covering only this scope) so each
new diagram type ships as its own independently plannable, testable
capability, matching how every other feature in this repository is scoped.
The sequence-diagram and use-case-diagram capabilities that were previously
bundled with this one will be specified separately.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View the repository's class diagram (Priority: P1)

As a developer orienting myself in an unfamiliar repository, I want to see a
single, simplified class diagram of the repository's major classes, their
methods, and how they relate to each other through inheritance, so that I
can understand the system's structure without reading the raw source or
having to piece it together from many per-module diagrams.

**Why this priority**: This is the only user story in this feature; it
delivers the complete, standalone value of the feature by itself.

**Independent Test**: Run the tool against a repository containing several
classes across multiple modules, including at least one inheritance
relationship where the parent class is defined in a different module. Open
the wiki's overview page and confirm a single class diagram is present
showing the repository's structurally significant classes, their methods,
and the relationship, matching the actual source.

**Acceptance Scenarios**:

1. **Given** a repository containing classes across multiple modules,
   **When** the wiki is generated, **Then** the overview page shows one
   class diagram listing the repository's major classes, each with its name
   and methods.
2. **Given** a class that inherits from another class defined in a different
   module, **When** the class diagram is opened, **Then** the inheritance
   relationship is visually shown between the two classes regardless of
   which modules they live in.
3. **Given** a repository containing far more classes than can legibly fit
   on one diagram, **When** the class diagram is generated, **Then** it
   includes only the structurally major classes rather than every class in
   the repository.
4. **Given** a repository containing no classes at all, **When** the wiki is
   generated, **Then** no broken or empty class diagram is shown.

---

### Edge Cases

- What happens when two included classes are defined in different modules
  and relate to each other through inheritance? The relationship must still
  be shown on the single class diagram regardless of which modules the
  classes come from.
- What happens when a class has no methods at all? It must still be shown
  on the diagram (if selected for inclusion) as a class with an empty
  method list, not omitted or shown as broken.
- What happens when the repository changes such that a class or inheritance
  relationship shown in a previously generated diagram no longer exists?
  The next regeneration must update the diagram rather than leaving it
  stale or broken.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST generate a single, repository-wide class
  diagram showing each included class's name and methods, derived from the
  existing symbol inventory.
- **FR-002**: The system MUST show inheritance relationships between classes
  in the class diagram, including when the related class is defined in a
  different module.
- **FR-003**: The system MUST NOT display attributes/fields or
  composition/aggregation relationships on the class diagram, because the
  existing symbol inventory does not capture class attribute data. This is
  an accepted limitation of this feature, not a gap to close as part of it.
- **FR-004**: The system MUST NOT display the class diagram when the
  repository contains no classes.
- **FR-005**: The system MUST select which classes are "major" enough to
  include in the class diagram using a structural-significance heuristic
  rather than including every class, so the diagram stays legible on large
  repositories: a class qualifies first if it participates in an
  inheritance relationship, and remaining inclusion slots are filled by the
  classes with the most incoming and outgoing dependency-graph edges. The
  number of included classes MUST be capped at a fixed maximum.
- **FR-006**: The system MUST render the class diagram using the same
  diagramming technology already used for the existing per-module
  dependency diagram, so it renders fully offline with no external network
  requests.
- **FR-007**: The system MUST wire the class diagram into the wiki's
  existing overview page.
- **FR-008**: The system MUST update or remove the class diagram when the
  wiki is regenerated after a repository change, consistent with the
  existing incremental regeneration behavior.

### Key Entities

- **ClassDiagramView**: Represents the single, repository-wide class
  diagram, composed of the major classes selected for inclusion and the
  inheritance relationships between them. (The implementation plan realizes
  this as two stages — a plain selection, then its rendering to diagram
  text — see `data-model.md`'s `ClassDiagramSelection` and
  `ClassDiagramSource`.)
- **ClassMethod**: Represents one method shown on a class within the class
  diagram. (Realized as `data-model.md`'s `SelectedMethod`.)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any scanned repository containing at least one class, a
  developer opening the wiki's overview page can see one class diagram
  covering the repository's structurally major classes, their methods, and
  inheritance relationships, without reading the source code.
- **SC-002**: On a test repository containing several classes spread across
  multiple modules, including at least one cross-module inheritance
  relationship, the generated diagram correctly shows the major classes,
  their methods, and that inheritance relationship.
- **SC-003**: After a repository change that adds, removes, or renames a
  class or an inheritance relationship, regenerating the wiki updates the
  class diagram without requiring a full from-scratch reindex of the
  repository.
- **SC-004**: The class diagram opens and remains fully usable when the
  generated wiki is opened directly from local files, with zero network
  requests to an external service.

## Assumptions

- This feature extends the existing symbol inventory (AST extractor) and
  dependency graph; it does not introduce new source-level static analysis
  beyond what those already capture. In particular, it does not add class
  attribute/field extraction — see FR-003.
- The class diagram is a single, repository-wide page reachable from the
  wiki's overview page, rather than one per module.
- The "major class" cap and exact ranking weights beyond the
  inheritance-first priority in FR-005 are an implementation detail to be
  finalized during planning, not fixed by this spec.
- The diagram renders as Mermaid, consistent with the existing dependency
  diagram, including the same offline-rendering and incremental-regeneration
  expectations already established for the wiki.
