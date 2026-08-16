# Technology Stack

What this project is built with, and why each piece was chosen. Specs 001–016
predate this document; their choices are reported here from evidence in the code and
each spec's `research.md`, not re-litigated. 017 (watcher) and 018 (reindex pipeline)
are where dependency choices were made directly alongside this document.

> Maintenance: update this file whenever a dependency is added, removed, or its
> role changes — the same rule as the root [`README.md`](../README.md) and
> `docs/architecture.md`.

## Language & runtime

**Python 3.11**, single interpreter for the entire backend (`pyproject.toml`,
`requires-python = ">=3.11"`). One language end-to-end (scanner → parser → graph → AI
pipeline → web server) keeps the whole system easy to reason about and matches the
constitution's "infrastructure minimale" principle — no polyglot backend to operate.
This is also why 017 rejected `chokidar` (Node.js) even though it was offered as an
option: it would have split the backend into two runtimes for one component.

## CLI

**Typer** (`repo_scanner/cli.py`, now also `cli/main.py`) — thin, typed CLI
wrapper for a Python function. Standard choice for a local dev tool's entry
point. 019 (CLI orchestrator) reuses this same dependency for its `index`/
`serve`/`config` commands — no new dependency was introduced — and moved the
project's `[project.scripts]` console-script target from
`repo_scanner.cli:app` to `cli.main:app`, which now also re-registers 001's
`scan` command unchanged, so `repo-scanner` stays the single entry point for
every command.

## Multi-language parsing

**Tree-sitter** + one grammar package per language (`tree-sitter-python`,
`-javascript`, `-typescript`, `-java`, `-go`, `-rust`), with Python's own `ast` module
used as a fast path for `.py` files specifically. Tree-sitter is the only realistic
way to get a real, incremental-friendly AST across six languages without hand-writing
six parsers — it is local (no network), fast, and error-tolerant (keeps producing a
tree even with syntax errors, which matters for the "report a failure, keep going"
edge case in the parser spec).

## Dependency graph

**Hand-rolled** (`dependency_graph/graph.py`'s `_SimpleDiGraph` — a dict of nodes plus
a dict of edges keyed by `(source, target, type)`), *not* a graph library. The actual
query needs are narrow (`dependents()`, `dependencies()`, `exportDiagram()`), so a
purpose-built structure was simpler than pulling in a general-purpose graph library.

## Local persistence

