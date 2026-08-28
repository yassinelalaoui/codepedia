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
`scan` command unchanged, so `codepedia` stays the single entry point for
every command.

## Multi-language parsing

**Tree-sitter** + one grammar package per language (`tree-sitter-python`,
`-javascript`, `-typescript`, `-java`, `-go`, `-rust`), with Python's own `ast` module
used as a fast path for `.py` files specifically. Tree-sitter is the only realistic
way to get a real, incremental-friendly AST across six languages without hand-writing
six parsers — it is local (no network), fast, and error-tolerant (keeps producing a
tree even with syntax errors, which matters for the "report a failure, keep going"
edge case in the parser spec).

`parser_engine/treesitter_symbols.py` walks that AST to build the symbol
inventory for the brace languages; `extractor.py`'s line-oriented regex scanner
is now only the fallback, used when no grammar is available for a language.
A line-at-a-time scanner cannot see a signature that spans lines, an arrow
function bound to a `const`, a Rust `impl` block's methods or a Go method's
receiver — and it reads `if (…) {` as a declaration named `if`. On this
repository's own `frontend/`, switching the default path raised the real symbol
count from 49 to 78 and removed 35 such phantom symbols
(`python scripts/inventory_report.py <repo>` reproduces the comparison).

`.tsx` needs `tree_sitter_typescript.language_tsx()`: the plain TypeScript
grammar reports JSX as a syntax error, which would cost every React component.
`tree-sitter` itself is capped below `0.26` — `0.26.0` segfaults when a node's
point is read after its children have been walked, which crashes on any file of
a few thousand nodes.

## Dependency graph

**Hand-rolled** (`dependency_graph/graph.py`'s `_SimpleDiGraph` — a dict of nodes plus
a dict of edges keyed by `(source, target, type)`), *not* a graph library. The actual
query needs are narrow (`dependents()`, `dependencies()`, `exportDiagram()`), so a
purpose-built structure was simpler than pulling in a general-purpose graph library.

## Retrieval

**Hybrid search: vector similarity fused with SQLite FTS5 (BM25).** Vector search
alone buries an exact identifier under text that is merely semantically close, so
a lexical index runs alongside it and the two rankings are combined with
Reciprocal Rank Fusion. FTS5 is compiled into the stdlib's SQLite build, so this
costs no new dependency — the same reasoning that keeps the rest of persistence
on `sqlite3`.

Fusion decides the **order** only. `SearchResult.score` stays the raw cosine
similarity, because `chat/retrieval.py` compares it against absolute thresholds
(below 0.15 is "not enough evidence", within 0.05 of the top is "ambiguous"); an
RRF score of ~0.016 would trip both on every answer. A lexical-only hit is given
a cosine computed on demand from its stored vector.

Results are then reordered by **proximity in the dependency graph**: a chunk whose
symbol calls, is called by, or inherits from a symbol the conversation already
cited moves ahead of one that is merely textually similar. The graph was already
built for documentation and summarization; this is the retrieval path reading it.
Reranking is a stable partition, never a rescoring — scores stay untouched.

Similarity itself is still a brute-force cosine pass in Python over the in-memory
index, not an approximate-nearest-neighbour structure. That is the next
bottleneck, and the reason `vector_index`'s connection is now usable across
threads (see below).

## Local persistence

