---

description: "Task list template for feature implementation"
---

# Tasks: Chat Interface Polish — Activity Feedback, Rich Rendering & Shareable Sessions

**Input**: Design documents from `/specs/028-chat-interface-polish/`

**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required for user stories), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Included — this project's established convention (specs 014–027) is to cover every user-facing behavior change with Vitest/Testing Library coverage in `frontend/tests/`, and `quickstart.md`'s "Automated coverage" section for this feature names the exact test files to extend/add.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P3) so each can be implemented and verified independently, in order.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact and relative to the repository root

## Path Conventions

This feature is frontend-only (plan.md Structure Decision): all paths are
under `frontend/` (`frontend/src/...`, `frontend/tests/...`). No backend
(`src/chat*`, `tests/`) file is touched.

---

## Phase 1: Setup

**Purpose**: Bring in the one new toolchain requirement shared across the
feature (only User Story 2 imports these packages, but adding them once up
front avoids every story branch needing its own dependency-install step).

- [X] T001 [P] Add `react-markdown`, `remark-gfm`, `rehype-highlight`, and `lowlight` to `frontend/package.json` dependencies, then run `npm install` in `frontend/` (research.md Decision 2)

---

## Phase 2: Foundational

**Purpose**: Blocking prerequisites shared by all user stories.

None. Research (`research.md`) and the data model (`data-model.md`) confirm
the three user stories are independent slices of the same, already-tested
`frontend/src/components/ChatPanel.tsx` baseline (specs 014–027): US1 only
touches indicator/delivery-state logic, US2 only touches answer-content
rendering, US3 only touches session-id persistence. No shared type,
migration, or infrastructure change is needed before story work can start —
proceed directly to Phase 3 once Phase 1 completes.

**Checkpoint**: Setup complete — user story implementation can begin, in
priority order (recommended) or in parallel if staffed separately.

---

## Phase 3: User Story 1 - Know the assistant is working the instant a question is sent (Priority: P1) 🎯 MVP

**Goal**: A visible activity indicator appears the instant a question is
submitted, stays up until the first answer fragment arrives, then gives way
to the answer building up progressively; a failure mid-stream replaces the
indicator/partial answer with a clear error instead of stalling forever.

**Independent Test**: Submit a question and confirm a visible "working"
signal appears immediately, stays visible until the first piece of the
answer is ready, and is then replaced by the answer itself growing
progressively until complete (spec.md User Story 1 Independent Test).

### Tests for User Story 1

> Write these first; they should fail against the current `ChatPanel.tsx` (which renders the pending assistant message as an empty `<p>` with no indicator) before the implementation tasks below make them pass.

