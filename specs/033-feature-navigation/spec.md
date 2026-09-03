# Feature Specification: Feature Navigation in the Generated Wiki

**Feature Branch**: `033-feature-navigation`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "Feature navigation replacing directory-clustered sections in the generated wiki. Today the wiki's navigation is directory clustering wearing an LLM-supplied name: modules are grouped by repository-relative directory, small directories are absorbed, large ones are split by label propagation, and one model call per group invents a name for it. The result answers 'where does this code live' and never 'what does this repository do'. Replace it with an LLM-planned *feature* set: deterministic evidence, then deterministic candidates, then exactly one model call that plans the whole feature set, then deterministic repair. Feature pages replace section pages outright; the kind 'section' disappears. A feature's key is its anchor module key, so page identity must survive an anchor moving between runs - aliases and redirect stubs, never a dead URL. The single model call exchanges short ordinal handles and assigns candidates, never individual modules. Every input to that call is capped by a named constant. With no model reachable the wiki must build and navigate identically, with plainer titles. Module pages leave the sidebar, so the feature page and the search index become their only doors and both must be proven to hold."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Learn what a repository does from its navigation (Priority: P1)

Someone opens a generated wiki for a repository they have never seen. They want
the sidebar to tell them what the software *does* - the capabilities it offers,
the subsystems that deliver them - so they can pick the one that bears on their
question and start there.

Today the sidebar shows them the directory tree with nicer labels. A reader who
already knows the codebase gains nothing from it, and a reader who does not is
being asked to infer purpose from folder names.

**Why this priority**: This is the entire defect. Every other story is either a
guard on this one or a refinement of it. Shipping only this story turns a folder
listing into an answer to "what is this repository for".

**Independent Test**: Generate a wiki for a repository whose directory layout
does not mirror its capabilities - one where a single feature is spread across
several directories, or one directory holds two unrelated concerns. Confirm the
navigation names capabilities rather than folders, and that a capability spread
across directories appears once, not three times.

**Acceptance Scenarios**:

1. **Given** a repository with identifiable entry points, **When** its wiki is
   generated, **Then** the navigation lists features named for what they do,
   and each carries a short description of the capability it covers.
2. **Given** a capability implemented across more than one directory, **When**
   the wiki is generated, **Then** that capability appears as one navigation
   entry holding modules from every directory involved, rather than as one
   entry per directory.
3. **Given** one directory holding two unrelated concerns, **When** the wiki is
   generated, **Then** those concerns may appear as separate features rather
   than being forced together by their shared folder.
4. **Given** any generated wiki, **When** a reader opens a feature, **Then** the
   page states what the feature does, lists every module that belongs to it,
   and shows how those modules depend on one another.

---

### User Story 2 - Reach any module, with no module tree in the sidebar (Priority: P1)

The sidebar stops listing individual modules. A reader who wants a specific
module - by name, or because they are looking at its file in an editor - must
still get to its page in the wiki without guessing a URL.

**Why this priority**: This is the single most likely way this change makes the
wiki worse. Removing the module tree is what makes the sidebar readable, but it
also removes the door most readers use today. The replacement doors - the
feature page's member list and the search box - must be proven to hold, not
assumed to.

**Independent Test**: Take any module in a generated wiki, pick it at random,
and reach its page starting from the home page using only navigation and search.
Repeat for the module belonging to the largest feature, which is where a
truncated member list would bite first.

**Acceptance Scenarios**:

1. **Given** a generated wiki, **When** a reader opens the feature a module
   belongs to, **Then** that module is listed on the page with a working link,
   whatever the size of the feature.
2. **Given** a feature holding more modules than its diagram can legibly draw,
   **When** the reader opens it, **Then** the diagram is capped but the member
   list is not - every module is still listed, and the page says so.
3. **Given** a generated wiki, **When** a reader searches for any module by
   name, **Then** that module's page appears in the results.
4. **Given** any module in the repository, **When** the wiki is generated,
   **Then** exactly one feature claims it - a module is never listed twice and
   never missing from every feature.

---

### User Story 3 - A saved link keeps working after the repository changes (Priority: P1)

