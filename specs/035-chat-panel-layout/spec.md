# Feature Specification: Chat Panel Layout — Reach the Input Without Scrolling

**Feature Branch**: `035-chat-panel-layout`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "Chat panel layout: stop scrolling to reach the input. Symptom: reading an answer and typing a question means scrolling up and down the page every time. The composer sits at the bottom of the whole document rather than the bottom of the viewport. Root cause: `.shell` is `min-height:100vh` with the document scrolling, so `#wiki-chat-root` stretches to the height of the whole grid row and `.wiki-chat-panel` is `height:100%` of that — the panel's internals are already correct (`.wiki-chat-messages` is `flex:1; overflow-y:auto`, the form is `flex:none`) but never receive a bounded height to divide. Make the chat column viewport-height and independently scrollable, keep anchor links working when `.main` becomes the scroll container, auto-scroll to the newest message only while pinned to the bottom with a jump-to-latest affordance otherwise, replace the single-line input with an auto-growing textarea (Enter to send, Shift+Enter for newline, visible send button), and replace `#wiki-chat-root { display:none }` below 1180px with a docked drawer."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a question without hunting for the box (Priority: P1)

A reader is partway down a long module page and wants to ask about what they are
looking at. Today the question box is at the bottom of the *entire document*, so
they scroll to the end of the page to type, then scroll back to find the answer,
then scroll down again for the next question.

**Why this priority**: This is the reported defect, and the whole reason the
feature exists. Nothing else here matters if the box is still out of reach.

**Independent Test**: Open the longest page in a generated wiki, scroll to the
middle, and type a question without scrolling the page at all.

**Acceptance Scenarios**:

1. **Given** any page, however long, **When** it is displayed, **Then** the chat
   header, the message area and the question box are all visible without
   scrolling the page.
2. **Given** a reader scrolled to the middle of a long page, **When** they look
   at the chat column, **Then** the question box is in exactly the same place on
   screen as it was at the top of the page.
3. **Given** a long conversation, **When** the reader scrolls the message list,
   **Then** only the message list moves — the header stays at its top, the
   question box stays at its bottom, and the page content does not move.
4. **Given** a reader scrolling the page content, **When** the content scrolls,
   **Then** the chat column does not move with it.

---

### User Story 2 - Jump to a heading and land on it (Priority: P1)

Readers reach a specific heading two ways: the "On this page" rail in the
sidebar, and a search result that points at a symbol partway down another page.
Both must still land on the right heading once the page content scrolls inside
its own column rather than as the whole document.

**Why this priority**: A regression guard on an already-shipped capability. This
change moves the scrolling container, which is exactly the thing fragment
navigation depends on. A release that fixed the chat box but broke every anchor
in the wiki would be a net loss.

**Independent Test**: Click an entry in the "On this page" rail and confirm the
heading is scrolled to. Separately, from a *different* page, open a search result
pointing at a symbol and confirm the freshly-loaded page lands on that symbol.

**Acceptance Scenarios**:

1. **Given** a page with an "On this page" rail, **When** the reader clicks an
   entry, **Then** the matching heading scrolls into view, not flush against the
   very top edge.
2. **Given** a search result naming a symbol on another page, **When** the reader
   opens it, **Then** the newly-loaded page is already scrolled to that symbol.
3. **Given** the reader has jumped to a heading, **When** they read on, **Then**
   the rail continues to highlight the section they are currently in.
4. **Given** a reader who has asked for reduced motion, **When** they use either
   route, **Then** the jump is immediate rather than animated.

---

### User Story 3 - Follow an answer, or read back without being yanked (Priority: P2)

An answer arrives progressively. The reader usually wants to follow the newest
text. Sometimes they scroll up mid-answer to re-read something earlier, and the
view must then stay where they put it.

**Why this priority**: A real improvement, but with story 1 delivered the reader
can already scroll the message list themselves. It is comfort, not the fix.

**Independent Test**: Ask a question and watch the answer arrive without touching
anything; then ask another and scroll up while it arrives.

**Acceptance Scenarios**:

1. **Given** the message list is at the bottom, **When** a new message arrives or
   an answer grows, **Then** the newest content scrolls into view automatically.
2. **Given** the reader has scrolled up to read an earlier message, **When** an
   answer is still arriving, **Then** the view does not move.
3. **Given** the reader has scrolled up and new content has arrived below,
   **When** they look at the message list, **Then** an affordance offers to take
   them to the newest message.
4. **Given** that affordance, **When** the reader activates it, **Then** the list
   scrolls to the newest message and resumes following automatically.

---

### User Story 4 - Write a question longer than one line (Priority: P2)

A useful question about code often needs more than one line — a snippet, or two
sentences. Today the box is a single line that scrolls sideways.

**Why this priority**: Improves the quality of questions a reader can ask, but a
one-line question still works today.

