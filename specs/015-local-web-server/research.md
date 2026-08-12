# Research: Local Web Server

## Decision 1: Extend the existing `chat_api` app rather than build a new server or run two processes

Decision: Add wiki static-file serving directly to the existing `chat_api`
FastAPI app (014) — `create_app(...)` gains a `docs_root` parameter — rather
than introducing a second server process or a new package.

Rationale: `chat_api` already exists, already binds to `127.0.0.1` by
default, and already owns the "local web server" role for this project.
Running a second server/process for the wiki would directly violate the
spec's "a single startup action MUST make both reachable" requirement and
the "no separate server process" acceptance criterion (US2) — those
requirements only make sense if there is exactly one running instance.

Alternatives considered: A separate static-file server process on a second
port was rejected — it would require the user to start two commands and
would reintroduce exactly the "two disconnected local addresses" problem
this feature exists to close. A reverse proxy in front of two backend
processes was rejected as unnecessary infrastructure for a single-user local
tool, contradicting the constitution's minimal-infrastructure principle
(2.6).

## Decision 2: Mount Starlette's `StaticFiles` at `/`, registered after the chat API's routes

Decision: Serve the wiki via `StaticFiles(directory=docs_root, html=True,
check_dir=False)`, mounted with `app.mount("/", ...)` **after** the chat
API's explicit routes (`/sessions`, `/sessions/{sessionId}/messages`) are
registered.

Rationale: Starlette's router matches routes in registration order — an
explicit path operation registered before a mount always wins over that
mount's catch-all match for the same path, so registration order alone
deterministically resolves the spec's "a request path could be interpreted
as either wiki content or a chat API operation" edge case, with no path
prefix or extra namespacing required. `html=True` makes `/` resolve to
`index.html` automatically, matching the wiki's existing home-page
convention (012), and directory-style requests behave like a normal static
site (e.g. a trailing-slash directory request resolves to its `index.html`
if present).

Note: `check_dir=False` only skips `StaticFiles`'s *constructor*-time
existence check — Starlette's `StaticFiles.__call__` re-checks that
`directory` exists on the *first incoming request* regardless, raising an
uncaught `RuntimeError` (a hard 500) if it is still missing at that point.
`check_dir=False` alone is therefore insufficient to satisfy Decision 4;
`create_app` also eagerly creates `docs_root` (`mkdir(parents=True,
exist_ok=True)`) before mounting, exactly mirroring
`DocumentationWriter.__post_init__`'s own `mkdir` (012), so the directory
always exists by the time any request arrives and a not-yet-generated wiki
degrades to ordinary `404`s instead of a crash.

Alternatives considered: A custom catch-all route that manually reads files
from `docs_root` was rejected as reimplementing what `StaticFiles` already
does correctly (MIME type detection, range requests, 404 handling, and path
traversal protection). Prefixing wiki routes under `/wiki/` was rejected
because it would require the entire already-generated site — particularly
the home page, which US1 and 012 both anchor at `/` — to change its base
path, and no such prefixing is needed once registration order alone
resolves the collision concern.

## Decision 3: Print a clear, non-blocking startup diagnostic when the wiki has not been generated yet

Decision: At server startup, check whether `docs_root/index.html` exists.
If it does not, print a clear message (e.g. instructing the user to run the
documentation-generation pipeline first) to the console, without blocking
or delaying server startup.

Rationale: The spec's edge case requires the server to "clearly indicate
the wiki is not yet available" rather than serve a blank or broken page.
A one-time, clear startup diagnostic addresses the "wiki not generated at
all" case specifically, while an individual missing page/resource still
resolves to `StaticFiles`'s standard 404 (the spec's separate "requested
page does not exist" edge case) — the two edge cases are deliberately
handled differently since they represent different situations for the user.

Alternatives considered: A custom "wiki not generated yet" HTML page served
in place of ordinary 404s was considered and rejected as speculative
browser-side UI work that belongs to the web interface this feature
explicitly does not build (spec Non-Goals), not to this serving layer.

## Decision 4: Do not require `docs_root` to exist at server startup

Decision: The server starts regardless of whether `docs_root` (or its
`index.html`) exists yet; wiki paths simply 404 until the wiki appears.

Rationale: Requiring the wiki to already exist before the server can start
would block US2 (using the chat API) in a workflow where a user wants chat
available before or while a first documentation-generation run completes,
and would be inconsistent with Decision 3's non-blocking diagnostic. This
keeps both orderings — generate-then-serve and serve-then-generate — valid,
which is a reasonable default absent any spec requirement to enforce
ordering.

Alternatives considered: Failing fast with a hard startup error if
`docs_root` is missing was rejected as an ordering constraint the spec does
not ask for — the spec only requires a *clear indication*, not that the
server refuse to run.

## Decision 5: No new dependency

Decision: Import `StaticFiles` from `starlette.staticfiles` without adding
an explicit `starlette` entry to `pyproject.toml`.

Rationale: `starlette` is already installed transitively as FastAPI's own
dependency (added in 014) and is confirmed importable in the current
environment; adding an explicit line would be redundant version pinning for
something FastAPI itself already constrains, and risks the two drifting out
of sync over time.

Alternatives considered: Adding an explicit `starlette>=...` line for
directness/documentation purposes was considered and rejected as
unnecessary given FastAPI's own dependency bound already governs the
compatible Starlette version.
