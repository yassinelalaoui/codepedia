# Feature Specification: Feature Grouping That Follows the Code

**Feature Branch**: none. The work stays on `main` (owner rule). Spec directory: `specs/039-feature-grouping`.

**Created**: 2026-09-15

**Status**: Draft

**Input**: User description: "Make the wiki's feature (subsystem) grouping from spec 033 follow the code, beyond Python, so the Overview (spec 038) and the sidebar describe real parts of the system. Scope: coupling beyond Python (US1), tests never seeding or claiming production code (US2), a feature anchored at its seed (US3), representative planner input (US4). Keep 033's guarantees. Out of scope: Java annotation parsing, calls through interfaces, 038's narrative prompt."

## Clarifications

### Session 2026-09-15

- Q: Where are test files placed (FR-009)? → A: With the feature holding most
  of the production code they exercise. A test exercising none is placed by
  its directory. Tests are placed after production modules, so they never move
  one.
- Q: Which languages must have their in-repository imports recognised? → A:
  Java and JavaScript/TypeScript, with Python unchanged. Go and Rust keep
  today's behaviour, falling back to directory grouping and never to a
  catch-all group, and are left for follow-up work.
- Q: Should modules holding commands, HTTP routes or `main` stay parts of
  their own rather than fold into larger groups? → A: Yes. Such an entry
  module is never folded into a group without entry modules. It may combine
  only with other entry modules it is coupled to or shares a directory with.
- Q: Should recorded function calls between modules count as coupling, or
  only imports? → A: Imports only. Modules that use each other without an
  import, such as Java classes in one package, are brought together by
  directory (FR-006).
- Q: May a feature the model builds by combining groups exceed the 30%
  ceiling? → A: Yes. The ceiling applies to the grouping, which uses no
  model. The model's merges stay allowed (033 FR-010), and the largest
  feature's share with a model is reported in verification rather than
  enforced.
- Q: When a feature holds an entry module and an ordinary seed with more
  uncalled functions, which is its anchor? → A: The entry module. Among entry
  modules, the one with the most entry points wins. A feature with no entry
  module falls back to its seed with the most entry points, then to 033's
  most-connected rule.

## Background

Spec 033 groups a repository's modules into features: the sidebar's entries,
the Overview's subsystems table and the subjects of the Overview's
per-subsystem paragraphs (spec 038). The grouping is decided with no model:
seed one group per entry-point module, attach modules by how strongly they are
coupled to a seed, fold groups that are too small, and group whatever is left
by directory. One model call then only names and combines the groups.

Read-only measurements on the two reference repositories (2026-09-15) show the
grouping, not the naming, is what misleads readers:

- **Coupling exists for Python only.** On `nextgen-wealth-ledger` (a Java
  backend and a TypeScript frontend, 109 modules), 56 of 64 Java files and 37
  of 43 TypeScript files have parsed imports, yet 0 Java and 2 TypeScript
  modules are coupled to anything. The dependency graph records each such
  import by name (a package-qualified type, or a relative file path), but
  with no source file, so the grouping cannot map it to the module it names.
- **Uncoupled modules collapse into one group.** With no coupling, all 60 of
  that repository's seeds stayed single-module groups and were folded away. A
  group coupled to nothing goes to the largest surviving group, so one feature,
  "Data Transfer Objects", holds 93 of 109 modules. The folds also discarded
  the entry-point counts: every feature there shows 0 entry points.
- **Tests seed groups and claim production code.** On `codepedia-sample-repo`
  (Python, 51 modules), 26 modules are seeds, 5 of them test files. A test
  seeded "Tests (Test Fines)" and pulled the fine calculator into it. The CLI
  module, with 7 commands, was folded into a group seeded by a data-seeding
  script and titled "Scripts".
- **A feature's anchor is its best-connected member, not its seed.** The
  anchor is the feature's page address and the module the Overview names as
  where to start. "Services (Lending Service)" starts at the identifier
  helper, "Services (Catalog Service)" at the errors module, and the
  93-module group at an animations file.