A reader bookmarks a feature page, or pastes its URL into an issue. Later the
repository changes, the wiki is regenerated, and the feature is now anchored on
a different module - so its URL has changed. The saved link must still land on
the right page. The same must hold for links saved against the *previous*
navigation scheme, before this feature existed.

**Why this priority**: A feature's identity is derived from its most connected
member, and a single new import can move that. Left unhandled, an ordinary
refactor silently breaks every link anyone saved. It is P1 because it is not
recoverable after the fact: once the links are out in issues and chat messages,
a later fix cannot repair them.

**Independent Test**: Generate a wiki, save a feature page's URL, edit the
repository so the feature's most-connected module changes, regenerate, and open
the saved URL. Separately, generate a wiki with the previous version of the
tool, regenerate it with this one, and open a URL saved from the old wiki.

**Acceptance Scenarios**:

1. **Given** a feature page URL saved from an earlier run, **When** the feature's
   anchor module changes and the wiki is regenerated, **Then** opening the saved
   URL reaches the feature's current page.
2. **Given** a wiki generated by the previous version of the tool, **When** it is
   regenerated with this version, **Then** every previously published section
   page URL still reaches a page, and that page is the feature that now holds
   most of the old section's modules.
3. **Given** a regenerated wiki, **When** an incremental run computes which pages
   no longer exist, **Then** it does not delete a file that a saved link is
   being redirected through.
4. **Given** a redirected URL, **When** it is opened, **Then** the reader arrives
   at the current page rather than at an error, and can tell where they were
   sent.

---

### User Story 4 - Generate a usable wiki with no model reachable (Priority: P2)

A reader generates the wiki on a machine with no provider configured, or with
every configured provider rate-limited or offline. The wiki must still build,
still group modules into features, and still navigate. Only the *names* should
be poorer.

**Why this priority**: P2 rather than P1 because the wiki is still generated
without it - but the failure mode it guards against is the quiet one. An
unreachable model and a silently-rejected call look identical from the outside,
so a navigation that depends on a model answering can degrade to nothing without
anyone noticing until a reader opens the wiki.

**Independent Test**: Generate a wiki with a working provider, record the
navigation. Generate the same repository with no provider configured at all.
Confirm the same features, holding the same modules, at the same page addresses -
differing only in their titles and descriptions.

**Acceptance Scenarios**:

1. **Given** no model is reachable, **When** the wiki is generated, **Then**
   every module still belongs to exactly one feature and every feature still has
   a page.
2. **Given** the same repository generated twice, once with a model and once
   without, **When** the two navigations are compared, **Then** the feature page
   addresses and the module-to-feature assignment are identical, and only titles
   and descriptions differ.
3. **Given** a model that answers with something unusable, **When** the wiki is
   generated, **Then** the outcome is the same as if no model had answered -
   never a partial or corrupted navigation.
4. **Given** a model that answers correctly, **When** the wiki is regenerated
   more than once for the same unchanged repository, **Then** the model is
   consulted once, not once per regeneration.

---

### User Story 5 - Read the navigation from general to specific (Priority: P3)

A reader scanning the sidebar wants the entry that describes the repository as a
whole near the top, the capabilities it offers next, the internals below that,
and the incidental tooling last - so the first thing they read is the most
orienting.

**Why this priority**: A genuine improvement in how quickly a newcomer orients,
but the navigation is already usable without it. It is the last thing to build
and the first thing to drop if it proves contentious.

**Independent Test**: Generate a wiki and read the sidebar top to bottom.
Confirm that entries describing the whole precede entries describing the parts,
and that incidental tooling is last rather than interleaved alphabetically.

**Acceptance Scenarios**:

1. **Given** a generated wiki whose features span several kinds, **When** a
   reader reads the sidebar top to bottom, **Then** the entries progress from
   the most general to the most specific rather than being ordered
   alphabetically.
2. **Given** two features of the same kind, **When** they are ordered, **Then**
   the one exposing more of the repository's entry points comes first, and ties
   between them are broken the same way on every run.

---

### Edge Cases

- **A repository with no identifiable entry points at all** - a library of pure
  helpers, or a repository of documents. Every module must still land in a
  feature; the grouping falls back to the structural clustering used today
  rather than producing nothing.
