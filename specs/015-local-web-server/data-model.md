# Data Model: Local Web Server

This feature adds no new persisted data structures. It wires together two
existing, unmodified systems behind one running server and reuses their
entities as-is.

## Reused entities

- **`DocumentationSet` / `DocPage`** (`doc_generator`, feature 012, and its
  Mermaid extension in 013): the already-generated wiki content on disk
  under `outputRoot`. This feature only reads these files from disk via
  `StaticFiles`; it does not parse, index, or hold them in memory.
- Every `chat_api` (014) entity — `SessionRegistry`, `CreateSessionResponse`,
  `AskQuestionRequest`/`AskQuestionResponse`, `ChatMessageView`,
  `SessionHistoryResponse`, `ApiErrorResponse` — unchanged. This feature adds
  no new fields, endpoints, or behavior to the chat API itself.

## Configuration-level concepts (spec.md Key Entities)

These map onto existing code structures rather than new dataclasses:

### LocalWebServer

The single running local process. Concretely: the `chat_api.app`
`FastAPI` instance returned by `create_app(vector_index, embedding_engine,
llm_engine, docs_root)`, run via `chat_api.server.main()` /
`uvicorn.run(...)`, bound to `127.0.0.1` by default (unchanged from 014).

Fields (as `create_app`/CLI parameters, not a persisted object):
- `docs_root` — the `doc_generator` `outputRoot` directory this instance
  serves as the wiki (new in this feature).
- `vector_index`, `embedding_engine`, `llm_engine` — the chat API's existing
  shared dependencies (014, unchanged).
- `host`, `port` — the existing bind configuration (014, unchanged; default
  `host="127.0.0.1"`).

Validation:
- `docs_root` MAY be absent or empty at startup (Decision 4); the server
  still starts. A missing `docs_root/index.html` at startup triggers the
  Decision 3 diagnostic but is not a startup failure.

### WikiStaticAsset

A generated wiki page or a static resource it depends on, served as-is from
`docs_root` by `StaticFiles`. Not a new Python type — this is Starlette's
own file-serving behavior (MIME type detection, byte-range support, 404 for
missing paths) applied to whatever `doc_generator` has written under
`docs_root` (`index.html`, `modules/*.html`, `diagrams/*.html`,
`assets/mermaid.min.js`, and their `.md` counterparts).

Relationships:
- Every `WikiStaticAsset` path is relative to `docs_root`, exactly matching
  the relative output paths `doc_generator.links` already computes
  (`index.html`, `modules/{slug}.html`, `diagrams/{slug}.html`,
  `assets/mermaid.min.js`) — this feature introduces no new path scheme.

## Routing precedence (not a data entity, but load-bearing for this model)

The chat API's routes and the wiki's `StaticFiles` mount coexist on one
`FastAPI` app instance. Because Starlette matches routes in the order they
were registered, and the chat routes are registered before the `/` mount
(Decision 2), a request path is resolved unambiguously:

1. `POST /sessions` → chat API (014), never the wiki mount.
2. `POST /sessions/{sessionId}/messages` → chat API (014), never the wiki
   mount.
3. `GET /sessions/{sessionId}/messages` → chat API (014), never the wiki
   mount.
4. Any other path → the wiki mount, resolved against `docs_root`; a path
   with no matching file returns a standard `404`.
