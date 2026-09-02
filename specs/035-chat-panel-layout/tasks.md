---

description: "Task list for 035-chat-panel-layout"
---

# Tasks: Chat Panel Layout — Reach the Input Without Scrolling

**Input**: Design documents from `/specs/035-chat-panel-layout/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/chat-panel-shell.md](./contracts/chat-panel-shell.md), [quickstart.md](./quickstart.md)

**Tests**: Included — the spec requires them. But read the honest caveat below
before trusting them.

> **jsdom cannot answer this feature's central question.** It reports all-zero
> element geometry, so a headless assertion that "the composer is visible without
> scrolling" is vacuous. User Story 1 has **no meaningful unit test at all**; its
> verification is the browser check in Phase 3. Feature 034 shipped two defects
> that every jsdom test passed over — this feature is *more* geometric than that
> one, not less.

**Organization**: Grouped by user story. Parallelism is limited by file, not by
story — see [Dependencies](#dependencies--execution-order).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different file, no dependency on incomplete work
- **[Story]**: US1..US5, mapping to the user stories in spec.md

## Path Conventions

Browser-only feature. Everything is under `frontend/`; no Python file is touched,
which is what makes FR-028 and SC-009 true by construction.

---

## Phase 1: Setup

**Purpose**: Test scaffolding that later phases assert against.

- [X] T001 Add a `scrollIntoView` stub to `frontend/tests/setup.ts` — define `Element.prototype.scrollIntoView` as a no-op when absent, beside the existing `localStorage` polyfill. jsdom 25 leaves it `undefined`, so without this the fragment handler's `typeof` guard is false under test and the whole path is skipped — exactly how 034's `setPointerCapture` defect stayed invisible (research Decision 4)
- [X] T002 [P] Add a `defineScrollGeometry(el, { scrollHeight, clientHeight })` helper to `frontend/tests/ChatPanel.test.tsx` using `Object.defineProperty` — jsdom reports both as `0`, so every pinned-state assertion needs them supplied

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The one structural change more than one story builds on.

**Honest scope note**: this phase is deliberately thin. US1 is CSS-only and US2
lives in `main.tsx`; **neither depends on anything here** and both could proceed
first. Only US3 strictly requires it, with US4 and US5 building around the same
markup.

- [X] T003 Introduce a stable, always-rendered `div.wiki-chat-scroll` in `frontend/src/components/ChatPanel.tsx` wrapping either `p.wiki-chat-empty` or `ul.wiki-chat-messages`, per data-model.md § DOM structure. Today the list is rendered only once a message exists (`ChatPanel.tsx:189`), so a scroll ref is `null` exactly when the first auto-scroll would need it
- [X] T004 Move `overflow-y: auto` from `.wiki-chat-messages` (`frontend/src/styles.css:658`) onto the new `.wiki-chat-scroll`, leaving the list's own spacing and flex rules intact

**Checkpoint**: The panel renders and behaves exactly as before, now with one
stable scroll container.

---

## Phase 3: User Story 1 — Ask without hunting for the box (Priority: P1) 🎯

**Goal**: The composer is always on screen, whatever the page length.

**Independent Test**: Open the longest page in a generated wiki, scroll to the
middle, type a question without scrolling the page at all.

**No unit tests in this phase.** Every requirement here is geometric and jsdom
reports zero for all of it. Asserting a CSS property was set would test the
stylesheet against itself. T008 is the real test.

- [X] T005 [US1] In `frontend/src/styles.css:104`, change `.shell` from `min-height: 100vh` to `height: 100vh` and add `overflow: hidden` (FR-001, FR-005)
- [X] T006 [US1] In `frontend/src/styles.css:237`, add `overflow-y: auto` and `scroll-padding-top: 24px` to `.main`, and move `scroll-behavior: smooth` here from the `html` rule at `:233`, keeping its `prefers-reduced-motion: no-preference` guard. Left on `html` it would apply to an element that no longer scrolls, silently losing the reader's preference (FR-003, FR-008, FR-027)
- [X] T007 [US1] In `frontend/src/styles.css:604`, add `height: 100%` and `min-height: 0` to `#wiki-chat-root`. `min-height: 0` is mandatory, not cosmetic: a grid item defaults to `min-height: auto` and refuses to shrink below its content, so a long conversation would push the column past the window and restore the original defect (FR-001, FR-002)
- [X] T008 [US1] Verify in a real browser per quickstart § 2 checks 1-3: on the longest page `document.scrollingElement.scrollHeight <= innerHeight + 1`; the composer's rect stays in the viewport after scrolling `.main` to its end; scrolling `.main` leaves the sidebar's and chat's `scrollTop` untouched; and 100 injected messages do not move the composer (SC-001, SC-002, FR-003, FR-004)