- [X] T002 [P] [US1] Add test "shows a visible activity indicator immediately after a question is submitted, before any fragment arrives" to `frontend/tests/ChatPanel.test.tsx` (assert the indicator element is present right after `askQuestionThroughUi(...)`, before resolving the mocked fetch's first read)
- [X] T003 [P] [US1] Add test "replaces the activity indicator with the answer content as soon as the first fragment arrives" to `frontend/tests/ChatPanel.test.tsx`, reusing the existing gated-fragment mock pattern (see the "renders the answer progressively..." test already in the file) to assert the indicator is gone and the first fragment's text is visible once it lands
- [X] T004 [P] [US1] Add test "replaces the indicator or a partial answer with a clear error message when the stream fails after starting" to `frontend/tests/ChatPanel.test.tsx` (send one fragment, then an `error` SSE event or a rejected read; assert no indicator/stalled bubble remains and the error text is shown)
- [X] T005 [P] [US1] Add test "transitions cleanly from indicator to answer with no leftover indicator artifact when the first fragment arrives immediately" to `frontend/tests/ChatPanel.test.tsx` (fragment available on the very first mocked `read()`; assert the indicator element is absent once content renders)

### Implementation for User Story 1

- [X] T006 [US1] In `frontend/src/components/ChatPanel.tsx`, add a `deliveryState: "awaiting-first-fragment" | "streaming" | "complete" | "error"` field to the `DisplayMessage` interface (data-model.md DisplayMessage) and set it to `"awaiting-first-fragment"` on the placeholder assistant message created in `handleSubmit`
- [X] T007 [US1] In `frontend/src/components/ChatPanel.tsx`, render a small activity-indicator element (e.g. `<span className="wiki-chat-indicator" aria-label="Generating an answer…">`) in place of the message body whenever `message.role === "assistant" && message.deliveryState === "awaiting-first-fragment"` (depends on T006)
- [X] T008 [US1] In `frontend/src/components/ChatPanel.tsx`, update the `onFragment` callback inside `handleSubmit` to set the last message's `deliveryState` to `"streaming"` alongside appending the fragment text, so the indicator swaps out on the very first call (depends on T006)
- [X] T009 [US1] In `frontend/src/components/ChatPanel.tsx`, set `deliveryState: "complete"` on the final assistant message object once `askQuestion` resolves, and confirm the existing catch-block behavior (dropping the optimistic user/assistant pair per FR-007) still leaves no stale indicator/partial bubble behind on failure (depends on T006)
- [X] T010 [P] [US1] Add `.wiki-chat-indicator` styling (e.g. an animated ellipsis) to `frontend/src/styles.css`

**Checkpoint**: User Story 1 is fully functional and independently testable — the indicator/streaming lifecycle works against the current plain-text rendering, before Markdown support (User Story 2) lands.

---

## Phase 4: User Story 2 - Read answers as formatted content, not an undifferentiated block of text (Priority: P2)

**Goal**: Assistant answers render as formatted Markdown — fenced code
blocks appear syntax-highlighted and visually distinct from prose, and
inline `path :: symbolId` references (the exact format `chat/prompting.py`'s
system prompt already asks the model to produce) render as clickable links
to the resolved documentation page, or as plain inline code when
unresolvable — reusing the exact same `findByCitation` lookup the separate
citation list already uses.

**Independent Test**: Ask a question whose answer includes both a code
snippet and at least one reference to a documented symbol or file, and
confirm the code renders visually distinct from prose, and the reference
renders as a working link to that item's documentation page (spec.md User
Story 2 Independent Test). Testable against any already-received answer
text, streamed or not, independent of User Story 1's indicator and User
Story 3's session persistence.

### Tests for User Story 2

- [X] T011 [P] [US2] Create `frontend/tests/markdownReferences.test.tsx` with unit tests for the reference-parsing logic per `contracts/inline-symbol-reference-rendering.md`: splits `"<path> :: <symbolId>"` correctly, returns no match for text without `" :: "`, resolves through a supplied `findByCitation`-style lookup (symbol-id match, then file-path fallback, then unresolved), and covers these malformed-input cases explicitly: an empty left segment (`" :: symbol"`), an empty right segment (`"path :: "`), and text containing more than one `"::"` (split on the *first* occurrence only, so the rest of the text stays part of the symbol-id side)
- [X] T012 [P] [US2] Add test "renders a fenced code snippet as visually distinct, syntax-highlighted code" to `frontend/tests/ChatPanel.test.tsx` (assert a code element carrying a `hljs`/`language-*` class exists, not a plain paragraph)
- [X] T013 [P] [US2] Add test "renders an in-answer `path :: symbolId` reference as a clickable link to its documentation page" to `frontend/tests/ChatPanel.test.tsx`, using the existing `SEARCH_ENTRIES` fixture and an answer body containing `` `src/auth/login.py :: auth.authenticate_user` `` inline — assert a link with the resolved `pageUrl` renders
- [X] T014 [P] [US2] Add test "renders an unresolvable in-answer reference as plain inline code, not a broken link" to `frontend/tests/ChatPanel.test.tsx` (FR-007)
- [X] T015 [P] [US2] Add test "renders a not-yet-closed code fence during streaming without crashing or breaking layout" to `frontend/tests/ChatPanel.test.tsx` (feed a partial ` ```python\ndef f(): ` fragment mid-stream and assert the panel still renders without throwing, per spec.md Edge Cases / Acceptance Scenario 4)
- [X] T016 [P] [US2] Add test "renders a truncated or malformed in-answer symbol reference as plain readable text without breaking the rest of the message" to `frontend/tests/ChatPanel.test.tsx` (feed an inline span cut off before its closing backtick mid-stream, e.g. `` `src/auth/login.py :: auth.authenticate `` with no closing backtick yet, and separately a span with a stray/duplicate `::`; assert the panel renders without throwing and the rest of the message is unaffected — spec.md Edge Cases, "malformed or incomplete... symbol reference")

