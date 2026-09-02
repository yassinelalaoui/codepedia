# Implementation Plan: Chat Panel Layout — Reach the Input Without Scrolling

**Branch**: `035-chat-panel-layout` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/035-chat-panel-layout/spec.md`

## Summary

The chat column stretches to the height of the whole document rather than the
window, so its composer sits at the bottom of the *page* instead of the bottom of
the *screen*. Reading an answer and typing a question means scrolling between
them every time.

The panel's own internals have never been wrong — `.wiki-chat-messages` is
already `flex: 1; overflow-y: auto` and the form is already `flex: none`. They
simply divide a height that is currently unbounded. Giving the column a bounded
height is the whole of User Story 1, and it costs four CSS declarations.

The rest of the feature is what that change endangers or enables: fragment
navigation must keep working now that `.main` is the scroll container rather than
the document; the message list should follow a streaming answer without yanking a
reader who has scrolled up; the composer becomes a multi-line textarea; and the
chat stops silently vanishing below 1180px.

Three findings from Phase 0 shape the design:

1. **`scrollIntoView` and `Element.scrollTo` are both `undefined` in jsdom 25** —
   measured, not assumed. Auto-scroll therefore writes `scrollTop`, which is
   also the simplest correct answer in a real browser, so nothing is traded away.
2. **The fragment handler genuinely wants `scrollIntoView`**, and guarding it
   with `typeof` would reproduce feature 034's defect exactly: there, a guard
   around `setPointerCapture` hid a real bug from every test in the suite. So the
   guard stays, but `tests/setup.ts` stubs the API — turning a blindfold into an
   assertable call.
3. **The message list is rendered conditionally today** (`ChatPanel.tsx:189`), so
   there is no stable element to hold a scroll ref. One always-rendered container
   is introduced, which removes a whole class of ordering bug rather than
   working around it.

## Technical Context

**Language/Version**: TypeScript 5.6, React 18.3. **No Python at all** — the
first feature in this repository to touch none.

**Primary Dependencies**: None added. React and the existing chat client only.

**Storage**: N/A. Nothing persisted — no manifest row, no generated file, no
browser storage. All state is React state for the lifetime of a page view.

**Testing**: Vitest 2.1 + jsdom 25 (`frontend/tests/`), plus the headless-Chrome
CDP harness established in 034 for everything geometric.

**Target Platform**: Desktop browsers, including pages opened over `file://` with
no network.

**Project Type**: Web — the browser-side half of a static wiki generator.

**Performance Goals**: Auto-scroll and composer resize run on input and on
message arrival, not on a continuous observer; nothing here runs per frame.

**Constraints**: Generated pages byte-identical (FR-028, SC-009). Every existing
chat capability preserved (FR-029). No new runtime dependency (constitution 2.2).

**Scale/Scope**: 3 files modified, 1 test-setup file extended, 1 test file
extended. Roughly 120 lines of TSX and 70 of CSS.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Assessed against constitution v3.0.0.

| Principle | Applies? | Assessment |
| --- | --- | --- |
| **2.1** Remote engine by default, local mode explicit | No | Consumes no model. Changes how the chat panel is *laid out*, never how an answer is produced. |
| **2.2** Zero network exposure by default | **Yes — neutral** | No new dependency, no CDN, no webfont, no asset. The drawer and jump affordance are hand-written, like 034's viewport. Everything still works over `file://`. |
| **2.3** Automatic fallback within a configured chain | No | No provider involved. |
| **2.4** Traceability of AI answers | **Yes — preserved** | Citation rendering is untouched (FR-029); the contract lists it under unchanged surfaces. |
| **2.5** Incremental re-indexing | **Yes — neutral** | No page content changes, so no content hash moves and no page regenerates. |
| **2.6** Minimal infrastructure, local storage | **Yes — neutral** | No storage of any kind added. |
| **2.7** Analysed repository read-only | **Yes — neutral** | No new writes. The only new output bytes are the rebuilt `wiki-ui.{js,css}`, already-managed assets. |

**Initial gate: PASS.** No violations, so the Complexity Tracking section is
removed rather than left empty.

### Post-Design Re-check (after Phase 1)

