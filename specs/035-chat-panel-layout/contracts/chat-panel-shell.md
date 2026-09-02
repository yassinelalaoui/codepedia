# Chat Panel & Shell Contract

## Purpose

Define the three interfaces this feature changes, all of them browser-side: the
shell's scroll layout, the `ChatPanel` component's behaviour, and the fragment
handler in the bundle's entry point.

There is no Python in this feature. That is itself a contract — see
"Unchanged surfaces".

---

## 1. Shell layout (`frontend/src/styles.css`)

The page stops scrolling as one document and becomes three independent scroll
regions.

| Selector | Change | Requirement |
| --- | --- | --- |
| `.shell` (:104) | `min-height: 100vh` → `height: 100vh`, add `overflow: hidden` | FR-001, FR-005 |
| `.sidebar` (:112) | none — already `overflow-y: auto` | FR-004 |
| `.main` (:237) | add `overflow-y: auto`, `scroll-padding-top: 24px`, and the relocated `scroll-behavior` | FR-003, FR-008 |
| `#wiki-chat-root` (:604) | add `height: 100%`, `min-height: 0` | FR-001, FR-002 |
| `html` (:233) | remove `scroll-behavior: smooth` | FR-027 |

Expected behavior:

- **`min-height: 0` on `#wiki-chat-root` is mandatory, not stylistic.** A grid or
  flex item defaults to `min-height: auto`, which refuses to shrink below its
  content; a long conversation would then push the column past the window and
  restore the original defect in a less obvious form.
- **`scroll-behavior` MUST move, not be duplicated.** Left on `html` it applies to
  an element that no longer scrolls, so the reader's smooth-scrolling preference
  is silently lost. Its existing `prefers-reduced-motion: no-preference` guard
  moves with it unchanged (FR-027).
- `scroll-padding-top` on `.main` is what keeps an anchored heading off the top
  edge (FR-008). The fragment handler in section 3 relies on it and performs no
  offset arithmetic of its own.
- The narrow-window rule at :769-771 changes from `#wiki-chat-root { display: none }`
  to the overlay treatment in section 2.4 (FR-023).

---

## 2. `ChatPanel` (`frontend/src/components/ChatPanel.tsx`)

### 2.1 Structure

Adopt the DOM shape in `data-model.md` § DOM structure. The one structural change
is a stable, always-rendered `div.wiki-chat-scroll` holding either the empty
state or the message list.

- `overflow-y: auto` moves from `.wiki-chat-messages` to `.wiki-chat-scroll`.
- The ref MUST be attached to the always-rendered container, never to the
  conditionally-rendered list — today the list does not exist until the first
  message arrives (`ChatPanel.tsx:189`), so a ref on it is `null` exactly when
  the first auto-scroll would be needed.

### 2.2 Pinned-to-bottom and auto-scroll

| Event | Behavior | Requirement |
| --- | --- | --- |
| Container scrolls | Recompute `isPinned` from `scrollHeight - scrollTop - clientHeight <= 40` | — |
| Message added / answer grows, `isPinned` | Set `scrollTop = scrollHeight` | FR-011 |
| Message added / answer grows, not `isPinned` | Do nothing to scroll position | FR-012 |
| Not `isPinned` | Render the jump affordance | FR-013 |
| Jump affordance activated | Scroll to bottom and re-pin | FR-014 |
| Question submitted | Scroll to bottom and re-pin, whatever the previous state | FR-015 |

Expected behavior:

- **Auto-scroll MUST be `container.scrollTop = container.scrollHeight`.** Neither
  `scrollIntoView()` nor `Element.scrollTo()` exists in jsdom 25 — both are
  `undefined` and throw when called (research Decision 3). `scrollTop` is also
  the simplest correct answer in a real browser, so nothing is traded away.
- The scroll effect MUST run **after** the DOM has been updated but **before**
  the browser paints, so no intermediate position is visible.
- The auto-scroll write MUST NOT itself flip `isPinned` to a wrong value. Writing
  `scrollTop` fires a `scroll` event; the derivation in `data-model.md` re-reads
  the container and yields `isPinned = true`, which is correct — but a naive
  implementation that toggles state inside its own scroll handler can loop. Guard
  by deriving rather than toggling.

### 2.3 Composer