### Implementation for User Story 2

- [X] T017 [US2] Create `frontend/src/lib/markdownReferences.tsx` exporting `parseReference(text: string): { filePath: string; symbolId: string } | null` (recognition rule from `contracts/inline-symbol-reference-rendering.md`) and a `createSymbolAwareCodeRenderer(entries: SearchIndexEntry[])` factory returning a `react-markdown` `code` component override: block code (has a `language-*` className) renders normally for `rehype-highlight` to style; inline code calls `parseReference`, resolves a match via the existing `findByCitation` from `../lib/searchIndex`, and renders `<a href={pageUrl}>{label}</a>` when resolved or a plain `<code>` otherwise (depends on T001)
- [X] T018 [US2] In the same `frontend/src/lib/markdownReferences.tsx` module, configure `rehype-highlight` with a curated `lowlight` language subset (Python, JavaScript/TypeScript, plus a generic fallback) per research.md Decision 2, and export it alongside the renderer for `ChatPanel` to use (depends on T017)
- [X] T019 [US2] In `frontend/src/components/ChatPanel.tsx`, replace the assistant message's plain `<p>{message.content}</p>` with `<ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[configuredRehypeHighlight]} components={{ code: symbolAwareCodeRenderer }}>{message.content}</ReactMarkdown>` (user messages keep plain text — only generated answers need structured rendering) (depends on T017, T018)
- [X] T020 [P] [US2] Add code-block and inline-reference styling (`.wiki-chat-message pre`, `.wiki-chat-message code`, highlight.js theme overrides) to `frontend/src/styles.css`

**Checkpoint**: User Story 2 is fully functional and independently testable — structured rendering and clickable in-answer references work regardless of how the session id is carried (User Story 3, not yet implemented) or exactly how the indicator behaves (User Story 1).

---

## Phase 5: User Story 3 - Reload the page mid-conversation without losing it (Priority: P3)

**Goal**: The current conversation's session id lives in the page's own URL
(`?chatSession=<id>`, `contracts/session-url-parameter.md`) instead of
`localStorage`, so a reload, a copied link, or a different browser/device
all restore the full conversation — with the question input staying
disabled until that history fetch resolves one way or the other.

**Independent Test**: Start a conversation, ask at least one question,
reload the page, and confirm the complete prior exchange reappears before
any new question is asked — then copy the page's own address, open it
fresh, and confirm it lands on that same conversation (spec.md User Story 3
Independent Test).

### Tests for User Story 3

- [X] T021 [P] [US3] Replace the existing "resumes a session id stored in local storage" test in `frontend/tests/ChatPanel.test.tsx` with one that sets `?chatSession=session-1` on the test's URL (via `window.history.pushState`) instead of `window.localStorage.setItem`, and asserts history loads and no session is re-created
- [X] T022 [P] [US3] Add test "writes the newly created session id onto the page URL when the first question is asked with no id present" to `frontend/tests/ChatPanel.test.tsx` (assert `window.location.search` contains `chatSession=session-1` after the ask completes, with no page navigation/reload)
- [X] T023 [P] [US3] Replace the existing "falls back to creating a new session when the stored id no longer resolves" test in `frontend/tests/ChatPanel.test.tsx` with one driven by an unresolvable `?chatSession=stale-session` URL parameter, asserting the parameter is cleared from the URL and a fresh conversation starts (FR-011)
- [X] T024 [P] [US3] Add test "question input stays disabled until the mount-time history fetch settles" to `frontend/tests/ChatPanel.test.tsx` (FR-010 — with a `chatSession` param present, assert the input is disabled immediately after mount and only becomes enabled once the history `fetch` resolves)