- **2.2 holds and is unchanged by the design.** Research Decisions 4 and 9 both
  rejected heavier options — a hand-computed scroll geometry and the Fullscreen
  API / `<dialog>` respectively — in favour of what the platform already
  provides. Nothing was added to `package.json`.
- **2.5 confirmed neutral.** `data-model.md` § "What this feature does not touch"
  names every Python surface as unchanged; the Python suite is a pure regression
  check.
- **2.4 confirmed preserved.** The contract's § 5 lists citation rendering,
  streaming and session handling as untouched, with the existing tests as the
  evidence.
- **No new gate triggered.** The design added no provider call, no persisted
  state, and no network path.

**Post-design gate: PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/035-chat-panel-layout/
├── plan.md              # This file
├── spec.md              # 5 user stories, 29 FRs, 9 SCs
├── research.md          # Phase 0 — 9 decisions, each with its probe
├── data-model.md        # Phase 1 — in-memory state, DOM shape, constants
├── quickstart.md        # Phase 1 — unit / real-browser / manual, in that order of authority
├── checklists/
│   └── requirements.md  # Spec quality checklist (16/16)
├── contracts/
│   └── chat-panel-shell.md   # Phase 1 — shell CSS, ChatPanel, fragment handler
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── components/
│   │   └── ChatPanel.tsx      # MODIFIED — stable scroll container, pinned state,
│   │                          #   textarea composer, jump affordance, drawer toggle
│   ├── styles.css             # MODIFIED — shell scroll regions, composer, jump
│   │                          #   affordance, drawer; scroll-behavior relocated
│   └── main.tsx               # MODIFIED — fragment handler on load + hashchange
└── tests/
    ├── setup.ts               # MODIFIED — scrollIntoView stub (research Decision 4)
    └── ChatPanel.test.tsx     # MODIFIED — 4 label queries adapt; new coverage added

src/doc_generator/assets/
├── wiki-ui.js                 # REBUILT + COMMITTED
└── wiki-ui.css                # REBUILT + COMMITTED
```

**Structure Decision**: Entirely within the existing `frontend/` half of the
repository's Python-generator / browser-bundle split. No new file is introduced:
the fragment handler is a few lines in `main.tsx` beside the enhancer wiring
added by 034, and everything else belongs to `ChatPanel` or the stylesheet.

This is the first feature here to touch no Python, which is what makes FR-028 and
SC-009 true by construction rather than by test — and makes the whole Python
suite a clean regression signal.

## Implementation Order

1. **Shell CSS** — the four declarations plus the `scroll-behavior` relocation.
   This alone delivers User Story 1 and is independently verifiable in a browser
   before any component changes.
2. **Fragment handler** (US2) — the regression guard for what step 1 endangers.
   Immediately after, not later: step 1 is what breaks anchors, and shipping the
   two apart means shipping a wiki with broken anchors.
3. **Stable scroll container + pinned state + jump affordance** (US3).
4. **Textarea composer** (US4).
5. **Narrow-window drawer** (US5).
6. `npm run build`, stage the regenerated assets, both suites, then the
   real-browser pass in `quickstart.md` § 2.

**Steps 1 and 2 are one release boundary**, for the same reason 034's two P1
stories were: step 1 without step 2 fixes the composer and breaks every anchor
link in the wiki, which is a net loss.

## Risks

| Risk | Mitigation |
| --- | --- |
| `min-height: 0` omitted, so the column still grows | Called out in the contract as mandatory with the reason; caught by the real-browser check that the document does not scroll |
| Anchors break when `.main` becomes the scroll container | Explicit fragment handler, plus a `scrollIntoView` stub so the path is exercised in tests rather than skipped; verified for real position in a browser |
| `scroll-behavior` silently lost | It moves rather than being deleted; the reduced-motion guard moves with it |
| Auto-scroll fights the reader | `isPinned` is *derived* from scroll position, never toggled inside its own handler — a toggle here loops |
| A guard hides a defect from every test | The 034 lesson, applied directly: stub the missing API in `setup.ts` so the guarded path runs under test |
| jsdom geometry proves nothing | All-zero rects are documented; every geometric requirement is on the real-browser list in `quickstart.md` § 2 |
| Existing chat tests weakened to fit | The contract lists them as unchanged surfaces; only the four label queries adapt, and only because the element type changed |
| Stale committed bundle | Quickstart § 5 checks `git status` on the assets before commit |