**Checkpoint**: The reported defect is fixed — **and every anchor link in the
wiki is now broken.** Do not ship this alone; see Phase 4.

---

## Phase 4: User Story 2 — Jump to a heading and land on it (Priority: P1)

**Goal**: The "On this page" rail and cross-page search results still land on the
right heading now that `.main` scrolls instead of the document.

**Independent Test**: Click a rail entry and confirm the heading is reached. From
a different page, open a search result naming a symbol and confirm the loaded
page is already scrolled to it.

### Tests for User Story 2

- [X] T009 [P] [US2] In `frontend/tests/`, add a failing test that a `location.hash` naming an existing element causes `scrollIntoView` to be called on that element — spy via `vi.spyOn(Element.prototype, "scrollIntoView")`, which works only because T001 defined it (FR-006, FR-007)
- [X] T010 [P] [US2] Add a failing test that a hash naming no existing element leaves the page untouched and throws nothing (FR-010)
- [X] T011 [P] [US2] Add a failing test that a `hashchange` event re-resolves and scrolls to the new target

### Implementation for User Story 2

- [X] T012 [US2] Implement the fragment handler in `frontend/src/main.tsx` — resolve `location.hash`, guard `typeof el.scrollIntoView === "function"`, call it; register on `hashchange` and run once at module evaluation (the bundle loads at the end of `<body>`, so the DOM is already parsed). Compute no offset of its own — `scroll-padding-top` from T006 handles that. Makes T009-T011 pass (FR-006, FR-007, FR-010)
- [X] T013 [US2] Verify in a real browser per quickstart § 2 check 4: load a page with a `#fragment` naming a heading well down the page and assert the heading's `getBoundingClientRect().top` sits within a small band of `scroll-padding-top` — neither zero nor off screen. Repeat by clicking a rail entry. A stub proves the call was made; only this proves the reader ended up in the right place (SC-003, FR-008, FR-009)

**Checkpoint**: Both P1 stories complete. **This is the shippable increment** —
Phases 3 and 4 are one release boundary.

---

## Phase 5: User Story 3 — Follow an answer without being yanked (Priority: P2)

**Goal**: New content scrolls into view while the reader is at the bottom, and
never moves their view when they are not.

**Independent Test**: Ask a question and watch the answer arrive untouched; ask
another and scroll up while it arrives.

### Tests for User Story 3

- [X] T014 [P] [US3] In `frontend/tests/ChatPanel.test.tsx`, add a failing test that with the container pinned, a new message drives `scrollTop` to `scrollHeight` (FR-011)
- [X] T015 [P] [US3] Add a failing test that with the container scrolled up beyond the 40px tolerance, an arriving streamed fragment leaves `scrollTop` unchanged (FR-012)
- [X] T016 [P] [US3] Add a failing test that a non-overflowing container (`scrollHeight <= clientHeight`) counts as pinned, so a short conversation still auto-scrolls (data-model invariant)
- [X] T017 [P] [US3] Add failing tests for the jump affordance: absent while pinned, present when scrolled away, and on activation scrolls to the bottom and re-pins (FR-013, FR-014)
- [X] T018 [P] [US3] Add a failing test that submitting a question returns the view to the newest message even when scrolled away (FR-015)

### Implementation for User Story 3

- [X] T019 [US3] Implement `PinnedState` in `frontend/src/components/ChatPanel.tsx` — a scroll listener on the T003 container **deriving** `isPinned` from `scrollHeight - scrollTop - clientHeight <= 40`, never toggling it. Deriving is what prevents the auto-scroll write from feeding back through its own handler (contract § 2.2)
- [X] T020 [US3] Implement auto-scroll in `frontend/src/components/ChatPanel.tsx` as `container.scrollTop = container.scrollHeight`, in a layout effect so it lands before paint. **Not `scrollIntoView` or `scrollTo`** — both are `undefined` in jsdom 25 and throw (research Decision 3). Makes T014-T016 pass
- [X] T021 [US3] Add the jump-to-latest control to `frontend/src/components/ChatPanel.tsx`, rendered only when not pinned, scrolling to the bottom and re-pinning on activation. Makes T017 pass
- [X] T022 [US3] Re-pin and scroll to bottom on submit in `frontend/src/components/ChatPanel.tsx`. Makes T018 pass (FR-015)
- [X] T023 [P] [US3] Style `.wiki-chat-jump-latest` in `frontend/src/styles.css` using existing tokens, positioned above the composer without overlapping it

