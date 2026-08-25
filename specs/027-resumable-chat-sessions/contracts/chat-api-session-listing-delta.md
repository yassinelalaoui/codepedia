# Chat API Contract — Session Listing Delta

## Purpose

This feature adds exactly one new endpoint to the chat API defined by
`specs/014-local-chat-api/contracts/chat-api.md` (already extended by
025's `chat-api-persistence-delta.md` and 026's
`chat-streaming-api-delta.md`). It changes nothing else — `POST /sessions`,
`POST /sessions/{sessionId}/messages` (already SSE, per 026), and
`GET /sessions/{sessionId}/messages` are all unaffected and unchanged.

No new endpoint is added for asking a question — `POST
/sessions/{sessionId}/messages` already streams the answer (spec 026); see
`research.md` Decision 1 for why the technical direction's
`/chat/sessions/{id}/ask/stream` path is not introduced as a second route.

## `GET /sessions` — new

Request: no body, no parameters.

Response: `200 OK`, `SessionListResponse`:

```json
{
  "sessions": [
    {
      "sessionId": "b2b9…",
      "createdAt": "2026-08-20T10:03:12.441Z",
      "lastActivityAt": "2026-08-25T09:41:07.118Z"
    },
    {
      "sessionId": "7ac1…",
      "createdAt": "2026-08-18T15:22:40.009Z",
      "lastActivityAt": "2026-08-18T15:26:51.774Z"
    }
  ]
}
```

Behavior:
- Every persisted session is included, regardless of which server process
  created it — a fresh server process with an empty in-memory cache still
  returns every session ever created (FR-002), by reading directly from the
  SQLite-backed store rather than only the in-memory `SessionRegistry`
  cache.
- Ordered by `lastActivityAt` descending — the most recently active
  conversation first (spec.md Assumptions).
- No pagination — the full list is always returned in one response
  (spec.md Assumptions; not expected to be needed at the target scale of a
  single local user).
- No messages are included in this response — retrieving a specific
  session's full history is a separate call to the existing
  `GET /sessions/{sessionId}/messages`, unchanged.
- When no sessions exist yet, returns `200 OK` with `{"sessions": []}`, not
  an error (spec.md Edge Cases / Acceptance Scenario 1.3).

Failure paths: none specific to this endpoint — it always succeeds when the
chat API itself is reachable (matching FR-008's local-only reachability,
which applies the same way to this route as every other).

## `GET /sessions/{sessionId}/messages` — unchanged

Still exactly as defined by 014 and confirmed by 025: a single, complete
`SessionHistoryResponse` JSON body containing the session's full, correctly
ordered message history, including a clear `404` / `session_not_found`
error for an unknown `sessionId`. `GET /sessions` (above) is what a caller
now uses first, when it does not already know a `sessionId`, to discover
which one to call this with.