- **A module no entry point reaches** - dead code, a script nothing imports, a
  test helper. It must still be claimed by exactly one feature rather than
  disappearing from the navigation.
- **Two features whose planned titles are identical**, or a title long enough to
  break the sidebar's single line. Both are rejected rather than published.
- **A model that names a candidate that does not exist**, or names one twice, or
  leaves one out entirely. Each is repaired deterministically; none may produce
  a module that belongs to no feature.
- **A model that answers with fewer than two usable features** - a "plan" that
  collapses the whole repository into one entry is not navigation. The whole
  plan is rejected in favour of the deterministic grouping.
- **A very large repository** whose candidate count or member summaries would
  push the single planning call past what a provider accepts in one window. Every
  input is capped in advance, and the cap is verified rather than trusted.
- **A repository whose entry points all live in one module** - the candidate set
  collapses to one. This must still produce a navigable wiki rather than a
  single feature holding everything.
- **Regeneration where nothing changed** - no model call at all, and no page
  rewritten.
- **A feature whose anchor module is deleted** between runs. The saved URL must
  still resolve, and the removal pass must not race the redirect.
- **A module that is a document rather than code** - the wiki indexes README and
  other prose files as modules, and no entry point ever reaches one. They must
  still be grouped and still be navigable, not silently dropped from the
  navigation for lacking callers.
- **A model that answers with a kind outside the recognised vocabulary.** The
  feature keeps its title and description and takes the default kind; it is not
  discarded over a field that only affects ordering.
- **An existing wiki on disk built by the previous version**, mid-migration:
  interrupted after some pages were rewritten. The next run must complete the
  migration rather than leaving the wiki half-converted.

## Requirements *(mandatory)*

### Functional Requirements

#### Grouping: what a feature is and how membership is decided

- **FR-001**: Every module in the analysed repository MUST belong to exactly one
  feature. No module may appear in two features, and none may be absent from all
  of them.
- **FR-002**: Feature membership MUST be decided deterministically, with no model
  involved: the same repository MUST yield the same features, holding the same
  modules, with the same page addresses, on every run.
- **FR-003**: The system MUST derive, for each module and with no model call,
  the evidence a feature grouping is decided from: which of the repository's
  entry points reach it, which public symbols it exports, its existing generated
  summary, and its path.
- **FR-004**: The system MUST read the analysed repository's own README, where
  one exists, for the repository's stated capabilities, and MUST NOT write to
  the analysed repository in doing so.
- **FR-005**: Grouping MUST be seeded from the repository's entry points - the
  places the software is actually invoked - rather than from its directory
  layout. Entry points sharing a module MUST share one seed.
- **FR-006**: Modules MUST be attached to a seed by how directly the seed reaches
  them, with the attachment weakening as the distance grows and stopping at a
  bounded distance. A module reachable from several seeds MUST be assigned to
  exactly one, chosen by a rule that resolves ties identically on every run.
- **FR-007**: Groups too small to read as a capability MUST be folded into a
  larger group that reaches them, and the surviving groups MUST be capped at a
  fixed maximum, with the remainder folded the same way. Both steps MUST be
  deterministic.
- **FR-008**: Modules that no entry point reaches MUST still be grouped, using
  the structural clustering the wiki uses today as the fallback path.

#### Planning: the one model call

- **FR-009**: The system MUST consult a model at most once to plan the whole
  feature set. It MUST NOT make one call per feature, per group, or per module.
- **FR-010**: The model MUST assign whole candidate groups to features, never
  individual modules. This is what makes it impossible for the model's answer to
  leave a module belonging to no feature.
- **FR-011**: The system MUST exchange short opaque handles with the model in
  place of module or group identifiers, and MUST resolve the returned handles
  back to groups itself.
- **FR-012**: Every input to the planning call - the number of groups described,
  the number of members described per group, the length of each member's
  description, and the length of the repository capability text - MUST be bounded
  by a named, single-source constant, and the resulting worst-case size MUST be
  verified against those constants rather than assumed.