- **The model sees the least telling members.** Each group is described by its
  first three members in alphabetical order. The sample's 12-module API group
  was shown as `README`, `__init__` and `__init__`.

Stranger tests on the Overview (spec 038, research Decisions 18 and 19) found
readers learned the architecture from module names and called the subsystems
table and paragraphs misleading, for these reasons.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Parts of the system are grouped by how their code connects, in Java and JavaScript/TypeScript too (Priority: P1)

A developer opens the wiki of a repository written in Java and TypeScript. The
sidebar and the Overview's subsystems table show parts they recognise:
controllers with the services they call, security, the frontend's features.
Today they see one group holding almost the whole repository, beside a few
directory-named fragments.

**Why this priority**: Without coupling there is no grouping for these
languages, only directory fallback plus one catch-all bucket. Every later
improvement, and every Overview paragraph, depends on the groups being real.

**Independent Test**: Regenerate `nextgen-wealth-ledger` with no model.
Confirm that modules importing one another are grouped together, that no
feature holds most of the repository, and that each feature's entry-point
count is the sum over its modules.

**Acceptance Scenarios**:

1. **Given** a module importing another module of the same repository by its
   package-qualified name, **When** features are derived, **Then** the two are
   recorded as coupled.
2. **Given** a module importing a whole package with a wildcard, **When**
   features are derived, **Then** it is coupled to that package's modules, and
   no more strongly to each of them than a direct import of one module would
   couple it.
3. **Given** a module importing another by relative path, including a
   directory's index file, **When** features are derived, **Then** the two are
   recorded as coupled.
4. **Given** an import naming nothing inside the repository (standard library,
   third-party package, unresolvable alias), **When** features are derived,
   **Then** it adds no coupling and is attributed to no repository module.
5. **Given** a group too small to stand alone that is coupled to no surviving
   group, **When** groups are folded, **Then** it joins the group holding the
   most modules from its own directory or the nearest directory above it. It
   never joins the largest group merely for being largest.
6. **Given** any folding, **When** a feature's entry-point count is shown,
   **Then** it counts every non-test entry point of every module the feature
   holds.
7. **Given** a Python-only repository, **When** features are derived, **Then**
   its module coupling is the same as before this feature.
8. **Given** a one-file module holding commands, such as a CLI whose every
   dependency is itself a seed, **When** groups are folded, **Then** it is not
   absorbed into a group without commands, routes or `main`. It joins the
   group holding commands, routes or `main` that it is most coupled to, or
   failing that one found by the directory rule, and otherwise stays a part
   of its own (FR-006a).
9. **Given** two groups of two or more modules, each holding routes, in the
   same directory, **When** groups are folded, **Then** they stay two parts
   (FR-006a).

---

### User Story 2 - Tests follow the code they test instead of claiming it (Priority: P1)

A reader looking for the fine calculation finds it among the services, with
its test beside it or among the tests. It is not filed under a feature named
after the test. The CLI appears as a part of its own rather than inside a
group named after a script.

**Why this priority**: Test files are the most coupled modules in any
repository, because a test imports what it tests. Letting them seed groups
lets them decide where production code is shown, which is how "Tests (Test
Fines)" and "Scripts" came about.

**Independent Test**: Regenerate `codepedia-sample-repo` with no model.
Confirm no group is seeded by a test file, no production module sits in a
group only because a test reaches it, and each test file sits in the feature
holding most of the code it exercises.

**Acceptance Scenarios**:

1. **Given** a test file with test functions nothing calls, **When** seeds are
   chosen, **Then** it is not a seed.
2. **Given** a production module whose strongest coupling is to its test,
   **When** features are derived, **Then** it is grouped by its coupling to
   other production code and by its directory, never by the test.
3. **Given** a test file exercising production modules, **When** features are
   derived, **Then** it joins the feature holding most of them, and belongs to
   exactly one feature.
