# Phase 1 Data Model: Chat Panel Layout

**Feature**: 035-chat-panel-layout | **Date**: 2026-09-02

Nothing is persisted. No manifest table, no generated file, no browser storage —
FR-028 and SC-009 say the generated output is unchanged, and this feature is
entirely browser-side presentation state. Everything below lives in React state
or in the DOM for the lifetime of a page view.

---

## Entity: `PinnedState`

Whether the message list is currently showing its newest message. Decides
whether arriving content scrolls into view or is announced by the jump
affordance instead.

| Field | Type | Initial | Notes |
| --- | --- | --- | --- |
| `isPinned` | boolean | `true` | A fresh conversation starts at the bottom, which is also the top. |

**Derivation** — recomputed on every scroll of the container:

```text
distanceFromBottom = scrollHeight - scrollTop - clientHeight
isPinned = distanceFromBottom <= PIN_TOLERANCE_PX
```

**Invariants**

- `PIN_TOLERANCE_PX = 40`. Sub-pixel rounding, a partially visible last line, and
  a fractional device pixel ratio all leave `distanceFromBottom` slightly above
  zero when the reader is, to their own eyes, at the bottom. A strict `=== 0`
  test would report "scrolled away" for a reader who has not scrolled at all.
- When the container does not overflow (`scrollHeight <= clientHeight`),
  `distanceFromBottom` is `<= 0`, so `isPinned` is `true`. A short conversation is
  always pinned, which is the correct answer.
- `isPinned` is derived, never set directly, with two deliberate exceptions
  below.

**State transitions**

```text
pinned --reader scrolls up past the tolerance--> unpinned
unpinned --reader scrolls back within tolerance--> pinned
unpinned --activates the jump affordance--> pinned   (and scrolls to bottom)
unpinned --submits a question--> pinned              (FR-015)
```

The last two are the exceptions: both are deliberate reader actions whose whole
point is to see the newest message, so they re-pin rather than waiting for a
scroll event to derive it.

---

## Entity: `ComposerState`

The pending question and the composer's presentation. Partly present today; this
feature adds only height and multi-line handling.

| Field | Type | Initial | Notes |
| --- | --- | --- | --- |
| `question` | string | `""` | Already exists in `ChatPanel`. |
| `isDisabled` | derived | `false` | `pending \|\| historyLoadState === "loading"` — unchanged from today. |
| `rows` | derived | 1 | Grown to fit content, capped at `MAX_COMPOSER_ROWS`. |

**Invariants**

- Height is recomputed from content on every change: reset to `auto`, then set
  from `scrollHeight`, capped at `MAX_COMPOSER_ROWS`. Resetting first is
  required — without it the box can only ever grow, never shrink when text is
  deleted.
- Beyond the cap the box scrolls internally and MUST NOT push the message list
  out of view (FR-016, SC-006).
- After a successful send, `question` is `""` and the height is back to its
  initial value (FR-021). The height does not reset itself when the value
  changes; it is recomputed, so this is a consequence of the recompute, not a
  separate action.
- A whitespace-only question is never sent, by any of the three routes — Enter,
  the button, or form submit (FR-022). One guard, checked in one place.

**Keyboard contract**

| Key | Behaviour |
| --- | --- |
| `Enter` (no modifier) | Send; suppress the newline the textarea would otherwise insert |
| `Shift+Enter` | Insert a newline; do not send |
| Any other key | Default textarea behaviour |

`Enter` must call `preventDefault()`. Without it the question is sent *and* a
newline lands in the freshly cleared box.

---

## Entity: `DrawerState`

Only meaningful below the narrow-window breakpoint. Above it the chat is docked
and this state is inert.

| Field | Type | Initial | Notes |
| --- | --- | --- | --- |
| `isOpen` | boolean | `false` | Drives the overlay class and `aria-expanded`. |
| `returnFocusTo` | element ref | the toggle | Focused when the drawer closes (FR-025). |

**State transitions**

```text
closed --toggle activated--> open   (aria-expanded="true")
open --toggle activated--> closed   (focus returns to the toggle)
open --Escape--> closed             (focus returns to the toggle)
```

**Invariants**

- `aria-expanded` on the toggle always matches `isOpen` (FR-026).
- Closing always returns focus to the toggle; a keyboard reader must never be
  dropped at the top of the document.
- Opening and closing MUST NOT alter `PinnedState` or `ComposerState` — the same
  panel is being revealed, not rebuilt.

---

## DOM structure

The one structural change to `ChatPanel`'s markup. A stable scroll container now
always exists (research Decision 7); today the list is rendered only when there
are messages, so there is nothing to hold a ref to on first render.

```text
div.wiki-chat-panel
├── div.wiki-chat-panel-head          flex: none   (unchanged)
├── div.wiki-chat-scroll              flex: 1; overflow-y: auto   <- NEW, stable ref
│   └── p.wiki-chat-empty  OR  ul.wiki-chat-messages
├── button.wiki-chat-jump-latest      shown only when not pinned
└── form                              flex: none   (unchanged)
    ├── textarea[aria-label="Ask a question about this repository"]
    ├── button[type=submit]           the visible send control
    └── p.wiki-chat-foot-note         (unchanged)
```

**Invariants**

- `div.wiki-chat-scroll` is rendered unconditionally, so its ref is stable for
  the component's lifetime and the scroll listener attaches exactly once.
- `overflow-y: auto` moves from `.wiki-chat-messages` to `.wiki-chat-scroll`; the
  list keeps its own spacing and layout rules.
- The textarea's `aria-label` is the existing string, byte-for-byte:
  `ChatPanel.test.tsx` queries by it in four places, and FR-020 requires it.
- `.wiki-chat-foot-note` stays inside the form and unchanged (FR-020).

---

## Shell layout

Not an entity, but the contract the CSS has to satisfy — stated here because
three separate rules have to agree.

| Element | Required | Why |
| --- | --- | --- |
| `.shell` | `height: 100vh; overflow: hidden` | Was `min-height: 100vh`, which let the document scroll |
| `.sidebar` | `overflow-y: auto` | Already present; unchanged |
| `.main` | `overflow-y: auto`, `scroll-padding-top`, `scroll-behavior` | Becomes the content scroll container; inherits the smooth-scroll preference from `html` |
| `#wiki-chat-root` | `height: 100%; min-height: 0` | `min-height: 0` is what actually permits the inner flex child to scroll |

---

## Constants

| Name | Value | Source |
| --- | --- | --- |
| `PIN_TOLERANCE_PX` | `40` | spec Assumptions; FR-011, FR-012 |
| `MAX_COMPOSER_ROWS` | `5` | spec Assumptions; FR-016 |
| `SCROLL_PADDING_TOP` | `24px` | FR-008 — a heading must not sit flush against the top |
| narrow breakpoint | `1180px` | existing value, styles.css:769 |

---

## What this feature does *not* touch

- Any Python file. No generator, no template, no manifest — which is what makes
  FR-028 and SC-009 true by construction rather than by test.
- The chat API client, session handling, streaming, or citation rendering
  (FR-029). `handleSubmit`'s body is unchanged; only how it is *invoked* gains a
  second route.
- `TocHighlighter`, which observes the window rather than a scroll container
  (research Decision 8).
- `SearchWidget`.