- **FR-013**: The system MUST validate the model's answer and repair it
  deterministically, with no second model call. Specifically:
  - a handle that names no known group MUST be ignored;
  - a group named by no feature MUST become its own feature under its
    deterministic name;
  - a group named by several features MUST be kept in exactly one of them;
  - a feature left holding nothing after repair MUST be dropped;
  - a feature whose title is empty, over-long, or a duplicate of another MUST be
    rejected, and its groups reassigned;
  - a feature whose kind is not one of the recognised kinds MUST be given the
    default kind rather than rejected - an unrecognised kind costs the feature
    its place in the ordering, which is not worth discarding a good title and
    description for.
- **FR-014**: Any group still unplaced after repair MUST land in one explicitly
  constructed terminal feature rather than being left to emerge from the repair
  rules.
- **FR-015**: If repair leaves fewer than two usable features, the whole planned
  answer MUST be discarded in favour of the deterministic grouping.
- **FR-016**: A planned feature set MUST be cached against the repository
  structure it was planned from, so that regenerating an unchanged repository -
  which happens more than once per indexing run - consults the model once at
  most.
- **FR-017**: A model that is unreachable, that refuses the call, or that answers
  unusably MUST degrade the wiki's titles, never its structure and never the run.

#### Identity: addresses that survive

- **FR-018**: A feature's identity MUST be derived from its anchor module,
  chosen deterministically from the feature's own membership, so that two runs
  over an unchanged repository produce identical page addresses.
- **FR-019**: A feature's title MUST NOT contribute to its page address. A
  re-titled feature MUST keep the address it had.
- **FR-020**: When a feature's anchor changes between runs, the system MUST
  record the previous address as an alias for the new one and MUST leave
  something at the old location that sends a reader to the new page.
- **FR-021**: The pass that removes pages no longer present MUST NOT delete a
  file that a recorded alias points through.
- **FR-022**: A wiki generated by the previous version MUST be migrated on the
  next run: every previously published section page address MUST resolve, and it
  MUST resolve to the feature holding the largest share of that section's
  modules.
- **FR-023**: Detecting a wiki from the previous version MUST force one complete
  regeneration rather than an incremental one, and the previous version's cached
  group names MUST be discarded in the same pass.

#### Navigation and pages

- **FR-024**: The persistent sidebar MUST list features only. It MUST NOT list
  individual modules. The home page's own listing of the repository's areas MUST
  list the same features, so the two never disagree about what the repository
  contains.
- **FR-025**: A feature's page MUST list every module belonging to that feature,
  with no truncation, whatever the feature's size. Where the page's diagram is
  capped for legibility, the page MUST say so and MUST still list the omitted
  modules.
- **FR-026**: The wiki's search MUST return an entry for every module in the
  repository, so that a module is reachable without navigating to its feature
  first.
- **FR-027**: Every feature MUST carry a kind drawn from one fixed, closed
  vocabulary ordered from general to specific, and sidebar entries MUST be
  ordered by that kind first, with a deterministic tie-break within a kind,
  rather than alphabetically.
- **FR-028**: A feature page MUST show how its own modules depend on one another,
  and the diagram's nodes MUST remain clickable links to those modules' pages,
  exactly as the section page's diagram is today.

#### Preservation

- **FR-029**: Incremental regeneration MUST be preserved: a change to one module
  MUST NOT rewrite every page, except where the navigation itself has changed
  shape, which already forces a full pass today.
- **FR-030**: Every part of the feature-derivation pipeline except the single
  planning call MUST be exercisable and verifiable with no model available at
  all, and the no-model path MUST be asserted by a test rather than assumed.
- **FR-031**: The previous navigation scheme MUST be removed rather than left
  alongside the new one. A generated wiki MUST NOT publish two competing
  groupings of the same repository, whether behind a setting or side by side.
- **FR-032**: The generated Markdown output for a feature page MUST carry the
  same information the section page carries today: what the area is, every module
  in it, its internal dependency diagram, and its neighbouring areas.
- **FR-033**: The planning call MUST reach a model only through the model access
  the project already has configured, with the same ordering and the same
  visibility of a switch between providers. It MUST NOT introduce a second route
  to a model.
- **FR-034**: The feature plan and its cache MUST be held in the storage the wiki
  already uses. No new storage technology, and no network service, may be
  introduced by this feature.

### Key Entities

- **Feature evidence**: what is known about one module before any grouping is
  decided - the entry points that reach it, the public symbols it exports, its
  existing summary, and its path. Derived with no model call, and the sole input
  to candidate formation.
