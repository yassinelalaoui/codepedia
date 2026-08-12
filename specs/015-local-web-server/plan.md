# Implementation Plan: Local Web Server

Branch: `015-local-web-server` | Date: 2026-08-12 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/015-local-web-server/spec.md`

## Summary

Extend the existing chat API server (`chat_api`, feature 014) so the same
running FastAPI/uvicorn process also serves the generated documentation
wiki's static files (`doc_generator`'s `outputRoot`, features 012/013).
Static wiki serving is added via Starlette's `StaticFiles` mounted at `/`,
registered after the chat API's explicit routes so `/sessions` and
`/sessions/{sessionId}/messages` are always matched first and the wiki mount
only ever catches everything else. No new server, package, or dependency is
introduced; the server continues to bind to `127.0.0.1` by default exactly
as 014 already established.

## Technical Context

Language/Version: Python 3.11+, consistent with the rest of the toolchain

Primary Dependencies: FastAPI + uvicorn (existing, from 014); Starlette's
`StaticFiles` (already a transitive dependency of FastAPI — no new package
required); reuses `chat_api` (014) and the on-disk output of `doc_generator`
(012/013) unchanged

Storage: No new persistence. Reads the existing `doc_generator` `outputRoot`
directory (already-generated static HTML/JS files) directly from disk;
reuses the existing in-memory chat session registry from 014 unchanged

Testing: pytest, using FastAPI's in-process `TestClient` to request wiki
paths (home, a module page, a diagram page, its static asset) against a
real `doc_generator`-produced output directory, plus a reused live-socket
test (per 014's `test_chat_api_network_boundary.py` pattern) to confirm the
combined server still only accepts `127.0.0.1` by default

Target Platform: Runs as the same local process 014 already describes
(Windows/macOS/Linux); consumed by a standard web browser on `localhost` or
the user's local network

Project Type: Extension of the existing `chat_api` package; no new package
is introduced

Performance Goals: Interactive, single-user local browsing and chat; no
concurrent-load or throughput target (unchanged from 014)

Constraints: Server MUST continue to bind to `127.0.0.1` by default (014's
existing constraint, unchanged); wiki paths and chat API paths MUST never
collide or shadow one another; the server MUST start even if the wiki has
not yet been generated (Edge Case), serving standard 404s for wiki paths
until it has been

Scale/Scope: One generated wiki (one repository's documentation output)
served per running server instance, consistent with 014's single-repository
scope for the chat API

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentialite absolue: pass; the server only serves files already
  produced locally by `doc_generator` and exposes the already-local chat
  API; no new outbound calls are introduced
- Zero exposition reseau par defaut: pass; reuses 014's `127.0.0.1` default
  bind unchanged — this feature adds a mount to the same app, not a new
  network surface
- Jamais de repli silencieux vers le cloud: pass; not applicable, no new
  inference path is introduced
- Tracabilite des reponses IA: pass; the chat API's response shape and
  citations (014) are untouched by this feature
- Re-indexation incrementale: not applicable; this feature does not
  regenerate the wiki, it only serves whatever has already been generated
- Infrastructure minimale et stockage local: pass; no new dependency
  (Starlette's `StaticFiles` already ships with FastAPI) and no new
  persistent storage — purely serves existing on-disk files
- Depot analyse en lecture seule: pass; the server only reads the
  already-generated `outputRoot` (itself already outside the analyzed
  repository per 012's containment rule), never writes to it or to the
  analyzed repository

## Project Structure

### Documentation for this feature

`specs/015-local-web-server/`
- `spec.md`
- `plan.md`
- `research.md`
- `data-model.md`
- `quickstart.md`
- `contracts/`
  - `wiki-serving.md`

### Source Code

`src/`
- `chat_api/`
  - `app.py` (modified: `create_app(...)` gains a `docs_root` parameter and
    mounts `StaticFiles(directory=docs_root, html=True, check_dir=False)` at
    `/`, registered after the existing chat routes)
  - `server.py` (modified: new required `--docs-root` CLI argument, passed
    through to `create_app(...)`; prints a clear diagnostic at startup when
    `docs_root/index.html` is missing)
- `doc_generator/` (reused, unmodified: produces the `outputRoot` this
  feature serves)

`tests/`
- `integration/test_local_web_server.py` (new: serves a real
  `doc_generator`-produced wiki through the combined app and requests its
  home page, a module page, a diagram page, and its static asset; verifies
  chat API routes still resolve correctly alongside the mount; reuses the
  live-socket local-only check from 014's `test_chat_api_network_boundary.py`
  pattern)

Structure Decision: extend the existing `chat_api` package rather than
introduce a new one. The running process this feature describes literally
is the server 014 already built — US2 requires wiki browsing and the chat
API to be reachable from the "same running server instance," so adding a
second package/process would contradict the spec rather than satisfy it.
This mirrors 013's choice to extend `doc_generator` in place rather than
add a new package for a closely coupled enhancement.

## Phase 0: Research

### Decision 1

Extend the existing `chat_api` FastAPI app with a static-file mount for the
wiki, rather than building a new server or running two processes, since 014
already owns the "local web server" role and US2 requires one running
instance for both.

### Decision 2

Serve the wiki via Starlette's `StaticFiles(directory=docs_root, html=True,
check_dir=False)`, mounted at `/` with `app.mount("/", ...)` **after** the
chat API's explicit routes, so route-registration order alone
deterministically resolves any wiki-path-vs-chat-route ambiguity.

### Decision 3

At server startup, check whether `docs_root/index.html` exists and print a
clear, non-blocking diagnostic if it does not, addressing the "wiki not yet
generated" edge case without a bespoke error page.

### Decision 4

Do not require `docs_root` to exist at server startup; the server starts
regardless and serves standard 404s for wiki paths until the wiki appears,
keeping generate-then-serve and serve-then-generate both possible.

### Decision 5

No new dependency is added; `StaticFiles` comes from `starlette.staticfiles`,
already installed transitively by `fastapi` (014).

## Phase 1: Design

### Data model

No new persisted entities. `LocalWebServer` and `WikiStaticAsset` (spec.md
Key Entities) are configuration/serving concepts, not new data structures —
see `data-model.md` for how they map onto the existing `chat_api.app`,
`chat_api.server`, and `doc_generator` output. Reuses `DocumentationSet` /
`DocPage` (012, read-only, on-disk) and every existing `chat_api` (014)
schema unchanged.

### Contracts

Document the wiki-serving surface (path shapes, `html=True` resolution
behavior, 404 behavior, and the routing-precedence rule that keeps chat API
paths from ever being shadowed by the static mount) in
`contracts/wiki-serving.md`. The chat API's own contract
(`specs/014-local-chat-api/contracts/chat-api.md`) is unchanged and is
referenced, not duplicated.

### Quickstart

Provide validation steps that generate a wiki, start the combined server,
browse the home/module/diagram pages and confirm the diagram's static asset
loads, exercise the chat API at the same local address, confirm a server
started before the wiki exists still serves the chat API and returns clean
404s for wiki paths, and confirm the local-only bind default still holds.

## Constitution Check After Design

No violations introduced by the chosen design. No new dependency, no new
persistent storage, no new outbound network path, and the analyzed
repository's read-only status and the documentation output's containment
guarantees (012) are both unaffected.
