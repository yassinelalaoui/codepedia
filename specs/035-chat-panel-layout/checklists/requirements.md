# Specification Quality Checklist: Chat Panel Layout — Reach the Input Without Scrolling

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

Two iterations, same method as 034.

**Iteration 1 findings (resolved)**:

1. *No implementation details*: the description is written in CSS — selectors,
   properties, line numbers. Restating that in the requirements would make
   FR-001..FR-029 untestable as behaviour. Every mechanism moved to
   **Assumptions**; the requirements now describe what a reader can observe.
   FR-028 keeps the *outcome* of "browser-side only" (generated pages unchanged)
   without naming the mechanism.
2. *Success criteria technology-agnostic*: an earlier SC referred to the built
   bundle. Replaced by SC-009 (generated files byte-identical), which measures
   the same guarantee from the reader's side.
3. *Requirements testable*: "the chat column is viewport-height" is a CSS fact,
   not an observable. Restated as FR-001/FR-005 — the composer cannot be pushed
   off screen by any combination of page and conversation length, which is what a
   tester can actually check.

**Iteration 2 findings (resolved)**:

1. Two edge cases were missing and are genuinely reachable: sending a question
   while scrolled up (FR-015 now settles it — sending returns you to the newest
   message, because sending is deliberate), and a window short enough that the
   message list has almost no height left.
2. FR-022 was implicit. An empty send is currently blocked by the submit handler;
   with Enter-to-send and a button added, there are now three routes in and the
   rule has to hold for all of them.

**Deliberate judgement calls**, recorded so they are not re-litigated:

- **No [NEEDS CLARIFICATION] markers.** The description settled the layout
  approach, the pinned tolerance, the composer bound, the Enter convention and
  the narrow-window treatment. Each is in Assumptions with its reasoning, so a
  later reader can challenge a decision without rediscovering it.
- **User Story 2 (fragment navigation) is P1**, alongside the actual fix. It adds
  no new value — it is purely a regression guard. But this change relocates the
  scroll container, which is precisely what anchor navigation depends on, and
  every page in the wiki has a rail. Same reasoning that made 034's
  click-navigation story P1.
- **SC-003 and SC-001 require verification in a real browser.** Feature 034
  shipped two defects that every jsdom test passed over — a swallowed promise
  rejection and a pointer-capture retarget — and both were found only by loading
  a real page. Layout and scroll containers are, if anything, less faithfully
  modelled by a headless DOM than events are: jsdom reports all-zero element
  geometry, so a test asserting "the composer is visible" there proves nothing.
- **Reduced motion (FR-027) is stated as preservation, not a new feature.** The
  preference already applies today; the risk is that relocating the scroll
  container silently drops it, which is why it is called out explicitly.