- **Candidate**: a provisional group of modules seeded by one entry-point module
  and grown by reachability. Every module belongs to exactly one candidate. This
  is the unit the model is asked to organise, and the unit repair operates on -
  which is what makes an orphaned module structurally impossible.
- **Feature**: a published capability of the repository - a title, a description,
  a kind that places it on the general-to-specific scale, and the candidates
  assigned to it. Its identity comes from its anchor module, never from its
  title.
- **Feature plan**: one model answer covering the whole repository - a list of
  features, each naming the candidates it holds by handle. Validated and repaired
  before use, cached against the structure that produced it, and discardable in
  full.
- **Page alias**: a record that an address a wiki once published now belongs to a
  different page, together with the files left behind at the old address to send
  readers onward. Consulted before any page file is deleted.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reader who has never seen the repository can name three things
  the software does by reading the sidebar alone, without opening a page.
- **SC-002**: 100% of the repository's modules are reachable from the home page
  through navigation, and 100% are returned by search - verified on a regenerated
  wiki, not in a test harness alone.
- **SC-003**: Every module belongs to exactly one feature: the count of modules
  across all features equals the count of modules in the repository, with no
  duplicates.
- **SC-004**: Planning the whole feature set costs at most one model call per
  distinct repository structure, and zero calls when regenerating an unchanged
  repository.
- **SC-005**: The worst-case size of the planning call, computed from the
  declared caps, stays within the smallest provider window the project is
  configured against, with headroom - and that arithmetic is checked
  automatically against the constants rather than recorded in prose.
- **SC-006**: Generating the same repository with a model and with no model
  available produces identical feature page addresses and identical
  module-to-feature assignment; only titles and descriptions differ.
- **SC-007**: 100% of page addresses published by a previous run still resolve
  after a regeneration in which anchors moved, and 100% of section page addresses
  published by the previous version of the tool still resolve after migration.
- **SC-008**: No feature page truncates its member list at any repository size.
- **SC-009**: A wiki generated with no provider configured is byte-for-byte
  navigable: the same pages exist, at the same addresses, with the same links.
- **SC-010**: An ordinary edit to one module still regenerates a small number of
  pages rather than the whole wiki, matching today's incremental behaviour.

## Assumptions

Recorded because the feature description or prior decisions settled them; they
constrain the solution rather than being open questions.

- **Features replace sections outright.** The previous grouping is not kept
  alongside the new one behind a switch. Two navigations describing the same
  repository differently is worse than either alone, and the migration path
  (FR-022, FR-023) is what makes the replacement safe.
- **A feature's key is its anchor module's key.** One identifier, not a
  composite: the address is derived from one argument, which is what keeps the
  alias table's job simple enough to be correct.
- **The model is asked to organise candidates, not modules.** This is a
  measurement-driven constraint, not a stylistic one: naming modules directly
  would put thousands of tokens of identifiers into a single call, and it would
  reintroduce the orphaned-module failure mode that assigning candidates designs
  out.
- **Short opaque handles stand in for real identifiers** in both directions of
  the model exchange, matching the convention the wiki's diagram generation
  already uses for the same reason - the real key is neither short nor safe to
  echo back.
- **Entry points are the seed.** The repository's own invocation points are the
  closest available proxy for "what this software does", they are already
  identified by the existing pipeline, and they cost no model call.
- **The structural clustering used today survives as the fallback path**, not as
  the main one. It is the answer for modules no entry point reaches, and for a
  repository that has no entry points at all.
- **The single planning call goes through the existing provider chain** as every
  other optional model call in the generator does, and fails the same way: a
  degraded page, never a failed run.
- **Existing per-diagram size caps stay as they are.** This feature changes how
  modules are grouped and named, never how many nodes a diagram draws.
- **Reading the analysed repository's README is a read, and is permitted.** The
  read-only guarantee on the analysed repository forbids writes, not reads, and
  the chat pipeline already reads it for the same kind of reason.
- **Verification on a real generated wiki is part of the feature, not an
  optional extra.** The requirements most likely to fail silently - a module
  losing its last door, a saved link dying, a model call being rejected without
  a trace - are all requirements a passing test suite can be blind to.
