# Phase 0 Research: Chat Panel Layout

**Feature**: 035-chat-panel-layout | **Date**: 2026-09-02

Every finding below was probed against this repository's actual environment, not
recalled. Feature 034 shipped two defects that came from inferring behaviour
instead of measuring it, so each decision names the probe that produced it.

---

## Decision 1: Three scroll containers, replacing one document scroll

**Decision**: `.shell` becomes `height: 100vh; overflow: hidden`; `.main` gains
`overflow-y: auto`; `#wiki-chat-root` gains `height: 100%; min-height: 0`. The
sidebar keeps the `overflow-y: auto` it already has.

**Rationale**: The panel's internals are already correct —
`.wiki-chat-messages` is `flex: 1; overflow-y: auto` (styles.css:658) and the
form is `flex: none` (styles.css:753). They have never been wrong; they simply
divide a height that is currently the whole document's. Giving the column a
bounded height is the entire fix, and it is why this feature touches no
component logic for User Story 1.

**`min-height: 0` is load-bearing, not decoration.** A flex or grid item's
default `min-height: auto` refuses to shrink below its content, so a long
conversation would push the column taller than the window and re-create the
original bug in a subtler form. This is the single most common way a "flex child
with overflow" layout silently fails.

**Alternatives considered**:

- `position: sticky` on the composer alone: leaves the column document-height, so
  the message list still never bounds and the header still scrolls away.
- `position: fixed` on the whole chat column: takes it out of flow, so the grid
  no longer reserves its 384px and the content column runs underneath it.

---

## Decision 2: `100vh` accepted; `100dvh` rejected for this surface

**Decision**: `height: 100vh`.

**Rationale**: `dvh` exists for mobile browsers whose toolbars collapse on
scroll. This wiki is a desktop reading surface served at `127.0.0.1` and opened
over `file://`; the spec puts mobile explicitly out of scope. `100vh` is
understood by every browser that can run the existing bundle, whereas `dvh`
would add a fallback path for a case this feature does not serve.

Revisit only if the wiki gains a genuine mobile target.

---

## Decision 3: Auto-scroll writes `scrollTop`; it must not call `scrollIntoView` or `Element.scrollTo`

**Probed** under this project's exact vitest + jsdom 25 setup:

| API | Available | Consequence |
| --- | --- | --- |
| `element.scrollTop` (read + write) | **yes**, persists as set | Usable directly in tests |
| `element.scrollHeight` / `clientHeight` | present but always `0` | Overridable via `Object.defineProperty` |
| `Element.prototype.scrollIntoView` | **undefined** | Calling it *throws* |
| `Element.prototype.scrollTo` | **undefined** | Calling it *throws* |
| `window.scrollTo` | function | Not needed here |
| `requestAnimationFrame` | **function** | Usable |
| `IntersectionObserver` | undefined | `TocHighlighter` already returns early under test |
| `matchMedia`, `ResizeObserver` | undefined | Must not be called |

**Decision**: auto-scroll is `container.scrollTop = container.scrollHeight`.

**Rationale**: It is the only one of the three that exists in the test
environment, and it is also the simplest and most widely supported in real
browsers. Choosing it costs nothing and makes the behaviour directly assertable
rather than merely mocked.

---

## Decision 4: Stub `scrollIntoView` in the test setup rather than let a guard hide it

**The problem, stated precisely.** The fragment handler (Decision 5) genuinely
wants `scrollIntoView()` — it is the only API that honours `scroll-padding-top`
and `scroll-behavior` and correctly resolves a nested scroll container. But
jsdom does not define it, so the natural implementation is:

```js
if (typeof target.scrollIntoView === "function") target.scrollIntoView();
```

**That is the exact shape of the bug feature 034 shipped.** There, a `typeof`
guard around `setPointerCapture` meant jsdom skipped the whole code path in every
test, and the defect — capture retargeting the click so Mermaid's node links
stopped navigating — was invisible until a real browser ran it.

**Decision**: add a `scrollIntoView` stub to `frontend/tests/setup.ts`
(`Element.prototype.scrollIntoView = function () {}` when absent), so the guard
is *true* under test and the call path executes. Tests then assert the call
happened on the right element via `vi.spyOn`.

**Rationale**: this converts an untestable branch into a testable one. The guard
stays in the production code — an old browser without the API must not throw —
but it no longer functions as a blindfold. The stub belongs in `setup.ts`, beside
the existing `localStorage` polyfill, which is there for the same class of
reason.

**Still not sufficient on its own**: a stub proves the call was *made*, never
that the browser *scrolled to the right place*. FR-006 through FR-009 remain on
the real-browser list (Decision 8).

**Alternative considered**: compute `container.scrollTop = target.offsetTop - padding`
manually. Fully testable, but reimplements what the browser already does,
silently ignores `scroll-padding-top` and `scroll-behavior`, and breaks the
moment a heading sits inside another positioned ancestor. Rejected: hand-rolling
scroll geometry to satisfy a test harness is the tail wagging the dog.

---

## Decision 5: Resolve the fragment explicitly on load and on `hashchange`