**Independent Test**: Type a multi-line question, confirm the box grows, send it
with the keyboard, and separately send it with the button.

**Acceptance Scenarios**:

1. **Given** the question box, **When** the reader types past one line, **Then**
   the box grows to fit, up to a limit, after which it scrolls internally.
2. **Given** text in the box, **When** the reader presses Enter, **Then** the
   question is sent.
3. **Given** text in the box, **When** the reader presses Shift+Enter, **Then** a
   newline is inserted and nothing is sent.
4. **Given** a question is being answered, **When** the reader looks at the box,
   **Then** it is visibly unavailable, exactly as it is today.
5. **Given** the reader prefers the mouse, **When** they look at the composer,
   **Then** a send button is visible and sends the question.
6. **Given** a sent question, **When** it has been sent, **Then** the box is
   empty and back to its one-line height.

---

### User Story 5 - Use the chat on a narrow window (Priority: P3)

A reader narrows the browser window, or works on a smaller screen. Today the chat
panel silently disappears entirely.

**Why this priority**: Affects fewer sessions than the others, and the reader can
widen the window. But silent disappearance is a bad failure: nothing tells them
the feature still exists.

**Independent Test**: Narrow the window until the chat column would no longer
fit, then still open the chat, ask a question, and dismiss it.

**Acceptance Scenarios**:

1. **Given** a window too narrow for a docked chat column, **When** the page is
   displayed, **Then** a visible control offers to open the chat.
2. **Given** that control, **When** it is activated, **Then** the chat opens over
   the content at full height and behaves as it does when docked.
3. **Given** the chat is open over the content, **When** the reader presses
   Escape or activates the control again, **Then** it closes and keyboard focus
   returns to the control.
4. **Given** the chat is open on a narrow window, **When** assistive technology
   reads the control, **Then** it reports whether the chat is currently open.

---

### Edge Cases

- **An empty conversation**: the placeholder still fills the middle of the panel
  and the question box is still pinned at the bottom.
- **A single message longer than the panel**: it scrolls within the message list;
  the header and the box do not move.
- **A very long question in the box**: the box stops growing at its limit and
  scrolls its own content rather than pushing the message list off screen.
- **Sending while the message list is scrolled up**: sending a question is a
  deliberate act, so the view returns to the newest message.
- **A page shorter than the window**: nothing scrolls, and the layout is
  unchanged from today.
- **A fragment pointing at a heading that no longer exists**: the page opens
  normally at the top rather than failing.
- **Reduced motion**: no smooth scrolling anywhere, including auto-scroll and
  anchor jumps.
- **A very short window** (a laptop with browser chrome and a bookmarks bar): the
  question box remains visible; the message list absorbs the loss of height.
- **The chat is unavailable** (opened without the access token): the error is
  visible without scrolling, and the composer keeps its existing behaviour.

## Requirements *(mandatory)*

### Functional Requirements

#### Layout

- **FR-001**: The chat column MUST occupy exactly the height of the window and
  MUST NOT grow with the length of the page.
- **FR-002**: Within the chat column, the header MUST stay at the top and the
  composer MUST stay at the bottom, with the message list taking the remaining
  space and scrolling on its own.
- **FR-003**: The page content MUST scroll independently of the chat column and
  of the navigation sidebar; scrolling one MUST NOT move the others.
- **FR-004**: The navigation sidebar MUST keep its own independent scrolling.
- **FR-005**: The page MUST NOT scroll as a whole document; no combination of
  content length and conversation length may push the composer off screen.

#### Fragment navigation

- **FR-006**: Activating an entry in the "On this page" rail MUST scroll the
  matching heading into view within the content column.
- **FR-007**: Opening a link that names a heading on another page MUST leave the
  newly-loaded page already scrolled to that heading.
- **FR-008**: A heading reached by either route MUST NOT sit flush against the
  top edge of the content column.
- **FR-009**: The rail MUST continue to indicate which section the reader is
  currently in as they scroll.
- **FR-010**: A fragment naming a heading that does not exist MUST leave the page
  displayed normally rather than failing.

#### Message list behaviour

- **FR-011**: When the message list is already at its newest message, new content
  — including an answer arriving progressively — MUST be scrolled into view
  automatically.
- **FR-012**: When the reader has scrolled away from the newest message, arriving
  content MUST NOT move their view.
- **FR-013**: While the reader is scrolled away and newer content exists below,
  the system MUST offer a visible affordance to reach the newest message.
- **FR-014**: Activating that affordance MUST scroll to the newest message and
  resume automatic following.
- **FR-015**: Sending a question MUST return the view to the newest message
  regardless of where the reader had scrolled.

#### Composer

- **FR-016**: The question box MUST accept multi-line input and MUST grow with
  its content up to a bounded height, scrolling internally beyond it.
- **FR-017**: Enter MUST send the question; Shift+Enter MUST insert a newline
  without sending.