**Checkpoint**: US1, US2 and US3 all work independently.

---

## Phase 6: User Story 4 — Write a question longer than one line (Priority: P2)

**Goal**: A multi-line composer with Enter to send and Shift+Enter for a newline.

**Independent Test**: Type a multi-line question, confirm the box grows, send it
with the keyboard, then again with the button.

### Tests for User Story 4

- [X] T024 [P] [US4] **No change was needed.** All four `findByLabelText` call sites, and all 17 existing ChatPanel tests, passed against the textarea unmodified — keeping the label byte-identical was sufficient. Recorded rather than silently skipped: the task assumed adaptation would be required and it was not
- [X] T025 [P] [US4] Add a failing test that `Enter` without Shift sends the question and calls `preventDefault` (FR-017)
- [X] T026 [P] [US4] Add a failing test that `Shift+Enter` inserts a newline and sends nothing (FR-017)
- [X] T027 [P] [US4] Add a failing test that the send button sends, and that an empty or whitespace-only value sends nothing by any of the three routes (FR-018, FR-022)
- [X] T028 [P] [US4] Add a failing test that after a send the value is empty and the height is back to its initial value (FR-021)
- [X] T029 [P] [US4] Add a failing test that the composer stays disabled while `pending` or while history is loading (FR-019)

### Implementation for User Story 4

- [X] T030 [US4] Replace the `<input type="text">` at `frontend/src/components/ChatPanel.tsx:230-237` with a `<textarea>`, preserving the `aria-label`, the `disabled` expression and `.wiki-chat-foot-note` verbatim (FR-019, FR-020)
- [X] T031 [US4] Implement auto-grow in `frontend/src/components/ChatPanel.tsx` — reset height to `auto` **before** reading `scrollHeight`, then cap at 5 rows. Without the reset the box can only grow and never shrinks when text is deleted (FR-016). Makes T028 pass
- [X] T032 [US4] Implement the `keydown` handler in `frontend/src/components/ChatPanel.tsx`: `Enter` without Shift sends and calls `preventDefault()` — without it the question is sent *and* a newline lands in the box just cleared; `Shift+Enter` falls through. Makes T025, T026 pass
- [X] T033 [US4] Add the visible send button in `frontend/src/components/ChatPanel.tsx` and route all three send paths through one guard that rejects empty or whitespace-only input. Makes T027 pass (FR-018, FR-022)
- [X] T034 [P] [US4] Style the textarea and send button in `frontend/src/styles.css`, replacing the `input[type="text"]` rules at `:754-767` and keeping the existing focus and disabled treatments

**Checkpoint**: US1-US4 complete.

---

## Phase 7: User Story 5 — Use the chat on a narrow window (Priority: P3)

**Goal**: The chat stops silently vanishing below 1180px.

**Independent Test**: Narrow the window past the breakpoint, open the chat, ask a
question, dismiss it.

### Tests for User Story 5

- [X] T035 [P] [US5] In `frontend/tests/ChatPanel.test.tsx`, add failing tests that the toggle carries `aria-expanded` matching the open state, that Escape closes an open drawer, and that focus returns to the toggle on close (FR-025, FR-026)

### Implementation for User Story 5

- [X] T036 [US5] Add the drawer toggle and open/closed state to `frontend/src/components/ChatPanel.tsx`, with `aria-expanded`, Escape-to-close and focus return. Opening or closing must not reset the conversation, the pinned state or the composer contents. Makes T035 pass
- [X] T037 [US5] In `frontend/src/styles.css:769-771`, replace `#wiki-chat-root { display: none }` with the overlay treatment — toggle visible below the breakpoint, panel fixed at full window height above the content when open (FR-023, FR-024)
- [X] T038 [US5] Verify in a real browser per quickstart § 2 check 5: at 1000px width the toggle is visible, opening covers the content, Escape closes and returns focus