**SQLite via the Python stdlib `sqlite3`** — used independently by four components
(`repository_metadata`, `dependency_graph`'s snapshot store, `vector_index`'s
storage, `doc_generator`'s page manifest). Zero-ops, file-based, no server process —
a direct requirement of constitution principle 2.6 ("pas de serveur de base de
données externe... stockage embarqué uniquement"). Each component keeps its own
SQLite file rather than sharing one schema, trading some duplicated
connection-handling code for simpler ownership boundaries.

## Local AI access (LLM + embeddings)

**Raw HTTP via `urllib.request`** (stdlib, no SDK) against an **Ollama-compatible**
local endpoint convention (`http://localhost:11434`, `/api/tags` for availability, a
generate/embeddings endpoint for the call itself). Two near-identical components,
`local_llm` and `embedding_engine`, each independently check availability first, then
call. Why this shape:

- No SDK dependency for what is just two JSON HTTP calls — keeps the footprint
  minimal.
- The endpoint's host is validated to be loopback-only (`normalize_endpoint_url`
  rejects anything but `localhost` / `127.0.0.1` / `::1`) — constitution 2.1/2.3
  enforced in code, not just policy: it is structurally impossible to point this at a
  cloud API.
- Availability-check-before-call, everywhere, with a hard failure
  (`ServiceUnavailableError` / `LocalLLMUnavailableError`) instead of any fallback —
  constitution 2.3, "jamais de repli silencieux vers le cloud."

## Documentation rendering

**Jinja2** (page templates) + **Python-Markdown** (Markdown → HTML, with the
`attr_list` extension added in 016 so headings get stable anchor ids for
search/citation links) + a **vendored, locally-committed `mermaid.min.js`** for the
dependency diagrams. Vendored instead of a CDN `<script>` tag because of constitution
2.2 (zero network exposure) — a generated wiki page must render fully offline, so
nothing in the shipped HTML may reach out to a CDN.

## Web / API layer

**FastAPI + Uvicorn**, with Starlette's `StaticFiles` mounted to serve the generated
wiki from the same process that serves the chat API. FastAPI gives typed
request/response models (Pydantic schemas in `chat_api/schemas.py`) for very little
boilerplate, and binds to `127.0.0.1` by default — matching constitution 2.2 directly
(015's spec is built around this constraint). One process doing both jobs (static
wiki + chat API) rather than two was a deliberate simplicity choice, not a technical
necessity.

## File watching

**`watchdog`** (added in 017) — wraps each OS's native file-change notification API
(`ReadDirectoryChangesW` / `FSEvents` / `inotify`) behind one cross-platform
interface. Chosen over polling because it is event-driven (near-instant detection, no
CPU burned scanning) and over `chokidar` because it keeps the whole backend
single-language.

## Frontend (Wiki UI)

**React 18 + TypeScript + Vite**, tested with **Vitest + Testing Library**, built as
a **classic (non-`type="module"`) IIFE bundle** and committed into
`src/doc_generator/assets/`. Deliberate choices baked into that last point (016
`research.md`):

- Classic script, not an ES module — avoids CORS/MIME issues when the wiki is opened
  as a `file://` page outside the server, and keeps the "no CDN, no external script"
  guarantee airtight.
- The built bundle is committed to the repo, not built on the fly — so
  `doc_generator`'s output never depends on Node/npm being available at
  documentation-generation time, only at frontend-development time.

## Testing

**pytest** for the entire Python backend (`tests/unit`, `tests/integration`,
`tests/contract` — the layout every spec in this project follows), **Vitest +
`@testing-library/react`** for the frontend components.

## Packaging

**setuptools**, `src/` layout (`package-dir = {"" = "src"}`), one editable install
for the whole backend. Keeps every package (`repo_scanner`, `parser_engine`,
`dependency_graph`, ... `repo_watcher`) importable as siblings without path hacks
(aside from `tests/conftest.py` inserting `src/` onto `sys.path` for test discovery).

**PyInstaller** (020, build-time only — never a runtime dependency of the
shipped binary) turns that same codebase into a standalone, single-file
executable per OS, so an end user needs no Python interpreter at all (see
`packaging/pyinstaller/repo-scanner.spec`, `packaging/build.py`). Chosen
over Nuitka (needs a C compiler on every build machine; less predictable
bundling multiple native tree-sitter grammar packages) and over cx_Freeze
(smaller community, thinner docs for this native-extension-plus-data-file
combination) — see `specs/020-cli-packaging/research.md` §2. This also
surfaced a latent gap: `doc_generator`'s Jinja templates and static assets
had no `[tool.setuptools.package-data]` declaration at all, so only
*editable* installs (which read the source tree directly) happened to
include them — a real built wheel or binary silently omitted them. Fixed
alongside 020 (research.md §3).

**GitHub Actions** (020, `.github/workflows/release.yml`, tag-triggered
only) runs `packaging/build.py` on real Windows/macOS(x86_64)/Linux
runners and publishes the results as a GitHub Release. Added after this
project's own development machine turned out to be unable to complete a
local PyInstaller build at all (research.md §8's superseding decision) —
`packaging/build.py` itself is unchanged and still works standalone on
any unrestricted machine; CI is an additional path, not a replacement.

## Two loose ends

- **`pathspec`** and **`networkx`** are both declared in `pyproject.toml` but
  **unused** anywhere in `src/` — the scanner hand-rolled its own `.gitignore`
  matcher instead of `pathspec`, and the dependency graph hand-rolled its own
  adjacency structure instead of `networkx`. Not a functional problem, just dead
  weight in the dependency list; worth pruning if the manifest should reflect reality.
- **`httpx`** is declared and *is* used — but only transitively, because Starlette's
  `TestClient` requires it in the test suite. The app's own local-LLM/embedding HTTP
  calls use stdlib `urllib`, not `httpx`.