### Implementation for User Story 3

- [X] T025 [US3] In `frontend/src/components/ChatPanel.tsx`, remove the `SESSION_STORAGE_KEY`/`localStorage` read-write logic and introduce a `CHAT_SESSION_PARAM = "chatSession"` constant plus a mount effect that reads `new URLSearchParams(window.location.search).get(CHAT_SESSION_PARAM)` in place of the old `localStorage.getItem` call
- [X] T026 [US3] In `frontend/src/components/ChatPanel.tsx`, add a `historyLoadState: "idle" | "loading" | "loaded" | "not-found"` state (data-model.md ConversationUrlState) — `"loading"` while a present `chatSession` id's history fetch is outstanding — and combine it with the existing `pending` flag so the form's `disabled` condition covers both cases (FR-010) (depends on T025)
- [X] T027 [US3] In `frontend/src/components/ChatPanel.tsx`, on a `session_not_found` response from `getHistory()`, clear the id from the URL via `window.history.replaceState(null, "", <url with chatSession removed>)` and set `historyLoadState` to `"not-found"` (FR-011) (depends on T025, T026)
- [X] T028 [US3] In `frontend/src/components/ChatPanel.tsx`, after `createSession()` succeeds inside `handleSubmit`, write the new id onto the current URL via `window.history.replaceState(null, "", <url with chatSession=newId>)`, preserving the rest of the current path/query string (FR-008, FR-009) (depends on T025)

**Checkpoint**: All three user stories are independently functional; the full acceptance flow described in spec.md (indicator → streaming → formatted answer with clickable references → survives reload/copy) now works end-to-end.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation upkeep and final validation across all three stories.