**Checkpoint**: All five user stories independently functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T039 [P] Confirm `frontend/src/components/ChatPanel.tsx` calls none of `matchMedia`, `ResizeObserver`, or `Element.scrollTo` — all undefined in jsdom 25, and reduced motion is handled in CSS only (contract § 4)
- [X] T040 Run `npm run build` in `frontend/` and stage the regenerated `src/doc_generator/assets/wiki-ui.js` and `wiki-ui.css` — committed build artifacts that the Python tests serve (quickstart § 5)
- [X] T041 Run `cd frontend && npm test` — all suites green, with the existing ChatPanel coverage **unweakened** (FR-029, SC-008)
- [X] T042 Run `pytest --basetemp=<scratchpad> -p no:cacheprovider`. This feature touches no Python, so the suite is a pure regression signal: 667 green plus the known Groq-availability flake, identified by failure text naming `groq:...: available`. Anything else is real
- [X] T043 Confirm SC-009 by diffing generated output against a pre-change build; both builds must index the same repository at the same absolute path, or embedded absolute source paths make files differ for that reason alone
- [ ] T044 **(OPEN — needs human eyes)** Execute the manual pass in [quickstart.md](./quickstart.md) § 3 — reduced motion and dark mode in particular, which no automated check here covers

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no dependencies. T001 blocks US2's tests specifically.
- **Phase 2 (Foundational)**: blocks US3 only — see the scope note in that phase.
- **Phase 3 (US1)**: depends on nothing. Could be done first.
- **Phase 4 (US2)**: depends on T006 (`scroll-padding-top`) for correct
  positioning, and on T001 for its tests.
- **Phases 5-7**: depend on Phase 2.
- **Phase 8**: depends on every story you intend to ship.

### Story dependencies — the honest version

- **US1 → US2 is a hard ordering, and they are one release.** US1 relocates the
  scroll container, which is exactly what fragment navigation depends on.
  Shipping US1 without US2 fixes the composer and breaks every anchor in the
  wiki: a net loss, the same shape as 034's two P1 stories.
- **US3, US4 and US5 all write to `ChatPanel.tsx`.** They are independently
  testable and reviewable, but not independently authorable in parallel.
- **US4 and US5 do not depend on US3**, or on each other, once Phase 2 lands.

### Parallel Opportunities

Genuinely parallel, because they touch different files:

- **T001** (`setup.ts`) alongside **T002** (test file)
- **US1's CSS tasks** (`styles.css`) alongside **US2's handler** (`main.tsx`)
- **T023, T034** (`styles.css`) alongside any `ChatPanel.tsx` work
- Test-writing tasks within a phase — they append independent cases to
  `ChatPanel.test.tsx` and can be authored before the implementation

Not parallel despite appearances: T003, T019-T022, T030-T033, T036 — all one
file, `ChatPanel.tsx`. Likewise T005-T007, T023, T034, T037 — all `styles.css`.

---

## Parallel Example: the two P1 stories

```bash
# Different files, no shared state:
Task: "T005-T007 shell scroll regions in frontend/src/styles.css"
Task: "T012 fragment handler in frontend/src/main.tsx"
```

---

## Implementation Strategy

### MVP scope

**Phases 1-4** — both P1 stories. US1 alone is not shippable: it fixes the
reported defect and simultaneously breaks anchor navigation across the whole
wiki. The two are one release boundary.

1. Phase 1 + Phase 2 → scaffolding and the stable container, no behaviour change
2. Phase 3 → the composer is reachable (anchors now broken)
3. Phase 4 → anchors work again
4. **STOP and VALIDATE**: quickstart § 2 checks 1-4, in a real browser
5. Ship

### Incremental delivery

- MVP → validate → ship
- Add US3 (follow/jump) → validate → ship
- Add US4 (composer) → validate → ship
- Add US5 (drawer) → validate → ship
- T040 belongs in **every** commit that touched `frontend/src`, or the committed
  bundle goes stale

---

## Notes

- `[P]` = different file, no dependency on incomplete work
- Verify each test fails before implementing against it — especially T014-T018,
  where an assertion on the wrong element passes trivially
- The browser checks (T008, T013, T038) are not optional extras: they are the
  only evidence for SC-001, SC-002 and SC-003, and jsdom is structurally
  incapable of providing it
