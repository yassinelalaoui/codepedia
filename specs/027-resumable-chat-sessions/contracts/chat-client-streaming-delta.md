# Frontend Chat Client Contract — Streaming Consumption Delta

## Purpose

`frontend/src/lib/chatApiClient.ts` is the bundled wiki UI's only caller of
the chat API. This document defines the delta to its exported functions and
to `frontend/src/components/ChatPanel.tsx`'s use of them, needed to
actually consume the SSE stream `POST /sessions/{sessionId}/messages` has
returned since spec 026, and to consume the new `GET /sessions` (this
feature's `contracts/chat-api-session-listing-delta.md`). See
`research.md` Decision 4 for why this is in scope.

## `askQuestion()` — changed

**Before**: `askQuestion(sessionId, question): Promise<AskQuestionResponse>`
— sent the request, then called `response.json()` on the result. This
never matched the server's actual response shape once 026 shipped
(`text/event-stream`), so this call would throw in a real browser.

**After**: `askQuestion(sessionId, question, onFragment): Promise<AskQuestionResponse>`

- Adds one parameter: `onFragment: (fragment: string) => void`, invoked
  once per `fragment` SSE event, in arrival order, with that event's text
  — this is what lets `ChatPanel.tsx` render the answer progressively.
- Still resolves to the same `AskQuestionResponse` shape
  (`{ answer, citedSymbolIds, citedFilePaths }`) as before, taken from the
  stream's terminal `done` event — so `answer` continues to equal the
  concatenation of every fragment passed to `onFragment`, in order
  (contract already guaranteed server-side by 026's
  `chat-streaming-api-delta.md`).
- On a terminal `error` SSE event, rejects with the same `ChatApiError`
  shape existing callers already handle (`{ code, message }`), unchanged
  from before this feature.
- On an HTTP-level failure *before* any streaming begins (unknown session,
  empty question, engine unavailable), behaves exactly as before — the
  existing non-streaming error handling in `request()` already covers this
  case, since the server only starts streaming after those checks pass
  (per 026).

## `listSessions()` — new

`listSessions(): Promise<SessionListResponse>` — a plain JSON `GET
/sessions` call using the existing `request()` helper (no streaming
involved), returning `{ sessions: SessionSummary[] }` ordered
most-recently-active first, exactly as the backend returns it.

## `ChatPanel.tsx` — changed

- On receiving a fragment via `onFragment`, appends it to the in-progress
  assistant message already being displayed (creating that in-progress
  message on the first fragment of a given answer), instead of only
  displaying the full answer once the request's promise resolves.
- Once the request resolves (the `done` event), the in-progress message's
  citations (`citedSymbolIds`/`citedFilePaths`) are attached — unchanged
  from today's already-correct citation-rendering logic, just applied to
  the now-progressively-built message instead of a freshly-created one.
- Session resumption (`GET /sessions/{id}/messages` via `getHistory`,
  gated on a `localStorage`-remembered session id) is unchanged by this
  feature — `listSessions()` is additive, not a replacement for the
  existing single-browser resume path. Wiring a session-switcher UI onto
  `listSessions()` is out of scope for this feature (spec.md's User
  Story 1 requires the *capability* to exist and be usable by *a client*;
  it does not require the bundled UI to expose a session picker).