- [X] T029 [P] Update the "Frontend (Wiki UI)" section of `docs/stack.md` to list the new client dependencies (`react-markdown`, `remark-gfm`, `rehype-highlight`, `lowlight`) and why they were added
- [X] T030 [P] Update the `frontend/` (`wiki-ui`) row/description in `docs/architecture.md` to mention structured answer rendering (code + clickable in-text symbol references) and the URL-persisted, shareable session id
- [X] T031 [P] Review `README.md`'s frontend-related sections and update them if any documented behavior (e.g. what the chat panel does, how a session is resumed) changed
- [X] T032 [P] Review `docs/diagrams/`, `.gitignore`, and `pyproject.toml` for any updates this feature requires (expected to be a no-op for a frontend-only change with no new build artifact or Python dependency; update only if something is actually found)
- [X] T033 Confirm the pre-existing "renders the answer progressively as fragments arrive" test and the pre-existing separate-citation-list tests (resolvable and unresolvable) in `frontend/tests/ChatPanel.test.tsx` still pass unmodified after the `deliveryState` (US1) and Markdown-rendering (US2) changes — explicit regression check for FR-003 and FR-012, since neither is touched by a dedicated task above
- [X] T034 Run `npm run test` and `npm run build` in `frontend/` to confirm the full suite (including T033's regression check) passes and the bundle builds cleanly with all three stories implemented
- [ ] T035 Execute the manual scenarios in `quickstart.md` end-to-end against a running local server (indicator/streaming, structured rendering + link, reload/copy-URL/invalid-id)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Empty — no blocking prerequisites beyond Setup.
- **User Stories (Phase 3-5)**: Each depends only on Phase 1 completing (dependency install for US2's imports to resolve; US1 and US3 don't even need Phase 1). They touch non-overlapping concerns within the same two files (`ChatPanel.tsx`, `styles.css`) and are safe to implement in priority order (recommended, to keep diffs reviewable) or in parallel by different people.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: No dependency on US2 or US3 — indicator/delivery-state logic is independent of how content is formatted or how the session id is stored.
- **User Story 2 (P2)**: No dependency on US1 or US3 — Markdown/reference rendering applies to `message.content` regardless of delivery state or session-id source.
- **User Story 3 (P3)**: No dependency on US1 or US2 — session-id persistence and history gating are independent of indicator/formatting behavior.

### Within Each User Story

- Tests are written first and should fail against the current baseline.
- Within US1: T006 (type) before T007-T009 (behavior using it); T010 (CSS) is independent.
- Within US2: T017 (parser/renderer) before T018 (highlight config using it) before T019 (wiring into `ChatPanel.tsx`); T020 (CSS) is independent.
- Within US3: T025 (URL read) before T026-T028 (state/behavior built on it).

### Parallel Opportunities

- All tests within a single user story phase (marked `[P]`) can be written in parallel — they land in the same file but as independent `it(...)` blocks with no shared mutable state.
- T010 (US1 CSS), T020 (US2 CSS) can proceed in parallel with that story's implementation tasks once the markup they style exists.
- T029-T032 (Polish documentation tasks) can all run in parallel.
- Once Phase 1 completes, the three user story phases (3, 4, 5) can be picked up by different people in parallel, since none shares an implementation task with another — only the final merge into `ChatPanel.tsx`/`styles.css` needs normal sequencing/rebasing.

---

## Parallel Example: User Story 1

```bash
# Tests for User Story 1 (independent it() blocks in the same file):
Task: "Add test 'shows a visible activity indicator immediately...' to frontend/tests/ChatPanel.test.tsx"
Task: "Add test 'replaces the activity indicator with the answer content...' to frontend/tests/ChatPanel.test.tsx"
Task: "Add test 'replaces the indicator or a partial answer with a clear error...' to frontend/tests/ChatPanel.test.tsx"
Task: "Add test 'transitions cleanly from indicator to answer...' to frontend/tests/ChatPanel.test.tsx"
```

## Parallel Example: User Story 2

```bash
Task: "Create frontend/tests/markdownReferences.test.tsx with reference-parsing unit tests"
Task: "Add test 'renders a fenced code snippet as visually distinct, syntax-highlighted code' to frontend/tests/ChatPanel.test.tsx"
Task: "Add test 'renders an in-answer path :: symbolId reference as a clickable link...' to frontend/tests/ChatPanel.test.tsx"
Task: "Add test 'renders an unresolvable in-answer reference as plain inline code...' to frontend/tests/ChatPanel.test.tsx"
Task: "Add test 'renders a not-yet-closed code fence during streaming...' to frontend/tests/ChatPanel.test.tsx"
Task: "Add test 'renders a truncated or malformed in-answer symbol reference...' to frontend/tests/ChatPanel.test.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Phase 2: nothing to do
3. Complete Phase 3: User Story 1 (T002-T010)
4. **STOP and VALIDATE**: run `frontend/tests/ChatPanel.test.tsx`, then manually confirm Scenario 1 in `quickstart.md`
5. This alone already resolves the single biggest perceived-quality gap named in spec.md's Why-this-priority rationale for User Story 1

### Incremental Delivery

1. Setup → nothing to validate yet
2. Add User Story 1 → validate → the chat now always shows either an active indicator or growing content, never a silent disabled state
3. Add User Story 2 → validate → answers with code/references now render as structured, clickable content
4. Add User Story 3 → validate → a reload or a copied link now restores the full conversation
5. Phase 6 → documentation + full-suite validation

### Parallel Team Strategy

With three developers: complete Phase 1 together, then one developer per
user story phase (3, 4, 5) in parallel — none of the three touches an
overlapping implementation task, only the same two files, so normal
rebase/merge discipline on `ChatPanel.tsx` and `styles.css` is all that's
needed to integrate.