**Decision**: a small handler in the wiki-ui bundle reads `location.hash`,
resolves the element, and calls `scrollIntoView()`.

**Rationale**: Browsers reliably handle a same-page fragment click even when the
scroll container is not the document. The *initial page load* case is the
unreliable one — and it is the case that matters most here, because a search
result linking `modules/foo.html#bar` is a fresh page load, and the sidebar's
"On this page" rail exists on every page in the wiki.

The handler runs on `DOMContentLoaded` (or immediately if the document is already
parsed, since the bundle is loaded at the end of `<body>`) and on `hashchange`.

**Interaction with `scroll-padding-top`**: setting it on `.main` means
`scrollIntoView()` leaves the requested offset above the heading automatically,
so the handler does no arithmetic of its own.

---

## Decision 6: `scroll-behavior` moves from `html` to `.main`

**Finding**: `styles.css:233` currently carries
`html { scroll-behavior: smooth; }` inside a `prefers-reduced-motion: no-preference`
guard.

**Decision**: move it to `.main`.

**Rationale**: once `html` no longer scrolls, a `scroll-behavior` on it applies
to nothing — the preference would be silently lost rather than loudly broken,
which is the harder kind of regression to notice. The existing reduced-motion
guard moves with it unchanged, which is what keeps FR-027 true.

---

## Decision 7: A stable scroll container, always rendered

**Finding**: `ChatPanel.tsx:189-193` renders the message list *conditionally* —
`<p class="wiki-chat-empty">` when there are no messages, `<ul class="wiki-chat-messages">`
otherwise. Both are `flex: 1` children (styles.css:638, :658).

**Consequence**: there is no single element that is always the scroll container,
so a ref to "the message list" is `null` on first render, and the pinned-to-bottom
listener would have to be attached and torn down as the conversation appears.

**Decision**: introduce one always-rendered scroll container that holds either
the empty state or the list. The ref is then stable for the component's lifetime,
the scroll listener attaches once, and `isPinnedToBottom` has somewhere to live
from the first render.

**Rationale**: the alternative — attaching the ref to whichever element happens
to exist — makes every subsequent behaviour conditional on a state that changes
underneath it. This is a small structural change that removes a whole class of
ordering bug.

---

## Decision 8: What must be verified in a real browser

Feature 034 established the CDP harness (headless Chrome over the DevTools
Protocol, page loaded from `file://`). It is reused here, and it is not optional:
**jsdom reports all-zero element geometry**, so a headless assertion that "the
composer is visible without scrolling" is vacuous.

Must be checked in a real browser:

| Requirement | Why jsdom cannot answer it |
| --- | --- |
| FR-001, FR-005, SC-001, SC-002 | Requires real layout — all rects are zero under jsdom |
| FR-003, FR-004 | Requires three genuinely independent scroll containers |
| FR-006-FR-009, SC-003 | A stub proves the call, never the resulting scroll position |
| FR-024, drawer overlay | Requires real stacking and viewport size |
| FR-027 | `matchMedia` is undefined; the media query is CSS-only |

Checkable in jsdom (with `scrollHeight`/`clientHeight` defined per test):
pinned-vs-unpinned auto-scroll (FR-011, FR-012), the jump affordance appearing
and acting (FR-013, FR-014), send-returns-to-bottom (FR-015), and every composer
behaviour (FR-016-FR-022).

---

## Decision 9: Narrow-window drawer, and what "narrow" means

**Decision**: keep the existing `1180px` breakpoint. Below it, the chat column
leaves the grid and becomes an overlay opened by a fixed toggle.

**Rationale**: the breakpoint is already in the stylesheet (:769) and already
matches the width at which a 264 + 384px pair of side columns stops leaving a
readable content column. Changing it would be an unrelated judgement.

**Decision**: the disclosure is CSS-driven state plus a small amount of
component state for focus return and `aria-expanded` — the same shape as the
diagram viewport's expand control in 034, and for the same reason: the Fullscreen
API and native `<dialog>` both bring behaviour (backdrop, focus trapping,
`file://` inconsistencies) that this surface does not want.

**Focus return is explicit**: the control that opened the drawer receives focus
when it closes (FR-025). Without that, a keyboard reader who closes the drawer
lands at the top of the document.

---

## Resolved unknowns

No `NEEDS CLARIFICATION` markers remain.

| Question | Answer | Probe |
| --- | --- | --- |
| Does jsdom support `scrollIntoView`? | No — undefined, throws | `vitest` env probe |
| Does jsdom support `Element.scrollTo`? | No — undefined | same |
| Is `scrollTop` usable in tests? | Yes, read and write | same |
| Are `scrollHeight`/`clientHeight` usable? | Only if defined per test | same |
| Is `requestAnimationFrame` available? | Yes | same |
| Is the message list always rendered? | **No** — conditional on message count | `ChatPanel.tsx:189` |
| Where is `scroll-behavior` today? | `html`, styles.css:233 | grep |
| Does `TocHighlighter` need changing? | No — observes the window, not a container | source read |
| Current breakpoint for hiding chat? | 1180px, styles.css:769-771 | grep |
