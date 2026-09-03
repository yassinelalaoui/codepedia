# Specification Quality Checklist: Feature Navigation in the Generated Wiki

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-02
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

Two iterations, same method as 034 and 035.

**Iteration 1 findings (resolved)**:

1. *No implementation details*: the feature description is written almost
   entirely in module names, function names and file paths, because it is the
   technical input to planning rather than a user description. Every mechanism it
   names — reachability weighting, ordinal handles, the alias table, the
   fallback clustering — moved to **Assumptions**, where a later reader can
   challenge the decision without having to rediscover it. The requirements
   describe what a reader of the generated wiki can observe.
2. *Requirements testable*: an early FR read "the model plans the feature set",
   which is a description of a call, not an observable. Split into FR-009 (at
   most one call), FR-010 (it assigns groups, not modules) and FR-013 (its answer
   is validated and repaired) — each of which a test can fail.
3. *Success criteria technology-agnostic*: an early SC named the provider's
   per-minute token ceiling directly. Replaced by SC-005, which states the
   property — worst case within the smallest configured window, with headroom,
   checked automatically against the declared caps — without naming the provider
   or the number, so the criterion survives a provider change.

**Iteration 2 findings (resolved)** — all four are substantive, not editorial:

1. **The kind vocabulary was assumed rather than required.** FR-027 asked for
   general-to-specific ordering and the Key Entities section mentioned a "kind",
   but nothing required features to carry one or bounded what it could be. A
   model free to invent a kind makes the ordering unspecifiable. FR-027 now
   requires one fixed, closed, ordered vocabulary.
2. **The repair table had no row for an unrecognised kind**, which follows
   directly from (1) and is the likeliest single malformation in a real answer.
   Added to FR-013 as a *default*, not a rejection: a kind only affects
   ordering, and discarding a good title and description over it would be a
   worse outcome than a misplaced sidebar entry.
3. **The home page's own listing of the repository's areas was unspecified.**
   FR-024 covered only the sidebar. The home page renders the same grouping a
   second time, so leaving it unstated would permit a wiki whose sidebar and home
   page disagree about what the repository contains. FR-024 now covers both.
4. **Prose modules had no edge case.** The wiki indexes README and other
   documents as modules, and nothing ever calls a document — so under an
   entry-point-seeded grouping they are reachable from no seed at all. Without
   the edge case, "every module belongs to exactly one feature" (FR-001) and the
   entry-point seeding rule (FR-005) are in silent conflict for a whole class of
   module. FR-008 resolves it; the edge case now names the case explicitly.

One further change was editorial rather than a finding: FR-033 originally bundled
network exposure, storage technology and model access into a single requirement
restating three constitution principles at once, which no single test can fail.
Split into FR-033 (one route to a model) and FR-034 (existing storage, no network
service).

**Deliberate judgement calls**, recorded so they are not re-litigated:

- **No [NEEDS CLARIFICATION] markers.** Three decisions that would otherwise have
  been questions were settled with the user before planning: the model exchanges
  handles and organises candidates rather than modules; a feature's key is its
  anchor module key, one argument rather than two; and feature pages replace
  section pages outright rather than living beside them. All three are in
  Assumptions with their reasoning.
- **User Story 2 (module reachability) is P1**, though it adds no new value and
  is purely a regression guard. Removing the module tree is the change that makes
  the sidebar readable and it is simultaneously the change most likely to make
  the wiki worse — a module whose feature page truncates its member list becomes
  unreachable, and nothing in the wiki would say so. Same reasoning that made
  034's click-navigation story and 035's fragment-navigation story P1.
- **User Story 3 (saved links) is P1 rather than P2** because it is the only
  requirement here that cannot be repaired later. A truncated member list can be
  fixed next week and the wiki is correct again; links already pasted into issues
  and chat messages cannot be recalled once they die.
- **SC-001 is deliberately a human judgement** ("can name three things the
  software does from the sidebar alone"). The measurable proxies — feature count,
  title length, kind distribution — would all be satisfiable by a navigation that
  is still useless, which is exactly the failure this feature exists to correct.
  It is checked by hand, and the spec says so.
- **SC-002, SC-007 and SC-009 require verification on a real regenerated wiki**,
  not in a test harness. This project has now shipped four defects that passed a
  full green suite; the common shape is a check that asserts a call was made
  rather than that a reader arrived somewhere. "Every module is reachable" and
  "every saved link resolves" are both of that shape.
- **FR-030 (every stage verifiable with no model) is a requirement, not an
  assumption.** An unreachable model and a silently-rejected call are
  indistinguishable from the outside, so the no-model path has to be asserted
  rather than inferred from the fact that the wiki still built.
