# Quickstart: Chat Session Persistence

## Prerequisites

- A repository already indexed (`codepedia index /path/to/repo`), with a
  local embedding engine and local LLM reachable on `localhost`.
- `curl` (or an equivalent local HTTP client).
- Access to the repository's state directory to inspect the SQLite file
  directly, if you want to confirm rows exist between steps:
  `~/.codepedia/repos/<state-id>/repository-metadata.sqlite`
  (`sqlite3 <path> ".tables"` / `.schema chat_sessions`).

This validates spec.md's User Stories 1–3 and Success Criteria SC-001–SC-004.

## Validate: a session survives a full server restart (US1 / SC-001)

1. Start the server: `codepedia serve /path/to/repo`.
2. Create a session and ask two or three questions, noting the `sessionId`:

   ```sh
   curl -s -X POST http://127.0.0.1:8000/sessions
   curl -s -X POST http://127.0.0.1:8000/sessions/<sessionId>/messages \
     -H "Content-Type: application/json" \
     -d '{"question": "where is authentication handled?"}'
   ```

3. Fetch and save the current history for comparison:

   ```sh
   curl -s http://127.0.0.1:8000/sessions/<sessionId>/messages
   ```

4. Stop the server process entirely (not just the watcher — the whole
   process), then start it again: `codepedia serve /path/to/repo`.
5. Fetch history for the same `sessionId` again. Confirm it is byte-for-byte
   identical to step 3's result — same messages, same order, same
   `citedSymbolIds`/`citedFilePaths`, same timestamps.
6. Fetch history for a `sessionId` that was never created. Confirm `404`
   with `code: "session_not_found"` — not an empty `200`.

## Validate: a session survives a wiki page reload without a server restart (US2 / SC-002)

1. With the server still running from the previous section, open the wiki
   in a browser and use the chat panel to ask a question.
2. Reload the page.
3. Confirm the chat panel shows the prior conversation restored, not a blank
   chat — without asking the question again.

## Validate: appending a message does not rewrite session history (US3 / SC-003)

1. Create a fresh session and append messages one at a time (a small script
   loop is fine — e.g. 20–50 `POST .../messages` calls is enough to observe
   the pattern; spec.md's SC-003 threshold is 500).
2. After each append, confirm the previously-asked questions/answers are
   still present, unchanged, in a `GET .../messages` call.
3. Optionally, confirm via `EXPLAIN QUERY PLAN` or timing that each append
   is a constant-time operation (a single-row `INSERT` plus a single-row
   `UPDATE` on `chat_sessions.last_activity_at`) — it should not visibly
   slow down as the session grows from 1 to 50 messages.

## Validate: full history in one request (SC-004)

1. Using the session built up in the previous section, fetch its history:

   ```sh
   curl -s http://127.0.0.1:8000/sessions/<sessionId>/messages
   ```

2. Confirm the single response contains every message exchanged so far, in
   order — no pagination parameters, no follow-up requests needed.

## Automated coverage

These same scenarios are what the feature's tests exercise directly (see
plan.md's Project Structure): a restart is simulated in
`tests/integration/test_chat_session.py` by closing and reopening the
SQLite connection between two `chat.sqlite_store` calls (rather than an
actual process restart), which is equivalent for this feature's purposes
since all session state lives in that file.
