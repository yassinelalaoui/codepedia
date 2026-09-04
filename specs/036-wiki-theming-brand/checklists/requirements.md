# Specification Quality Checklist: Wiki Theming and Brand Identity

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

Two issues were found on the first pass and fixed before this checklist was
marked complete:

1. **Edge case without a requirement.** The printing edge case was identified in
   Edge Cases and echoed in Assumptions, but no functional requirement made it
   testable. Added **FR-026** covering printed output, which brings the Feature
   Readiness item "All functional requirements have clear acceptance criteria"
   into line with the edge case list.
2. **Storage mechanism naming.** An early draft named the browser storage
   mechanism directly in FR-007 and FR-010, which is an implementation choice
   belonging in `plan.md`. Reworded to "remember the reader's choice" and "if
   storing or reading the preference fails", leaving the mechanism to planning.

3. **A requirement about a component that does not exist.** `/speckit-analyze`
   found that FR-013b, added when FR-013 was split during clarification, required
   syntax-highlighted code to stay legible across themes — but the wiki ships no
   syntax highlighter. There are no `hljs` rules in `frontend/src/styles.css` and
   no highlighting extension is registered in `src/doc_generator/html_render.py`.
   Code blocks are styled entirely from theme tokens
   (`styles.css` lines 390-399), so they follow a theme change with no work.
   FR-013b was reworded to "code blocks", the matching User Story 4 acceptance
   scenario was corrected, and an Assumptions entry records the finding. It is
   now a regression guard rather than a build item.

The single reference to `docs/brand/` in the spec appears only inside the
verbatim **Input** quotation of the user's own description, which the template
requires be reproduced as given. It is not treated as a leaked implementation
detail.

### Deferred to `/speckit-clarify` — now resolved

The spec resolved these with documented defaults in Assumptions rather than
`[NEEDS CLARIFICATION]` markers. All four were put to the user in the
clarification session of 2026-09-04 and are recorded in the spec's
`## Clarifications` section:

- Which brand asset the shell's brand slot uses, given the policy's 24 px
  minimum for the full mark against the slot's current 20 px size — **resolved**:
  grow the slot to 24 px and use the full mark (FR-014, FR-017).
- Whether the theme control is a three-way control or a two-way toggle with
  System reachable another way — **resolved**: a segmented three-way control in
  the sidebar (FR-001, FR-002).
- Whether the theme preference is shared across generated wikis on one machine
  or stays per-wiki as assumed — **resolved**: per wiki, independent, which is
  what browsers permit for filesystem-opened pages (FR-007).
- Whether the print requirement is in scope — **resolved**: kept but minimal,
  light palette only, with print layout work explicitly excluded (FR-026).

A fifth question was raised in the same session and is not in the list above,
because it emerged from the clarification scan rather than from spec drafting:
whether diagrams must redraw on a theme change. **Resolved**: they must,
preserving the reader's zoom and pan (FR-013, FR-013a, SC-011).
