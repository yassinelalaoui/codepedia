# Wiki Serving Contract

## Purpose

Define how the combined local server serves the generated documentation
wiki alongside the existing chat API, and the precedence rule that keeps
the two from ever colliding on the same running instance.

This document covers only the wiki-serving surface added by this feature.
The chat API's own request/response contract is defined in
`specs/014-local-chat-api/contracts/chat-api.md` and is unchanged — refer to
it directly rather than duplicating it here.

## Network binding

Unchanged from 014: the server binds to `127.0.0.1` by default; binding
elsewhere requires an explicit `--host` argument at startup. The wiki and
the chat API are served from that same bound address — there is no separate
bind configuration for either.

## Wiki routes

| Path pattern | Resolves to | Notes |
|---|---|---|
| `GET /` | `docs_root/index.html` | The wiki's home page, per `html=True` directory-index resolution |
| `GET /modules/{slug}.html` | `docs_root/modules/{slug}.html` | A module documentation page (012) |
| `GET /diagrams/{slug}.html` | `docs_root/diagrams/{slug}.html` | A module's interactive dependency diagram page (013) |
| `GET /assets/mermaid.min.js` | `docs_root/assets/mermaid.min.js` | The vendored diagram-rendering script (013) |
| `GET /{any-other-path}` | `docs_root/{any-other-path}` if present, else `404` | Any other file `doc_generator` has written under `docs_root` |

Behavior:
- A path with no corresponding file under `docs_root` returns `404 Not
  Found` (Starlette's standard `StaticFiles` behavior).
- If `docs_root` itself does not exist yet, `create_app` creates it (empty)
  before mounting, so every wiki path returns `404` until real content
  appears there (Decision 4) — the server does not crash or refuse to
  start.
- Response `Content-Type` is determined by file extension (`.html`, `.js`,
  `.md`, etc.) via Starlette's standard MIME type detection.

## Routing precedence

The chat API's routes are registered on the `FastAPI` app before the wiki's
`StaticFiles` mount at `/`. Starlette matches routes in registration order,
so:

- `POST /sessions` always resolves to the chat API (014), never to a file
  lookup under `docs_root`.
- `POST /sessions/{sessionId}/messages` always resolves to the chat API,
  never to a file lookup.
- `GET /sessions/{sessionId}/messages` always resolves to the chat API,
  never to a file lookup.
- Every other path is resolved against `docs_root` by the wiki mount.

This ordering guarantee holds regardless of what `doc_generator` ever
writes under `docs_root`, because `doc_generator`'s own output paths
(`index.html`, `modules/*`, `diagrams/*`, `assets/*`) never produce a
top-level `sessions` path — but the precedence rule is enforced structurally
by registration order, not by coincidence of naming.

## Startup expectations

- The server MUST start successfully whether or not `docs_root` currently
  contains a generated wiki.
- If `docs_root/index.html` is missing at startup, the server MUST print a
  clear, human-readable diagnostic to the console before continuing to
  serve (Decision 3). This is a startup-time message only, not part of the
  HTTP response contract.
