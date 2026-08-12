# Quickstart: Local Chat API

## Prerequisites

- Python 3.11 or later, local project dependencies installed (including the
  new `fastapi`/`uvicorn` dependencies this feature adds)
- A sample repository already indexed with a populated local `VectorIndex`
  (feature 007) and a running local embedding engine and local LLM (features
  008/009) reachable on `localhost`
- `curl` (or an equivalent local HTTP client) and, for the network-boundary
  check, a second machine on the same local network (optional — this check
  can also be reasoned about from `netstat`/`ss` output on one machine)

## Validate the local-only default binding

This same-machine LAN-interface refusal is also covered by an automated
test (`tests/integration/test_chat_api_network_boundary.py`); the steps
below add a manual, cross-machine confirmation on top of it.

1. Start the server with no `--host` argument.
2. Confirm (e.g. via `netstat`/`ss`) that the listening socket is bound to
   `127.0.0.1`, not `0.0.0.0` or a LAN-visible address.
3. From another machine on the local network (or by attempting to connect to
   the machine's LAN IP instead of `127.0.0.1`), confirm the connection is
   refused.
4. Restart the server with an explicit `--host <local-network-address>` and
   confirm the connection now succeeds only after that explicit opt-in.

## Validate creating a session and asking a question

1. With the server running on `127.0.0.1`, create a session:

   ```sh
   curl -s -X POST http://127.0.0.1:8000/sessions
   ```

   Confirm the response contains a `sessionId`.

2. Ask a question about the indexed repository, using the returned
   `sessionId`:

   ```sh
   curl -s -X POST http://127.0.0.1:8000/sessions/<sessionId>/messages \
     -H "Content-Type: application/json" \
     -d '{"question": "where is authentication handled?"}'
   ```

   Confirm the response contains `answer`, `citedSymbolIds`, and
   `citedFilePaths`, and that the cited files/symbols are real locations in
   the indexed repository.

## Validate reading session history

1. Using the same `sessionId`, fetch history:

   ```sh
   curl -s http://127.0.0.1:8000/sessions/<sessionId>/messages
   ```

2. Confirm the response's `messages` array contains, in order, the user
   question from the previous step followed by the assistant's answer, and
   that the assistant message's citations match the previous response.
3. Create a second, unused session and fetch its history; confirm it returns
   `200` with an empty `messages` array.

## Validate explicit, structured failure when the local model is unavailable

1. Stop the local LLM (or local embedding) service the server is configured
   against.
2. Ask a question on an existing session, as above.
3. Confirm the response status is `503`, the body's `code` field is
   `"local_dependency_unavailable"`, and no answer text is returned.
4. Fetch that session's history and confirm the failed attempt was not
   recorded — the history is unchanged from before the failed question.

## Validate no outbound network requests occur

1. While asking a question that succeeds (local services running), monitor
   outbound connections from the server process (e.g. via `netstat` or an
   OS-level connection monitor).
2. Confirm the only connections observed are to the configured local
   embedding/LLM endpoints on `localhost`, and nothing to any other host.

## Expected result

A local HTTP client can create a session, ask a question, and receive a
structured `200` response with the generated answer and its cited
symbols/files, entirely via requests to `127.0.0.1`; the same client can
retrieve that session's history and see it match what was asked; the server
refuses connections from outside the local machine/network without an
explicit `--host` opt-in; and an unavailable local model produces an
explicit `503` instead of any fabricated answer.
