# Phase 0 Research: Chat Interface Polish

**Input**: [spec.md](./spec.md) · Frontend plan input (user-supplied technical
direction): fetch-based stream consumption, `react-markdown`-style client
rendering with a custom renderer for `file :: Symbol` references, URL query
parameter for session id read at `ChatPanel` mount.

All four points below resolve every open question from the Technical Context;
no `NEEDS CLARIFICATION` markers remain.

## 1. Stream consumption mechanism

**Decision**: Keep consuming `POST /sessions/{id}/messages` via `fetch` +
`ReadableStream` (already implemented in `frontend/src/lib/chatApiClient.ts`
`askQuestion()`, delivered by spec 027) rather than switching to
`EventSource`. This feature's frontend work is the activity indicator shown
*before* the first fragment arrives, not the fragment transport itself.

**Rationale**: `EventSource` only issues `GET` requests with no request body
and no custom headers, but asking a question is a `POST` carrying a JSON
`{ question }` body against a per-session URL. The existing `fetch`-based
reader already parses the same `text/event-stream` framing (`event:`/`data:`
lines, blank-line-delimited) by hand and is exercised by
`frontend/tests/chatApiClient.test.ts` and `ChatPanel.test.tsx`. There is
nothing left to change in the transport; the gap this feature closes is
purely presentational — `ChatPanel` renders the pending assistant message as
an empty `<p>` between submit and the first `onFragment` call, which reads as
a dead input rather than an active one.

**Alternatives considered**:
- *Switch the ask route to `GET` so `EventSource` can be used* — rejected;
  it would require re-encoding the question and conversation-relevant state
  into a query string, change an existing, already-shipped, already-tested
  HTTP contract (spec 014/026) for every other consumer, and buys no
  capability `fetch` streaming doesn't already provide locally.
- *WebSocket* — rejected; one-shot request/response-shaped streaming (ask a
  question, receive fragments, receive one terminal event) doesn't need a
  bidirectional, persistent connection, and would be a strictly larger
  change to `chat_api/app.py` for no behavioral gain.

## 2. Structured answer rendering (Markdown, code, inline symbol references)

**Decision**: Render assistant message content through `react-markdown` with
`remark-gfm` (fenced code blocks, inline code — the two constructs real
answers actually produce, per spec.md Assumptions) and `rehype-highlight`
for syntax-colored code blocks, using a small curated `highlight.js`
language subset (the languages this project's own parser supports:
Python, JavaScript/TypeScript, plus a generic fallback) registered via
`lowlight` to keep the bundle lean for a locally-served static site. A
custom `code` component override intercepts *inline* code spans (no
`language-*` className, i.e. not inside a fenced block) whose text matches
the existing citation format produced by `chat/prompting.py`'s system
prompt: `<filePath> :: <symbolId>` (e.g. `` `src/module.py :: ClassName.method` ``).
Matched spans resolve through the exact same `findByCitation` helper
(`frontend/src/lib/searchIndex.ts`) already used for the separate citation
list — no second resolution path, no duplicated symbol-id source of truth.
An unresolvable match renders as plain inline code text (matching the
existing citation-list fallback in `ChatPanel.tsx` `resolveCitations`);
anything that doesn't match the pattern renders as ordinary inline code.

**Rationale**: `react-markdown` never uses `dangerouslySetInnerHTML` unless a
raw-HTML plugin is explicitly added (none is here), so it introduces no new
XSS surface over what a plain-text `<p>` already had. Its component-override
API (`components={{ code: ... }}`) is the natural extension point for
turning one specific inline-code shape into a citation-resolving `<a>`
without hand-rolling Markdown parsing/escaping. Reusing `findByCitation`
keeps "what counts as a resolvable reference" defined in exactly one place,
consistent with FR-006's requirement that in-text resolution use "the same
resolution already used for the existing citation list."