4. **Given** a test file exercising no production module (shared fixtures),
   **When** features are derived, **Then** it is placed by its directory, like
   any other uncoupled module.

---

### User Story 3 - A subsystem starts where its work starts (Priority: P2)

The Overview says where to start reading "Lending Service": `lending_service`,
the module whose functions are called from outside it, not the identifier
helper that happens to be best connected inside the group. The subsystem's
page address is the same module.

**Why this priority**: The anchor is both the address and the "start here"
module. When it is a helper, every sentence the Overview writes about the
subsystem describes the helper.

**Independent Test**: Regenerate both reference repositories. Confirm that
every feature holding an entry module is anchored at one, that every other
feature holding a seed is anchored at a seed, and that every address the
previous run published still resolves.

**Acceptance Scenarios**:

1. **Given** a feature holding one or more seed modules, **When** its anchor is
   chosen, **Then** it is an entry module (commands, routes or `main`) if the
   feature holds one. Otherwise it is the seed with the most non-test entry
   points. Ties are resolved identically on every run.
2. **Given** a feature holding no seed (a directory group), **When** its anchor
   is chosen, **Then** 033's rule applies unchanged: its most internally
   connected member.
3. **Given** an anchor that moved because of this feature, **When** a reader
   follows an address the previous run published, **Then** it leads to the
   feature now holding that page's modules.

---

### User Story 4 - The planner is shown what a group actually is (Priority: P3)

When a model names the groups, it sees each group's seed and its most
important members, labelled so that same-named modules differ, plus the
README's own opening description. Titles and descriptions then name what the
code does, not the first files alphabetically.

**Why this priority**: Names matter less than membership, and US1–US3 change
membership. Once groups are right, better input is the cheapest way to better
names. It costs no extra model call.

**Independent Test**: Build the planning input for both reference
repositories and confirm each group is described by its seed first, then its
members by entry points and coupling, never alphabetically, and that the
repository description is the README's opening paragraph.

**Acceptance Scenarios**:

1. **Given** a group with a seed, **When** the planning input is built,
   **Then** the seed is the first member described.
2. **Given** a group with more members than are described, **When** the input
   is built, **Then** the members shown are those with the most entry points,
   then the most coupling within the group, with ties resolved identically on
   every run.
3. **Given** two members sharing a name, **When** they are described, **Then**
   their labels differ.
4. **Given** a README with a title, badges and headings before its first prose
   paragraph, **When** the input is built, **Then** the repository description
   is that paragraph, bounded as today.

---

### Edge Cases

- **Nothing resolves.** A repository whose imports resolve to nothing, such as
  single-file scripts, falls back to directory grouping, as 033 does today, and
  still produces no catch-all group.
- **Coupling without imports.** In some languages, modules of one package use
  each other without importing. They are placed together by their shared
  directory. Calls are not used (FR-004).
- **Very large wildcard imports.** A wildcard import of a large package must
  not outweigh a direct import (US1 scenario 2), or one `import dtos.*` would
  bind a controller to every data class.
- **Unconnected halves.** A frontend and a backend that talk only over the
  network share no imports. They must end up in different features, and
  folding must never merge them for lack of a better target. That is why the
  directory rule never climbs from a subdirectory into the repository root
  (FR-006).
- **Tests only.** A repository whose only entry points are in test files, such
  as a library with a test suite, has no seeds and is grouped by directory.
- **Tests across features.** A test exercising code in several features joins
  the one holding most of that code. A tie is resolved identically on every
  run (FR-009).
- **Seed removed.** When an incremental update removes a feature's seed, the
  feature re-anchors and the previous address is aliased (033 FR-020).
- **First run after upgrading.** The grouping of an existing wiki changes. The
  plan cached for the old groups must not be applied to the new ones (FR-018),
  and every previously published address must keep resolving.
- **Test-like names.** A production file whose name merely resembles a test
  (`contest.py`) is not a test file. Recognition follows the same conventions
  spec 038 uses.

## Requirements *(mandatory)*

### Functional Requirements

#### Coupling (User Story 1)