- **FR-018**: A visible send control MUST be present and MUST send the question.
- **FR-019**: The composer MUST remain unavailable while an answer is pending and
  while a conversation is still loading, exactly as it is today.
- **FR-020**: The existing accessible label of the question box and the existing
  privacy note beneath it MUST be preserved unchanged.
- **FR-021**: After sending, the box MUST be empty and back to its initial
  height.
- **FR-022**: An empty or whitespace-only question MUST NOT be sent, by any
  route.

#### Narrow windows

- **FR-023**: Where the window is too narrow for a docked chat column, the chat
  MUST remain reachable rather than being hidden.
- **FR-024**: The chat MUST then open over the page content at full window
  height, with the same internal behaviour as when docked.
- **FR-025**: It MUST be dismissible by Escape and by the control that opened it,
  returning keyboard focus to that control.
- **FR-026**: The control MUST report its open or closed state to assistive
  technology.

#### Preservation

- **FR-027**: Reduced-motion preferences MUST be honoured for every scroll this
  feature introduces or relocates.
- **FR-028**: The generated Markdown and HTML pages MUST be unchanged by this
  feature; it alters only the browser-side presentation and behaviour.
- **FR-029**: Every existing chat capability — conversation history, resuming a
  conversation from its link, citations, streaming indicators, and error
  reporting — MUST continue to work unchanged.

### Key Entities

- **Scroll regions**: three independent scrollable areas — the navigation
  sidebar, the page content, and the chat message list — replacing today's single
  document scroll. Each owns its own scroll position; none affects the others.
- **Pinned-to-bottom state**: whether the message list is currently showing its
  newest message. Decides whether arriving content scrolls into view or is
  announced by the jump affordance instead.
- **Composer state**: the pending question text, its current height up to a
  bound, and whether input is currently accepted. Already partly present; this
  feature adds only height and multi-line handling.
- **Narrow-window disclosure state**: whether the chat is currently open over the
  content, and which control to return focus to when it closes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reader can ask a question from any scroll position on the longest
  page in a generated wiki with **zero** page scrolling.
- **SC-002**: The composer is visible at all times, for every combination of page
  length and conversation length.
- **SC-003**: 100% of fragment links that land correctly today still land
  correctly — both the "On this page" rail and cross-page search results —
  verified in a real browser, not only in a test harness.
- **SC-004**: An answer arriving progressively stays in view without any reader
  action, in 100% of cases where the reader has not scrolled away.
- **SC-005**: Zero unrequested view movements while the reader is scrolled away
  from the newest message.
- **SC-006**: A reader can compose and send a question of at least five lines
  without the message list being pushed out of view.
- **SC-007**: The chat is reachable at every window width; there is no width at
  which it silently disappears.
- **SC-008**: Every existing chat behaviour still passes its current tests
  without those tests being weakened.
- **SC-009**: Generated page files are byte-identical to what the same repository
  produced before this change.

## Assumptions

Recorded because the feature description settled them in advance. They constrain
the solution rather than being open questions.

- **Layout mechanism**: the application shell becomes exactly window height with
  its own overflow suppressed, the content column becomes its own scroll
  container, and the chat column is given a bounded height to divide. The chat
  panel's internal structure already assumes a bounded height and needs no
  change — it simply never received one.
- **Scroll-behaviour relocation**: the smooth-scrolling preference currently
  applies to the document element, which stops scrolling under this change and
  would silently take the preference out of effect. It moves to the content
  column, together with an offset so an anchored heading is not flush against the
  top.
- **Fragment handling on first load**: browsers are reliable about fragment
  navigation *within* a loaded page but historically unreliable about the initial
  page load when the scroll container is not the document, so the feature
  resolves the fragment explicitly on load and on subsequent fragment changes.
- **The section-tracking rail needs no change**: it observes intersections
  against the window, and headings still cross the window when the content column
  scrolls rather than the document.
- **Pinned-to-bottom tolerance**: roughly 40 pixels from the end counts as "at
  the newest message", so sub-pixel rounding and a partially visible last line do
  not read as "the reader scrolled away".
- **Composer height bound**: approximately five lines before internal scrolling.
- **Enter sends**: matching the dominant convention for chat composers, with
  Shift+Enter reserved for a newline.
- **This feature touches no server-side code.** It changes only the browser-side
  presentation layer, which is what makes FR-028 and SC-009 true by construction.
- **Verification cannot rely on a headless DOM alone.** The immediately preceding
  feature shipped two defects that every headless test passed over and only a
  real browser caught. Everything here that depends on real layout — that the
  composer is reachable without page scrolling, that a fragment lands on the
  right heading, that the overlay covers the content — is verified in a real
  browser as well as in unit tests.
- **Touch and small-screen gestures beyond the disclosure control are out of
  scope.** The generated wiki is a desktop reading surface; narrow-window support
  here means a usable narrow browser window, not a mobile-optimised experience.
