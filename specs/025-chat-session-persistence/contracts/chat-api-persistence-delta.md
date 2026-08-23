# Chat API Contract — Persistence Delta

## Purpose

This feature adds no new HTTP endpoint and changes no request/response
schema from `specs/014-local-chat-api/contracts/chat-api.md`. It changes
only the durability guarantee behind the three existing endpoints. This
document records that delta rather than restating the unchanged contract.

## What changes

- **`POST /sessions`**: in addition to the existing behavior, the created
  session now also persists a `chat_sessions` row (see
  `chat-persistence-schema.md`). Still always succeeds; still returns
  `201` with the same body shape.
- **`POST /sessions/{sessionId}/messages`**: in addition to the existing
  behavior, a successful `200` now persists both the user question and the
  generated answer as individual `chat_messages` rows (incrementally — see
  `chat-persistence-interface.md#append_message`) before the response is
  returned. The `404` / `422` / `503` failure responses are unchanged, and
  still append nothing on failure.
- **`GET /sessions/{sessionId}/messages`**: now returns the session's
  history correctly **even if the server process serving this request is
  not the same process that handled the session's earlier
  `POST`s** — i.e. across a restart. Response shape, `200` vs `404`
  semantics, and empty-history-vs-unknown-session distinction are all
  unchanged from the 014 contract; only *which processes* can correctly
  answer this request changes (previously: only the one still holding the
  in-memory session; now: any process pointed at the same repository's
  `repository-metadata.sqlite`).

## What does not change

- No new endpoint, no new request/response field, no new status code.
- The local-only network binding (`127.0.0.1` by default) is unaffected.
- `citedSymbolIds` / `citedFilePaths` continue to always be present (never
  omitted) on every persisted-and-returned message, satisfying constitution
  2.4 (traceability) whether the message came from the in-memory cache or
  was just reloaded from SQLite.