- **FR-001**: Module coupling MUST include every import that names another
  module of the analysed repository, in Java and in JavaScript/TypeScript as
  well as in Python: an import of a package-qualified type, a wildcard import
  of a package, and an import by relative path, including a directory's index
  file. Go and Rust imports are out of scope. Modules in those languages are
  grouped by directory (FR-006) and never by falling into a catch-all group.
- **FR-002**: An import that names no module of the analysed repository MUST
  add no coupling and MUST NOT be attributed to an unrelated module. 033's
  protection against shared standard-library imports inflating one module's
  coupling MUST still hold.
- **FR-003**: A wildcard import MUST couple its module to the imported
  package's modules no more strongly, in total, than a direct import of one
  module would.
- **FR-004**: Coupling MUST come from imports only. Recorded calls MUST NOT
  add coupling. Modules that use one another without an import, such as Java
  classes in one package, are placed together through their shared directory
  (FR-006).
- **FR-005**: For a Python-only repository, module coupling MUST be unchanged
  by FR-001 to FR-004.

#### Folding and counts (User Story 1)

- **FR-006**: A group too small to stand alone, or beyond the cap on groups,
  MUST fold into the surviving group it is most coupled to (033 FR-007). A
  group coupled to no surviving group MUST fold into the surviving group
  holding the most modules directly in its own directory, or failing that
  directly in the nearest directory above it. A directory counts only the
  modules directly in it, never its whole subtree. The walk MUST NOT climb
  from a subdirectory into the repository root: a group whose own directory
  is the root is placed by the root's modules, but a group in a subdirectory
  stops at its top-level directory.
  Groups still unplaced that share a directory MUST combine into one group
  for that directory. Only what remains alone after that may go to 033's
  explicit terminal feature, and there MUST be at most one terminal feature.
  No group may be placed in another chosen only for being the largest. When
  no group can stand alone (none is large enough and none holds an entry
  module), nothing is folded and the groups stay as they are, as in 033:
  there is nothing to fold into (owner decision, 2026-09-15).
- **FR-006a**: An **entry module**, a non-test module holding at least one
  command, HTTP route or program `main` (the entry kinds spec 038
  recognises), MUST NOT be folded into a group that holds no entry module,
  whatever its size. An **entry group**, a group holding an entry module, that
  is too small to stand alone MUST join the entry group it is most coupled
  to, or failing that the entry group found by FR-006's directory rule.
  Otherwise it stays a group of its own, at any size. Entry groups large
  enough to stand alone MUST NOT combine with one another, except under the
  cap on groups. The cap MUST fold other groups first. If entry groups alone
  exceed it, the smallest combine by the same coupling-then-directory rule;
  one with neither joins the entry group whose directory shares the longest
  leading path with its own. Ties are resolved identically on every run.
- **FR-007**: A feature's entry-point count MUST equal the number of non-test
  entry points across all the modules it holds, however those modules arrived
  in it.

#### Tests (User Story 2)

- **FR-008**: A test file MUST NOT seed a group, and MUST NOT cause a
  production module to join a group. A production module's group is decided
  by its coupling to other production modules and by structure alone. Test
  files are recognised by the directory and file-name conventions spec 038
  already uses for entry points.
- **FR-009**: A test file MUST be placed in the feature holding most of the
  production modules it exercises, with ties resolved identically on every run.
  A test file that exercises no production module, such as a fixtures-only
  file, MUST be placed by FR-006's directory rule, counting production modules
  only. Test files still unplaced after that, and sharing a directory, MUST
  combine into one group for that directory. What remains alone goes to the
  terminal feature. Each test file belongs to exactly one feature. Placing
  tests MUST happen after production modules are grouped, so it never changes
  where a production module goes (owner decision, 2026-09-15).

#### Anchors (User Story 3)