**SQLite via the Python stdlib `sqlite3`** — used independently by four components
(`repository_metadata`, `dependency_graph`'s snapshot store, `vector_index`'s
storage, `doc_generator`'s page manifest). Zero-ops, file-based, no server process —
a direct requirement of constitution principle 2.6 ("pas de serveur de base de
données externe... stockage embarqué uniquement"). Each component keeps its own
SQLite file rather than sharing one schema, trading some duplicated
connection-handling code for simpler ownership boundaries.

`vector_index` is the one component holding a **long-lived** connection (the
others open one per call), and it opens with `check_same_thread=False` behind its
own reentrant lock. `serve` opens the index on the main thread but writes from
the watcher's debounce timer thread and answers chat questions from uvicorn's
loop thread; sqlite3's default same-thread guard rejected both.

## Local AI access (LLM + embeddings)

**Raw HTTP via `urllib.request`** (stdlib, no SDK) for availability checks and
`embedding_engine`'s calls, against an **Ollama-compatible** local endpoint
convention (`http://localhost:11434`, `/api/tags` for availability, an embeddings
endpoint for the call itself). Two near-identical components, `local_llm` and
`embedding_engine`, each independently check availability first, then call. Why
this shape:

- No SDK dependency for what is otherwise just plain JSON HTTP calls — keeps the
  footprint minimal.
- The local endpoint's host is validated to be loopback-only
  (`normalize_endpoint_url` rejects anything but `localhost` / `127.0.0.1` / `::1`)
  — constitution 2.1/2.3 enforced in code, not just policy: it is structurally
  impossible to point the *local* engine at a cloud API.
- Availability-check-before-call, everywhere. A single engine still fails hard
  (`ServiceUnavailableError` / `LocalLLMUnavailableError`) with no fallback of
  its own; automatic failover only happens one layer up, in
  `provider_routing.FailoverExecutor`, and only within the operator's own
  explicitly configured chain (constitution 2.3, v3.0.0 — 029) — never as an
  undisclosed, out-of-chain cloud fallback.

**`httpx.AsyncClient`**/**`httpx`** (026, extended 029) for every remote-provider
call — `local_llm`'s Ollama streaming call, `GroqLLMEngine`'s Groq API call, and
(029) `OpenAIEmbeddingProvider`'s OpenAI embeddings call — since generation is
the one place this project needs a real async streaming HTTP response
(`generateStream`, consumed token-by-token as Server-Sent Events reach the chat
API). Every remote provider's endpoint is deliberately **not** run through
`normalize_endpoint_url` — that validator's loopback-only guarantee stays
specific to the local engine; a remote provider's own disclosed nature
(constitution 2.1 v3.0.0, `provider_routing` — 029) governs it instead. No new
HTTP client dependency was introduced by 029: `OpenAIEmbeddingProvider`'s
transport reuses the same already-a-direct-dependency `httpx`.

## Provider chains & failover (029)

**A new `provider_routing` package, no new dependency.** `FailoverExecutor`
(`provider_routing.router`) is stage-agnostic, plain-Python retry/classification
logic over whatever `(ProviderRef, engine)` pairs `provider_routing.factory`
resolves from a `CLIConfiguration` chain — no separate resiliency/retry library
(e.g. `tenacity`) was pulled in, since the retry policy here is deliberately
narrow (exactly the configured chain, exactly three classified failure
reasons) rather than a general-purpose one a library would be built for.
`engine_failover_log` is one additive SQLite table in the already-existing
`repository_metadata` file (`ALTER TABLE`-guarded the same way `chat_messages`
and `chunks` gained their own new columns), not a new database.

## Documentation rendering

**Jinja2** (page templates) + **Python-Markdown** (Markdown → HTML, with the
`attr_list` extension added in 016 so headings get stable anchor ids for
search/citation links, and the `toc` extension's `toc_tokens` read back to build
each page's section rail — which is why rendering builds an explicit `Markdown()`
instance per page rather than calling the module-level convenience function) + a **vendored, locally-committed `mermaid.min.js`** for the
dependency diagrams. Vendored instead of a CDN `<script>` tag because of constitution
2.2 (zero network exposure) — a generated wiki page must render fully offline, so
nothing in the shipped HTML may reach out to a CDN.

Inline symbol and file mentions in generated prose become wiki links through a
Python-Markdown **treeprocessor** (`doc_generator/cross_references.py`) rather
than a regex pass over the rendered HTML. A treeprocessor sees the element tree
after inline processing, so an inline `<code>` span is structurally
distinguishable from a fenced `<pre><code>` block — a regex over HTML is not, and
would eventually inject an anchor into a Mermaid diagram source. It also rewrites
only `DocPage.renderedHtml`, leaving `contentMarkdown` untouched, so the `.md`
artifacts on disk do not churn when the symbol manifest changes.

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

The chat panel (`ChatPanel.tsx`, 028) renders assistant answers as
structured content instead of plain text: **`react-markdown`** (Markdown to
React elements via component overrides, no `dangerouslySetInnerHTML`) with
**`remark-gfm`** (fenced/inline code parsing) and **`rehype-highlight`** +
**`lowlight`** for syntax highlighting, configured with a curated
**`highlight.js`** language subset (Python, JavaScript, TypeScript, Java,
Kotlin, Go, Rust — matching `repo_scanner/language.py`'s
`COMMON_LANGUAGE_MAP`) rather than the full ~190-language registry, to keep
the committed client bundle lean. A custom `code` renderer recognizes the
`path/to/file.ext :: Symbol.name` inline-reference format the chat's system
prompt already produces and resolves it through the same `findByCitation`
lookup the separate citation list uses — no new dependency for that part,
just a new render path over existing data.

## Testing

**pytest** for the entire Python backend (`tests/unit`, `tests/integration`,
`tests/contract` — the layout every spec in this project follows), **Vitest +
`@testing-library/react`** for the frontend components. **`pytest-asyncio`**
(026, test-only — not a runtime dependency) drives the async generators
`generateStream`/`askStream` introduced for chat streaming.

## Packaging

**setuptools**, `src/` layout (`package-dir = {"" = "src"}`), one editable install
for the whole backend. Keeps every package (`repo_scanner`, `parser_engine`,
`dependency_graph`, ... `repo_watcher`) importable as siblings without path hacks
(aside from `tests/conftest.py` inserting `src/` onto `sys.path` for test discovery).

**PyInstaller** (020, build-time only — never a runtime dependency of the
shipped binary) turns that same codebase into a standalone, single-file
executable per OS, so an end user needs no Python interpreter at all (see
`packaging/pyinstaller/codepedia.spec`, `packaging/build.py`). Chosen
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
only) runs `packaging/build.py` on a real Windows runner and publishes the
result as a GitHub Release. Added after this project's own development
machine turned out to be unable to complete a local PyInstaller build at
all (research.md §8's superseding decision) — `packaging/build.py` itself
is unchanged and still works standalone on any unrestricted machine; CI is
an additional path, not a replacement. The matrix originally built
macOS(x86_64)/Linux legs too; both were dropped after repeatedly failing
to fetch PyInstaller on those hosted runners — macOS/Linux binaries are
deferred to future work (docs/pfa.tex's "Perspectives d'Évolution")
instead of shipping as a permanently-red CI job.

## One loose end

- **`networkx`** is declared in `pyproject.toml` but **unused** anywhere in
  `src/` — the dependency graph hand-rolled its own adjacency structure instead.
  Not a functional problem, just dead weight in the dependency list; worth
  pruning if the manifest should reflect reality.

  (`pathspec` was in the same state until `repo_scanner/ignore.py` was rewritten
  on top of its `GitIgnoreSpec`. The hand-rolled matcher silently ignored
  negations — `!keep.log` never re-included anything — and only ever read the
  repository-root `.gitignore`, so per-directory ignore files did nothing.)

(`httpx` was transitive-only through 025; as of 026 it is a genuine direct
dependency — see "Local AI access" above.)
