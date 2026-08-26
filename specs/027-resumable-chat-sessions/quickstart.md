# Quickstart: Resumable Chat Sessions via Streaming, Listing & History

Validates this feature end-to-end against a running instance of the local
chat API (`src/chat_api`), reusing the same server setup as specs 014/025/026.

## Prerequisites

- A repository already indexed (`codepedia index ...`) so the local
  embedding engine and LLM engine are available.
- The local web server running (`codepedia serve ...`), exposing the
  chat API on `127.0.0.1` (see `docs/quickstart.md` / spec 015 for exact
  invocation).
- `curl` or any local HTTP client capable of reading a streamed response.

## Scenario 1 — List sessions, including one created before this run

1. Create a session and ask one question, so at least one session with
   history exists:
   ```sh
   curl -s -X POST http://127.0.0.1:8000/sessions
   # -> {"sessionId": "<id>"}
   curl -s -X POST http://127.0.0.1:8000/sessions/<id>/messages \
     -H "Content-Type: application/json" -d '{"question": "What does this repo do?"}'
   ```
2. Restart the local server process (`Ctrl+C`, then re-run `codepedia
   serve ...`) to prove listing does not depend on the in-memory cache.
3. List sessions:
   ```sh
   curl -s http://127.0.0.1:8000/sessions
   ```
   **Expected**: `200 OK`, a `sessions` array containing the `<id>` from
   step 1, with its original `createdAt` unchanged and `lastActivityAt`
   reflecting the question asked — present even though the server was
   just restarted (FR-002, contracts/chat-api-session-listing-delta.md).

## Scenario 2 — Empty list when nothing exists yet

Against a freshly initialized metadata database with no sessions created:

```sh
curl -s http://127.0.0.1:8000/sessions
```

**Expected**: `200 OK`, `{"sessions": []}` — not an error (spec.md
Acceptance Scenario 1.3).

## Scenario 3 — Resume: list, pick, retrieve identical history

1. From Scenario 1's list, pick `<id>`.
2. Retrieve its history:
   ```sh
   curl -s http://127.0.0.1:8000/sessions/<id>/messages
   ```
   **Expected**: `200 OK`, `SessionHistoryResponse` containing the same
   question and answer from step 1 of Scenario 1, in order, byte-identical
   to what was generated (spec.md SC-001, Acceptance Scenario 1.2).
3. Request the history of a made-up id:
   ```sh
   curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/sessions/does-not-exist/messages
   ```
   **Expected**: `404` (spec.md Acceptance Scenario 1.4, unchanged from
   spec 014).

## Scenario 4 — Progressive delivery is observable

```sh
curl -N -s -X POST http://127.0.0.1:8000/sessions/<id>/messages \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarize the main entry point."}'
```

**Expected**: multiple `data: {"fragment": "..."}` lines printed
progressively (visible arriving over time with `-N`, not all at once),
followed by one `event: done` line whose `answer` field equals every
printed fragment concatenated in order (spec.md SC-002, SC-003).

## Scenario 5 — Local-only reachability holds for the new route

From a second machine on the same network (or by binding a test client to
a non-loopback interface, per how spec 014's own equivalent scenario was
validated):

```sh
curl -s http://<host-machine-lan-ip>:8000/sessions
```

**Expected**: connection refused / unreachable, the same way an equivalent
request to `POST /sessions` already is today (spec.md SC-004, User
Story 3).

## Scenario 6 — Bundled UI actually shows progressive delivery

1. Open the served wiki (`http://127.0.0.1:8000/`) in a browser.
2. Ask a question in the chat panel.
   **Expected**: the assistant's reply visibly builds up progressively
   (word-by-word/chunk-by-chunk) rather than appearing all at once after a
   delay, and no console error is thrown (this is the regression
   `research.md` Decision 4 fixes — before this feature, the panel would
   throw parsing the SSE response as JSON).
3. Reload the page.
   **Expected**: the same conversation reappears via the existing
   `localStorage` + `getHistory` resume path (spec 025), unaffected by this
   feature's changes.