**Alternatives considered**:
- *Hand-rolled regex formatter over the raw string* (fence detection,
  manual escaping, manual link substitution) — rejected; correctly handling
  nested/partial/malformed Markdown this way reinvents a parser and is
  measurably more bug-prone than delegating to one, especially under
  streaming (Edge Case: a code block that hasn't finished arriving yet must
  still degrade gracefully, which is exactly the "unterminated fence renders
  as plain text until closed" behavior a real Markdown parser gives for
  free).
- *`marked` + `DOMPurify`* — rejected; requires `dangerouslySetInnerHTML`
  plus a sanitizer dependency, and injecting the custom symbol-reference
  link behavior mid-render is far more awkward via a post-hoc HTML string
  transform than via `react-markdown`'s component override.
- *Full `highlight.js` (all languages) or a CDN-hosted highlighter* —
  rejected; the tool ships a fully local, offline static site (constitution
  2.2/2.6 posture extends in spirit to the bundled client, even though those
  principles target server network exposure) — a curated local language
  subset via `lowlight` avoids both a runtime network dependency and
  unnecessary bundle bloat for languages this project doesn't even parse.

## 3. Session id persistence via URL

**Decision**: Carry the session id as a URL query-string parameter (e.g.
`?chatSession=<id>`) on whatever wiki page hosts the chat panel, read once
via `URLSearchParams(window.location.search)` in a `ChatPanel` mount effect,
and written back with `history.replaceState` (no navigation, no reload)
whenever a session is created or confirmed resumable. The existing
`localStorage`-based persistence (`repo-scanner:chat-session-id`, spec 025)
is removed and fully replaced by the URL parameter.

**Rationale**: FR-009 requires that a conversation's page address restore
that conversation "including from a different browser or device than the
one that started it." `localStorage` is scoped to one browser profile on
one device and structurally cannot satisfy that; a URL query parameter is
copyable, bookmarkable, and shareable by construction, and needs no backend
change — `GET /sessions/{id}/messages` (spec 025/027) already accepts any
id and already returns `session_not_found` for one that doesn't resolve,
which is exactly the signal FR-011's "start a new, empty conversation"
fallback needs.

**Alternatives considered**:
- *URL path segment* (e.g. a session-specific page path) — rejected; wiki
  pages are pre-generated static files at fixed, content-derived paths
  (`modules/*.html`, etc.) computed by `doc_generator`; making the session
  id part of the path would require the static site generator itself to
  know about live chat sessions at build time, which it structurally
  cannot (sessions are created at runtime, long after generation).
  A query parameter layers on top of any already-generated page untouched.
- *`sessionStorage`* — rejected; same single-browser-profile limitation as
  `localStorage`, plus it doesn't even survive closing and reopening the
  tab, which is a strictly worse fit than what 025 already shipped.
- *Keep `localStorage` as a fallback alongside the URL parameter* —
  rejected as an added-complexity two-sources-of-truth design (which one
  wins on conflict?) that spec.md's Assumptions don't ask for; the URL
  parameter alone satisfies every acceptance scenario in User Story 3.

## 4. Blocking new questions until history hydration completes

**Decision**: Extend the existing mount-time history-fetch effect (today
keyed off `localStorage`, now keyed off the URL parameter) so the question
input stays disabled — via the same `pending`-style boolean already gating
the form in `ChatPanel.tsx` — until that fetch settles one way or another
(history restored, or the id doesn't resolve and a fresh conversation
starts).

**Rationale**: Directly satisfies FR-010 ("retrieve and display that
conversation's complete history before the user is able to submit a new
question"). No new mechanism is needed: the component already disables the
form via a boolean while an async operation is outstanding (`pending` for
ask-in-flight); the same pattern extends naturally to gate on the initial
history load as well as an in-flight ask.

**Alternatives considered**:
- *Let the user type/submit immediately and reconcile history once it
  arrives* — rejected; directly contradicts FR-010's explicit ordering
  requirement and risks a new question being interleaved with, or answered
  ahead of, history the user hasn't seen yet.
