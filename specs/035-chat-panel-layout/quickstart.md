# Quickstart: Validating the Chat Panel Layout

**Feature**: 035-chat-panel-layout | **Date**: 2026-09-02

Three levels, in increasing order of what they can actually prove. Level 2 is not
optional: **jsdom reports all-zero element geometry**, so a headless assertion
that "the composer is visible without scrolling" is vacuous, and this feature is
almost entirely about geometry.

## Prerequisites

- Node 25 / npm 11.
- Python venv only for regenerating a wiki to test against (**3.11-3.13**; 3.14
  hangs in Pydantic schema generation).
- A generated wiki. The 034 scratchpad harness produced one from the
  alpha/beta/gamma fixture; any wiki with a long page works.

---

## 1. Unit tests — `cd frontend && npm test`

What these can prove, given `scrollHeight`/`clientHeight` are defined per test:

| Case | Asserts |
| --- | --- |
| pinned + message arrives | `scrollTop` was driven to `scrollHeight` (FR-011) |
| scrolled up + answer streams | `scrollTop` unchanged (FR-012) |
| scrolled up | jump affordance is present (FR-013) |
| jump activated | scrolls to bottom, re-pins (FR-014) |
| submit while scrolled up | returns to bottom (FR-015) |
| `Enter` | sends, and `preventDefault` was called (FR-017) |
| `Shift+Enter` | value gains a newline, nothing sent (FR-017) |
| send button | sends (FR-018) |
| whitespace-only, all three routes | nothing sent (FR-022) |
| after send | value empty, height reset (FR-021) |
| typing many lines | height grows then caps (FR-016) |
| fragment on load | `scrollIntoView` called on the right element (FR-006) |

Environment constraints, from research Decision 3 — measured, not assumed:

- `scrollIntoView` and `Element.scrollTo` are **undefined** in jsdom 25. The
  implementation must use `scrollTop`; `setup.ts` stubs `scrollIntoView` so the
  fragment path is exercised rather than skipped.
- `scrollHeight` / `clientHeight` are always `0` — define them per test with
  `Object.defineProperty`.
- `matchMedia`, `ResizeObserver`, `IntersectionObserver` are all undefined.

**Watch for the false pass**: a test asserting the jump button appears proves the
render, never that the reader was actually left in place. Pair every
"affordance appears" assertion with a `scrollTop` assertion.

---

## 2. Real browser — the level that matters

Reuse the 034 CDP harness: headless Chrome, page loaded from `file://`.

```bash
cd frontend && npm run build && cd ..
# regenerate a wiki, then:
chrome --headless=new --disable-gpu --remote-debugging-port=9333 \
       --user-data-dir=<tmp> about:blank &
node <harness>.mjs "file:///<abs>/demo-wiki/modules/<a-long-module>.html"
```

Checks that only a real browser can settle:

1. **Composer reachable** (FR-001, FR-005, SC-001, SC-002). On the longest page:
   `document.scrollingElement.scrollHeight <= innerHeight + 1` — the document
   does not scroll at all. Then confirm the composer's rect is inside the
   viewport, and *stays* there after scrolling `.main` to its end.
2. **Three independent scrolls** (FR-003, FR-004). Scroll `.main`; assert the
   sidebar's and the chat container's `scrollTop` are unchanged. Repeat for each.
3. **Long conversation cannot push the composer off** (FR-005). Inject 100
   messages, then re-check the composer's rect.
4. **Fragment lands correctly** (FR-006-FR-009, SC-003). Load a page with a
   `#fragment` naming a heading well down the page; assert the heading's
   `getBoundingClientRect().top` is within a small band of `scroll-padding-top` —
   not zero, and not off screen. Then click a rail entry and assert the same.
5. **Drawer overlays** (FR-023-FR-026). Set the window to 1000px wide, assert the
   toggle is visible, open it, assert the panel covers the content, press Escape,
   assert focus is back on the toggle.

Lessons carried from 034's harness, each of which produced a *false* result there
before being fixed — they apply verbatim here:

- Do not append a cache-busting query to a `file://` URL.
- Scroll the target into view before dispatching synthetic mouse events; CDP
  dispatches at window coordinates.
- Restart Chrome between runs rather than reusing a session across many
  navigations.
- `python -m http.server` truncates large files on Windows — use `file://`.

---

### Result, 2026-09-02

**11/11 in headless Chrome over `file://`**, on the longest generated module page:

| Check | Measured |
| --- | --- |
| Document does not scroll | `scrollHeight` 800 = `innerHeight` 800 |
| Content column does scroll | 1058 content in 800 visible |
| Composer inside the viewport | bottom 753 of 800 |
| Composer does not move when content scrolls | top 717 -> 717 |
| Three independent scroll regions | main 258, sidebar 0, chat 0 |
| 100 injected messages | composer bottom still 753 |
| Fragment on load | `.main` scrolled 187, heading 24px from the top |
| `scroll-padding-top` honoured | heading offset 24px, matching the declared value |
| Drawer at 1000px wide | toggle visible, panel covers 616-1000, `aria-expanded="true"` |

The drawer-toggle check **failed on the first run** and caught a real defect: the
base `.wiki-chat-drawer-toggle { display: none }` rule sat *after* the media
query, and with equal specificity the later rule won, so the toggle was invisible
at every width. No jsdom test could have seen it — jsdom applies no stylesheet.

---

## 3. Manual — what still needs human eyes

1. Open a long module page. Scroll the content to the middle. The question box
   has not moved. Type without touching the scroll wheel.
2. Ask something. Watch the answer arrive and stay in view.
3. Ask again, and scroll up mid-answer. The view holds; the jump affordance
   appears; activating it returns you to the newest message.
4. Type a five-line question. The box grows, then scrolls internally, and the
   message list is still visible.
5. `Enter` sends. `Shift+Enter` gives a newline.
6. Narrow the window past 1180px. The chat is still reachable. Escape closes it.
7. Enable reduced motion in the OS. Anchor jumps are instant.
8. Dark mode: the panel, jump affordance and drawer follow the existing palette.

---

## 4. Regression checks

```bash
cd frontend && npm test          # ChatPanel's existing suite, unweakened
cd .. && pytest --basetemp=<scratch> -p no:cacheprovider
```

Expected: 667 green plus one known flake —
`test_config_before_any_provider_reachable_still_reports_without_failing` makes a
live Groq availability call and passes or fails on whether Groq answers. Identify
it by failure text naming `groq:...: available`; any other failure is real.

**No Python file changes in this feature**, so the entire Python suite is a pure
regression check. If anything there moves, something has gone wrong.

Confirm the generated output is untouched (SC-009):

```bash
diff -r docs-before/ docs-after/ --exclude=assets
```

Both builds must index the same repository at the same absolute path — generated
pages embed absolute source paths, so indexing two copies makes files differ for
that reason alone. (This exact mistake produced a false failure during 034.)

---

## 5. Shipping

`src/doc_generator/assets/wiki-ui.{js,css}` are committed build artifacts and are
what the Python tests serve, so `npm run build` runs before the commit and the
regenerated files are staged with the source that produced them.

```bash
git status --short src/doc_generator/assets/
# expect: M wiki-ui.js, M wiki-ui.css
```