- **FR-010**: A feature's anchor MUST be chosen in this order, with ties
  resolved identically on every run. A tie on entry points goes to the module
  whose entry points reach the most modules, then to the module name (owner
  decision, 2026-09-15):
  1. its entry module (FR-006a) with the most entry points;
  2. if it holds no entry module, its seed with the most non-test entry
     points;
  3. if it holds no seed, 033's rule: its most internally connected member,
     among its non-test members when it has any, so a test file never becomes
     a page address (owner decision, 2026-09-15).

  A feature no model named is titled after its anchor, the way 033 titled it
  after its seed: the anchor's directory and name. The title without a model
  then names the module the feature starts at. Groups formed by directory keep
  their directory title (owner decision, 2026-09-15).
- **FR-011**: Every feature page address published before this feature MUST
  keep resolving after it, through 033's alias mechanism (033 FR-020 and
  FR-021). No new mechanism is added for this.

#### Planning input (User Story 4)

- **FR-012**: Each group's members described to the model MUST be chosen and
  ordered by relevance: its seed first, then members by number of non-test
  entry points, then by coupling within the group, with a deterministic
  tie-break, and test files after every other member (owner decision,
  2026-09-15). They MUST NOT be chosen alphabetically.
- **FR-013**: Members described to the model MUST carry labels that tell
  same-named modules apart.
- **FR-014**: The repository description given to the model MUST be the
  README's opening prose paragraph, not its headings or list items, bounded
  by a named constant.
- **FR-015**: The planning call's worst-case size MUST remain bounded by named
  constants and verified against the provider budget, as 033 FR-012 and SC-005
  require.

#### Preservation

- **FR-016**: Every guarantee of spec 033 except those this spec replaces
  (FR-006 and FR-006a refine 033 FR-007; FR-008 narrows 033 FR-005; FR-010
  refines 033 FR-018) MUST still hold:
  - no model call in grouping;
  - every module in exactly one feature;
  - deterministic features and addresses for an unchanged repository;
  - the same modules and candidate grouping with and without a model;
  - at most one planning call per repository grouping (FR-018);
  - a titles-only degradation when the model fails.
- **FR-017**: Grouping MUST remain computable and testable with no model
  available, and the no-model path MUST be asserted by a test.
- **FR-018**: A cached plan MUST be reused only for the exact grouping it was
  made for. When the grouping of an unchanged repository changes, including
  on the first run after this feature ships, the old answer MUST NOT be
  applied to the new groups. That costs at most one new planning call.
- **FR-019**: Incremental regeneration MUST be preserved (033 FR-029). The
  first run after upgrading may regenerate every page once.
- **FR-020**: No new storage technology, network service or dependency may be
  introduced, and the analysed repository stays read-only.

### Key Entities

- **Coupling**: an undirected, weighted relation between two modules of the
  analysed repository, from imports that name repository modules, and from
  nothing else (FR-004). It decides which seed a module joins and where a
  folded group goes.
- **Seed**: a non-test module holding at least one entry point. It starts one
  group. In a feature with no entry module, the seed with the most entry
  points is the anchor.
- **Entry module**: a seed whose entry points include a command, an HTTP route
  or a program `main`. It is never absorbed into a group without entry modules
  (FR-006a), and it is preferred as anchor (FR-010).
- **Candidate group**: as in 033, a provisional, indivisible set of modules.
  Every module belongs to exactly one.
- **Test file**: a module recognised as a test by directory or file-name
  convention. It never seeds and never pulls production code in. It joins the
  feature holding most of the code it exercises, or its directory's group when
  it exercises none.
- **Anchor**: the module a feature is addressed by and presented as starting
  from.
- **Planning input**: the bounded description of every group given to the one
  model call: seed first, relevant members, distinguishable labels, and the
  README's opening paragraph.

## Success Criteria *(mandatory)*

### Measurable Outcomes

Measured on the two reference repositories, `codepedia-sample-repo` and
`nextgen-wealth-ledger`.

- **SC-001**: With no model, no feature holds more than 30% of a repository's
  modules. Today one `nextgen-wealth-ledger` feature holds 85%. With a model,
  whose merges of whole groups stay allowed (033 FR-010), the largest
  feature's share is recorded in verification, not enforced.
