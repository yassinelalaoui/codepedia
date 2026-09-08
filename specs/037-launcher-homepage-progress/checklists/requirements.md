# Specification Quality Checklist: Launcher Homepage with Live Run Progress

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-04
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Validation record

Three issues were found on the first pass and fixed before this checklist was
marked complete:

1. **An edge case with no requirement behind it.** Edge Cases listed submitting
   the tool's own state directory as the path to analyse, but no functional
   requirement made that testable — FR-009 only required the path to exist, be a
   directory and be readable. FR-009 was extended to require that the path is
   neither the state location nor contained within it, which is what keeps an
   analysis from nesting inside its own output and is the input-side half of the
   read-only guarantee in FR-011.
2. **An unmeasurable word.** FR-020 required the user to reach the documentation
   "promptly" when a repository needs no bringing-up-to-date. Reworded to a
   5-second bound with an explicit requirement that no progress display appear
   at all, so the requirement can fail a test.
3. **An unmeasurable success criterion.** SC-012 required "no unreadable
   contrast", which no verification could settle. Replaced with a 4.5:1 contrast
   ratio and zero horizontal page overflow, both of which a browser check can
   assert directly.

The **Input** section quotes the user's own description verbatim, as the
template requires, and that quotation contains concrete technical details — a
command name, a loopback address, tokens, subprocesses. Those are not treated as
leaked implementation details, because the specification body restates every one
of them in outcome terms: FR-003 says "only from the local machine" rather than
naming an address, FR-004 and FR-005 say "credential" rather than naming a token
scheme, and FR-035 says "a server dedicated to that repository" rather than
naming a subprocess. The same convention was applied in feature 036.

### Decisions taken as settled, not as open questions

Six design questions were put to the repository owner before this specification
was drafted, and their answers are written into it as requirements rather than
left for `/speckit-clarify`:

- **The hub links to per-repository servers rather than re-hosting
  documentation** (FR-035, FR-037, Out of Scope).
- **A late failure keeps today's discard-everything behaviour**, reported
  honestly instead of prevented (User Story 3, FR-021 through FR-024, Out of
  Scope).
- **One analysis at a time, refusing the second** rather than queuing or
  parallelising (FR-012, Out of Scope).
- **The credential model matches the single-repository server's** — fresh per
  run, never persisted, carried in the printed address (FR-004, FR-005).
- **The row menu is Properties, Open, Remove, with no re-analyse action**
  (FR-033), because opening a repository already brings it up to date
  (FR-036) and the index control already provides the full-rebuild escape hatch
  (FR-013). This was settled after establishing from the code that the change
  watcher exists only inside a running single-repository server, and that it
  reconciles everything that changed while that server was stopped.
- **The provider outage on the owner's machine is designed for, not fixed**
  (FR-025, and User Story 3 as a first-class path rather than an edge case).

### Clarification session of 2026-09-04

Five questions were asked and answered; all five are recorded in the spec's
`## Clarifications` section and integrated into requirements. Re-validation
after the session left the checklist at **16/16 items passing**, unchanged —
no item newly passed and none regressed.

Two of the three points this checklist had deferred are now settled:

- The homepage **does** get the same three-state appearance control as the
  generated documentation (FR-044a through FR-044c, SC-012), with its own
  remembered choice — the homepage and each wiki are separate origins, so no
  preference can travel between them.
- A history row whose folder has moved or been deleted **stays listed, marked
  unavailable, readable and removable** (FR-031a, FR-031b, FR-039). Path is
  identity; a move is not detected and produces a second entry, which is
  accepted rather than solved.

The third remains deferred, correctly, to `/speckit-plan`: whether the derived
history scan needs a cache to meet SC-006 is a performance question, not a
requirement.

Two answers changed the shape of the feature rather than only settling a
detail, and both need attention in planning:

1. **Cancelling a run** (FR-012a) adds a third terminal outcome beside succeeded
   and failed. It touches the run model, the display, and the guarantee in
   FR-026 that the system is immediately ready for the next analysis. Every
   place the spec reasons about a terminal state now reasons about three.
2. **A durable run log** (FR-026a through FR-026e) was chosen over holding only
   the most recent run in memory, against the recommendation. This is genuinely
   new stored state, and `/speckit-plan` must treat it as such:
   - It stays within **constitution 2.6**, which forbids an external database
     server, broker or cloud component but expressly permits embedded local
     storage. FR-026c makes that explicit. It is not a violation and needs no
     Complexity Tracking entry, but the plan must show where the record lives
     and how it is pruned.
   - It creates a failure mode that would not otherwise exist: a run whose
     record was never closed because the hub was killed. FR-026d requires it be
     shown as interrupted rather than as permanently running, and FR-026e
     requires an unreadable or older-version record to degrade to "no past runs"
     rather than break the homepage. Both need tests.
   - It introduces a second, distinct notion of history. The Key Entities
     section separates them deliberately: a **run record** describes one
     attempt, including attempts that produced nothing; a **history entry**
     describes a repository that currently has stored analysis. Planning must
     not collapse them, or a failed run will start appearing as a repository —
     which is precisely what FR-030 exists to prevent.
