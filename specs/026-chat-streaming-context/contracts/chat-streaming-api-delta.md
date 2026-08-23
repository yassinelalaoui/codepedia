# Chat API Contract — Streaming Delta

## Purpose

This feature changes the response shape of one existing endpoint from
`specs/014-local-chat-api/contracts/chat-api.md` (already extended by
025's `chat-api-persistence-delta.md`). It adds no new endpoint. This
document records the delta rather than restating the unchanged parts of
the 014 contract (network binding, `POST /sessions`, `GET .../messages`
— all unaffected).

## `POST /sessions/{sessionId}/messages` — changed

Request body: **unchanged** — `{"question": "..."}`.

Response: **changed** from a single JSON body to a Server-Sent-Events
stream, `Content-Type: text/event-stream`.

Success path — a sequence of events, each `data: <json>\n\n`:

```text
data: {"fragment": "Authentication"}

data: {"fragment": " is handled by"}

data: {"fragment": " authenticate_user."}

event: done
data: {"answer": "Authentication is handled by authenticate_user.", "citedSymbolIds": ["auth.authenticate_user"], "citedFilePaths": ["src/auth/login.py"]}

```

Behavior:
- Every fragment event is sent as soon as `ChatSession.askStream()` yields
  it — no buffering of the full answer server-side before the first event.
- The `done` event's payload has exactly the same fields
  `AskQuestionResponse` (014) already had — a caller that ignores every
  `fragment` event and reads only `done` gets the same information today's
  single-block response gave it.
- Concatenating every `fragment` event's text, in order, equals `done`'s
  `answer` field exactly (FR-003/SC-003).

Failure paths — unchanged status-code semantics, now delivered as a
terminal SSE event instead of an HTTP error response, since the response
has already started streaming by the time most failures are knowable:

- Unknown `sessionId`: the connection fails **before** any `data:` event is
  sent, with the same `404` / `session_not_found` response 014 already
  defined — this check happens before generation starts, so it doesn't need
  the streaming path.
- Empty/whitespace-only `question`: same `422` / `empty_question`, before
  streaming starts — unchanged, request validation happens before the
  stream opens.
- Configured engine unavailable: same `503` / `local_dependency_unavailable`,
  before streaming starts (this is `askStream`'s pre-flight check, per
  contracts/chat-retrieval-and-session-interface.md) — no partial stream is
  ever opened for this case.
- **New**: a failure *partway through* an already-open stream (the
  configured engine errors out mid-generation) ends the stream with a
  terminal SSE event instead of an HTTP status code, since the response
  headers were already sent:

  ```text
  data: {"fragment": "Authentication is han"}

  event: error
  data: {"code": "generation_failed", "message": "..."}

  ```

  Nothing is appended to the session's history for this attempt (FR-011) —
  the `event: error` payload uses the same `{code, message}` shape
  `ApiErrorResponse` already defines.

## `GET /sessions/{sessionId}/messages` — unchanged

Still returns a single, complete JSON body (`SessionHistoryResponse`) —
history is always fully persisted/complete by the time it's stored (per
FR-011, a failed stream never reaches history), so there is nothing to
stream here.

## `POST /sessions` — unchanged

## Compatibility note

This is a breaking change to `POST /sessions/{sessionId}/messages`'s
response shape (single JSON → SSE stream). Per the request's own framing
("ne doit plus être bloquante de bout en bout"), this replaces today's
behavior rather than adding a parallel streaming-only endpoint — see
research.md Decision 6 for the alternatives considered and rejected.