- **SC-002**: At least 90% of the Java and JavaScript/TypeScript imports that
  name another module of the same repository are recognised as coupling,
  counted per import, per language. An import names a repository module when
  it is a relative JavaScript/TypeScript path, or a Java name whose package
  is the dotted form of a directory holding the repository's Java files.
  Today, on `nextgen-wealth-ledger`, 0 of 64 Java modules and 2 of 43
  TypeScript modules are coupled to anything.
- **SC-003**: No group is seeded by a test file, and no production module
  shares a feature with a test only because the test reaches it. Today 5
  seeds on the sample are test files.
- **SC-004**: The entry-point counts of all features add up to the repository's
  non-test entry points. Today every `nextgen-wealth-ledger` feature shows 0.
- **SC-005**: Every feature holding an entry module is anchored at one, and
  every other feature holding a seed is anchored at a seed.
  On the sample, the lending, catalog and CLI-bearing features start at
  `lending_service`, `catalog_service` and `cli` (or a route module), not at
  `ids`, `errors` or `member`.
- **SC-006**: Mapped against spec 038's answer keys, which were written from
  the code, at least 6 of the sample's 8 key subsystems and at least 6 of
  `nextgen-wealth-ledger`'s 9 each correspond to one feature, meaning a
  feature most of whose production modules belong to that subsystem. The
  sample's CLI, and `nextgen-wealth-ledger`'s wallets, authentication and
  security, chatbot and frontend parts, are among them. Controllers are not
  expected as a feature of their own: each joins the service and data classes
  it uses (research Decision 12).
- **SC-007**: In a repeat of spec 038's stranger test (a fresh reviewer per
  repository, given only the Overview page), each reviewer names at least
  three key subsystems from the table or prose, not only from module names,
  and flags at most one subsystem as mislabelled or misplaced. Today the
  sample reviewer flags about six.
- **SC-008**: Spec 033's outcomes still hold:
  - 100% of modules are in exactly one feature;
  - at most one planning call per grouping, and zero for an unchanged rerun;
  - 100% of previously published addresses still resolve after regrouping;
  - an ordinary one-module edit regenerates a small number of pages;
  - the planning call's worst case stays within the provider budget.

## Assumptions

- **Entry points are not changed here.** Spring controllers are found as
  uncalled public methods, as today. Recording annotations, and resolving
  calls through interfaces, are separate work. An uncalled public function
  outside a test file still makes its module a seed. It does not make its
  module an entry module (FR-006a). So on `nextgen-wealth-ledger`, the Spring
  controllers are ordinary seeds, and only `DigitalBankingApplication` is an
  entry module. SC-006's controllers must emerge through coupling (US1).
- **Test recognition** reuses spec 038's conventions: `test`, `tests` and
  `__tests__` directories, and the usual per-language test file names.
- **The kind vocabulary, sidebar order and repair rules** of 033 are
  unchanged. So is the model's role, which is to name and combine whole
  groups, never split them.
- **Summary quality is out of scope.** Members are described with their
  existing docstrings or summaries, capped as today.
- **Spec 038's narrative prompt is not changed.** Its evidence reads the new
  features, so each Overview is re-narrated once after regrouping. That is
  one model call per repository, the same cost as any prompt change.
- **The 30% ceiling** (SC-001) is set from the reference repositories: the
  largest single directory is 21% of `nextgen-wealth-ledger` and 14% of the
  sample. It is a check on these repositories, not a rule imposed on every
  repository.
- **Upgrading** an existing wiki costs one full regeneration and one planning
  call per repository.

## Dependencies

- Spec 033 (feature navigation): candidates, repair, the plan cache and the
  page alias mechanism this spec builds on.
- Spec 038 (narrative Overview): the test-file conventions reused here, the
  answer keys and stranger-test protocol used for SC-006 and SC-007, and the
  Overview whose table and paragraphs this spec is meant to improve.
