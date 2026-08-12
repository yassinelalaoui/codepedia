# Local Chat API Contract

## Purpose

Define the HTTP endpoints this feature exposes over the existing
`chat.ChatSession` pipeline, their request/response schemas, status codes,
and the default local-only network binding every endpoint is served behind.

## Network binding

- The server binds to `127.0.0.1` by default. Binding to any other address
  (including a local/private LAN address) requires an explicit `--host`
  argument at startup; there is no default that resolves to a
  publicly-reachable interface.
- Every endpoint below is served under that same bind restriction — there is
  no per-endpoint override.

## `POST /sessions`

Create a new chat session.

Request body: none.

Response `201 Created`:

```json
{ "sessionId": "b7e2b8f0f1c94db3ae1b8b9a0e6a2b3d" }
```

Behavior:
- Always succeeds (no failure mode defined for session creation itself,
  beyond generic server errors).
- The returned `sessionId` is immediately valid for the two endpoints below.
- The session starts with empty history.

## `POST /sessions/{sessionId}/messages`

Ask a question within an existing session.

Request body:

```json
{ "question": "where is authentication handled?" }
```

Response `200 OK`:

```json
{
  "answer": "Authentication is handled by authenticate_user.",
  "citedSymbolIds": ["auth.authenticate_user"],
  "citedFilePaths": ["src/auth/login.py"]
}
```

Response `404 Not Found` (unknown `sessionId`):

```json
{ "code": "session_not_found", "message": "No session with id '...'." }
```

Response `422 Unprocessable Entity` (empty/whitespace-only `question`):

```json
{ "code": "empty_question", "message": "question must not be empty." }
```

Response `503 Service Unavailable` (local embedding engine or local model
unavailable):

```json
{
  "code": "local_dependency_unavailable",
  "message": "Local LLM is unavailable; ChatSession cannot answer without it."
}
```

Behavior:
- On `200`, the question and the generated answer are appended, in order, to
  the session's history before the response is returned.
- On `404`, `422`, or `503`, nothing is appended to the session's history.
- `citedSymbolIds` and `citedFilePaths` are always present, and are empty
  arrays (not omitted) when the answer has no evidence to cite.

## `GET /sessions/{sessionId}/messages`

Read a session's full message history.

Response `200 OK`:

```json
{
  "sessionId": "b7e2b8f0f1c94db3ae1b8b9a0e6a2b3d",
  "messages": [
    {
      "role": "user",
      "content": "where is authentication handled?",
      "citedSymbolIds": [],
      "citedFilePaths": [],
      "timestamp": "2026-08-12T10:00:00+00:00"
    },
    {
      "role": "assistant",
      "content": "Authentication is handled by authenticate_user.",
      "citedSymbolIds": ["auth.authenticate_user"],
      "citedFilePaths": ["src/auth/login.py"],
      "timestamp": "2026-08-12T10:00:01+00:00"
    }
  ]
}
```

Response `404 Not Found` (unknown `sessionId`): same shape as above,
`code: "session_not_found"`.

Behavior:
- `messages` is `[]` (with `200`, not `404`) for a session that exists but
  has never been asked a question.
- Message order matches the order questions were successfully asked.

## Failure expectations

- No endpoint ever returns a fabricated or partial answer when the local
  model/embedding engine is unavailable; `503` is returned before any answer
  text is generated.
- No endpoint makes an outbound network request to a host other than the
  already-local embedding/LLM engines' configured `localhost` endpoints.
- A request from outside the bound local/private interface is refused at the
  network level (connection not accepted) rather than reaching any endpoint
  handler.