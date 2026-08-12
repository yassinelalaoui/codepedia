# Quickstart: Local Web Server

## Prerequisites

- Python 3.11 or later, local project dependencies installed (no new
  dependency beyond what 014 already added)
- A sample repository already indexed, with a documentation wiki already
  generated into a `docs_root` directory via the existing `doc_generator`
  pipeline (012/013), including at least one module with a diagram page
- A populated local `VectorIndex` (007) and a running local embedding
  engine and local LLM (008/009) reachable on `localhost`, as required by
  the chat API (014)
- A standard, modern web browser

## Validate browsing the wiki through the server

1. Start the server with `--docs-root` pointed at the generated wiki's
   output directory, and no `--host` argument.
2. Open a browser at `http://127.0.0.1:8000/` (or the configured port).
3. Confirm the wiki's home page renders — the same content as opening
   `docs_root/index.html` directly from disk.
4. Follow a link to a module page and confirm it renders correctly through
   the server.
5. Follow a link to that module's diagram page and confirm the interactive
   diagram renders (its script asset loads from `/assets/mermaid.min.js`
   through the server, not from a local file reference).

## Validate the chat API is reachable at the same address

1. With the server still running from the previous section, create a
   session:

   ```sh
   curl -s -X POST http://127.0.0.1:8000/sessions
   ```

2. Ask a question using the returned `sessionId`, and read its history —
   both exactly as described in `specs/014-local-chat-api/quickstart.md`.
3. Confirm both operations succeed against the same host/port the wiki was
   just browsed on, with no second server or port involved.

## Validate the server starts before the wiki exists

1. Point `--docs-root` at an empty or nonexistent directory and start the
   server.
2. Confirm the server starts successfully and prints a clear message
   indicating the wiki has not been generated yet.
3. Request `http://127.0.0.1:<port>/` and confirm a standard `404` response
   (not a crash, not a blank success response).
4. Confirm the chat API (`POST /sessions`, etc.) still works normally in
   this state.
5. Generate the wiki into that same `docs_root` while the server keeps
   running, then repeat step 3 and confirm the home page now renders.

## Validate the local-only default binding

Reuses the same approach as `specs/014-local-chat-api/quickstart.md`'s
"Validate the local-only default binding" section — this feature does not
change the bind configuration, only what is served on it.

1. Start the server with no `--host` argument.
2. Confirm (e.g. via `netstat`/`ss`) the listening socket is bound to
   `127.0.0.1`, not a LAN-visible address.
3. Confirm an attempt to reach the server via the machine's LAN address
   fails to connect.
4. Restart with an explicit `--host <local-network-address>` and confirm
   the wiki and chat API both become reachable at that address instead.

## Expected result

Running the server's single startup command makes the entire generated
wiki browsable at a localhost address and makes the chat API reachable at
that same address, with no second process or port; wiki paths and chat API
paths never collide; the server starts and serves the chat API even before
a wiki has been generated, and picks up the wiki once it appears; and the
server remains unreachable from outside the local machine/network without
an explicit `--host` opt-in.