| Input | Behavior | Requirement |
| --- | --- | --- |
| Typing past one line | Grow to fit, capped at 5 rows, then scroll internally | FR-016 |
| `Enter` without Shift | Send; `preventDefault()` so no newline is inserted | FR-017 |
| `Shift+Enter` | Insert a newline; do not send | FR-017 |
| Send button | Send | FR-018 |
| Empty or whitespace-only, any route | Do nothing | FR-022 |
| Pending or history loading | Composer unavailable | FR-019 |
| After a send | Value empty, height back to one row | FR-021 |

Expected behavior:

- **`preventDefault()` on the `Enter` send path is mandatory.** Without it the
  question is sent *and* a newline is inserted into the box that was just
  cleared.
- **Height recompute MUST reset to `auto` before reading `scrollHeight`.**
  Otherwise the box grows and never shrinks when text is deleted.
- The `aria-label` MUST remain exactly `"Ask a question about this repository"`
  (FR-020). `ChatPanel.test.tsx` queries by it in four places, and changing it
  would break them for a reason unrelated to the feature.
- `disabled={pending || historyLoadState === "loading"}` and
  `.wiki-chat-foot-note` are preserved verbatim (FR-019, FR-020).
- The existing `handleSubmit` body is unchanged. It gains a second caller, not a
  rewrite (FR-029).

### 2.4 Narrow-window drawer

Replaces `#wiki-chat-root { display: none }`.

| Input | Behavior | Requirement |
| --- | --- | --- |
| Below the breakpoint | A visible toggle is rendered; the panel is hidden until opened | FR-023 |
| Toggle activated | Panel overlays the content at full window height | FR-024 |
| Toggle again, or `Escape` | Panel closes; focus returns to the toggle | FR-025 |
| Always | `aria-expanded` on the toggle matches the open state | FR-026 |

- Opening or closing MUST NOT reset the conversation, the pinned state, or the
  composer's contents.
- A CSS class drives the overlay, not the Fullscreen API and not `<dialog>` —
  same reasoning as 034's expand control (research Decision 9).

---

## 3. Fragment handler (`frontend/src/main.tsx` or a small lib module)

Runs once at bundle evaluation and on every `hashchange`.

Expected behavior:

- Reads `location.hash`, resolves the element by id, and calls `scrollIntoView()`
  on it.
- MUST be guarded (`typeof el.scrollIntoView === "function"`) so an environment
  without the API does not throw.
- **The guard MUST NOT become a blindfold.** `frontend/tests/setup.ts` gains a
  `scrollIntoView` stub so the guard is true under test and the path executes;
  tests assert the call landed on the right element. This is a direct response to
  feature 034, where a `typeof` guard around `setPointerCapture` hid a real defect
  from every test in the suite (research Decision 4).
- A hash naming no existing element MUST leave the page as-is (FR-010).
- MUST NOT compute its own scroll offset — `scroll-padding-top` on `.main`
  handles that (FR-008).
- MUST NOT interfere with same-page rail clicks that the browser already handles
  correctly; re-scrolling to the element the browser just scrolled to is
  idempotent and harmless.

---

## 4. Test environment (`frontend/tests/setup.ts`)

Add a `scrollIntoView` stub when the API is absent, beside the existing
`localStorage` polyfill, which exists for the same class of reason.

The module MUST NOT call, and tests MUST NOT assert on:

- `Element.scrollTo` — undefined in jsdom 25
- `window.matchMedia` — undefined; the reduced-motion rule is CSS-only
- `ResizeObserver` — undefined; composer height is recomputed on input, not
  observed

`scrollHeight` and `clientHeight` are `0` in jsdom and MUST be defined per test
via `Object.defineProperty` wherever pinned-state or composer-height behaviour is
exercised.

---

## 5. Unchanged surfaces (asserted, not assumed)

- **Every Python file.** No generator, template, manifest or test on the Python
  side changes. Generated `.md` and `.html` output is byte-identical (FR-028,
  SC-009).
- `TocHighlighter.tsx` — observes the window with `root: null`, and headings
  still cross the window when `.main` scrolls (research Decision 8).
- `SearchWidget.tsx`, `chatApiClient.ts`, `searchIndex.ts`,
  `markdownReferences.tsx` — untouched.
- `ChatPanel`'s session handling, streaming, citation resolution and error
  reporting (FR-029). The existing tests covering them must pass **unweakened**;
  only the four `findByLabelText` call sites adapt, and only because the element
  changed from `<input>` to `<textarea>`.

If a change here requires editing anything in this section, the approach has
drifted from the design and should be re-examined rather than accommodated.
