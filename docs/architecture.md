# Architecture

The global and technical architecture of this project: how it's structured, how data
flows through it, and the principles that constrain every design decision made in it.
See also [`docs/stack.md`](stack.md) (what it's built with, and why) and
[`docs/diagrams/`](diagrams/) (visual class/use-case/sequence diagrams).

> Maintenance: update this document whenever a package is added/removed/renamed, a
> layer's responsibility changes, a new storage file is introduced, or an
> architectural principle is added or revised. Same standing rule as the root
> [`README.md`](../README.md), `docs/stack.md`, and every file under `docs/diagrams/`.

## What this is

A local tool that turns a source code repository into a browsable, AI-summarized,
searchable documentation wiki — and keeps that wiki current automatically as the
repository changes, without ever sending code off the machine it runs on.

## Architectural style

**A local-first, modular pipeline** — not a distributed system, not a client/server
product with a remote backend. Every "service" (local LLM, embedding engine, web
server) runs on `127.0.0.1` on the developer's own machine. The system is organized as
a **linear analysis pipeline** (scan → parse → build graph → persist → summarize →
embed → generate docs → serve) with a **second, parallel automation loop** (watch →
confirm → targeted re-run of the same pipeline stages) layered on top of it once the
repository has been indexed once. There is no orchestration framework, no message
broker, no microservice boundary between these stages — they are Python packages
calling each other's public functions/classes directly, in-process.

This shape is a direct consequence of the project's constitution
(`.specify/memory/constitution.md`): no external database server, no message broker,
no cloud dependency, and — critically — **incremental re-analysis is a first-class
architectural requirement, not an optimization bolted on later** (constitution 2.5).
That is why the pipeline stages are designed, from the start, to each accept "just
this file" or "just these symbols" as an alternative to "the whole repository."

## System layers

Every package under `src/` belongs to one of six layers. Packages within a layer
don't depend on each other; dependencies only flow downward (a later layer depends on
earlier ones, never the reverse) — see `docs/diagrams/class-diagram.md` for the
cross-package relationships this produces.

### 1. Ingestion & Analysis

Turns raw source files into structured, queryable facts about the codebase.

| Package | Responsibility |
|---|---|
| `repo_scanner` | Walk a repository, apply exclusion rules, detect binary files and languages, produce the candidate file list. |
| `parser_engine` | Parse one file into an AST (Tree-sitter, or Python's own `ast`) and extract its symbols (modules, classes, functions), imports, calls, and inheritance relations. |
| `dependency_graph` | Hold the graph of every file/symbol and the `import`/`call`/`inheritance` edges between them; answer "what depends on X" / "what does X depend on." |
| `repository_metadata` | The durable record of every scanned file, its symbols, and its content hash — the system's source of truth for "is this file actually indexed, and has it changed." |

### 2. Local AI Services

Stateless local model access, used by the layers above and below but owning no
domain data itself.

| Package | Responsibility |
|---|---|
| `local_llm` | Generate text from a prompt via a local (Ollama-compatible) endpoint; verify availability before every call; never fall back to a remote model. |
| `embedding_engine` | Turn text into a vector via the same local-endpoint convention. |

### 3. Knowledge Derivation

Uses the Analysis layer's facts plus the AI Services layer to produce higher-level,
generated knowledge about the codebase.

| Package | Responsibility |
|---|---|
| `repository_metadata.summary_pipeline` (`CodeSummaryPipeline`) | Generate a natural-language summary per module/public function, using source + imports + direct callers as context; regenerate only impacted summaries on a change. |
| `vector_index` | Store and search embedded code chunks by similarity. |
| `chat` | Answer a natural-language question by retrieving relevant chunks and asking the local LLM to answer *grounded in* that evidence, with citations. |

### 4. Presentation

Turns the analyzed/derived knowledge into something a human reads or interacts with.

| Package | Responsibility |
|---|---|
| `doc_generator` | Render the wiki: a home page, one page per module, dependency-diagram pages, a single repository-wide class diagram (its structurally major classes, capped for legibility), one bounded call-sequence diagram per identified entry point (CLI command, API route handler, or uncalled public function/method), and a single repository-wide use-case diagram (one shared actor per entry-point exposure kind, linked to its use cases); regenerate only the pages a change actually affects. |
| `chat_api` | The one local process (FastAPI) that serves the generated wiki as static files and exposes the chat session endpoints the browser UI calls. |
| `frontend/` (`wiki-ui`) | The React UI running in the browser: symbol search, dependency-diagram click-through, chat panel. |

### 5. Automation

Keeps the layers above current without a human re-running anything.

| Package | Responsibility |
|---|---|
| `repo_watcher` | Watch the repository in the background, debounce bursts of changes, hand off a stabilized batch of impacted files. |
| `reindex_pipeline` | Consume that batch and re-run just the affected slice of layers 1–4: re-parse, update the graph/metadata, regenerate impacted summaries/embeddings/pages. |

### 6. Entry Point

The outermost layer: the one thing a developer actually runs. Depends on
every layer above; nothing depends on it.

| Package | Responsibility |
|---|---|
| `cli` | The `repo-scanner` command (`index`/`serve`/`config`/`scan`) that sequences layers 1–5 into a single-command workflow: `index` runs the full pipeline and starts serving it; `serve` resumes an already-indexed repository with the watcher (5) active; `config` chooses the local LLM/embedding model (2) `index`/`serve` use. |

## Data flow

Two flows, sharing the same underlying stages:

- **Full indexing** (once, or on demand): `repo_scanner` → `parser_engine` →
  `dependency_graph` + `repository_metadata` → `CodeSummaryPipeline` (+ `local_llm`)
  → `vector_index` (+ `embedding_engine`) → `doc_generator`. See
  `docs/diagrams/sequence-diagrams/01-full-indexing.md`.
- **Incremental update** (continuous, once indexed): `repo_watcher` →
  `reindex_pipeline` → the *same* stages as above, called in their per-file/per-symbol
  "targeted" mode instead of full-repository mode, gated by a content-hash check
  against `repository_metadata` so a false "modified" signal costs nothing. See
  `docs/diagrams/sequence-diagrams/02-incremental-reindex.md`.

Both flows converge on the same stored state (`repository_metadata`,
`dependency_graph`, `vector_index`, `doc_generator`'s output), which is what makes
"the incremental result is identical to a full re-index" (018's own success
criterion) a meaningful, checkable property rather than two diverging code paths.

One subtlety worth knowing: `dependency_graph`'s symbol node ids are
content-hash-derived, so an incremental update replaces a changed symbol's node
outright rather than mutating it in place. That would silently drop the edge from an
*unrelated, unchanged* caller elsewhere in the repository (it isn't being
re-ingested this batch, so nothing re-creates the edge) — `reindex_pipeline` works
around this by capturing such external edges before the swap and re-linking them by
name afterward, so `dependents()`-based impact analysis (the mechanism the whole
"regenerate only direct dependents" guarantee rests on) keeps working after repeated
incremental updates, not just after a fresh full index.

Two more flows read that converged state without changing it: **browsing/searching
the wiki** and **asking the chat a question** — see
`docs/diagrams/sequence-diagrams/03-chat-rag.md` and `04-wiki-browsing.md`.

## Storage architecture

**One SQLite file per owning component**, not one shared database:

- `repository_metadata` — files, symbols, dependency edges, content hashes.
- `dependency_graph` — the persisted graph snapshot (nodes/edges).
- `vector_index` — embedded chunks + their vectors.
- `doc_generator` — the page manifest (what was generated, its content hash, its
  links) used to compute incremental regeneration impact.

Each store is only ever written by its owning package. This trades a small amount of
duplicated connection/schema boilerplate for simple ownership: no component needs to
understand another component's schema, and no migration ever has to touch more than
one file. All are plain files on local disk — no database server, per constitution
2.6.

## Runtime & deployment model

Everything runs as **local processes on the developer's own machine**:

- `repo-scanner index` (`cli`, layer 6) runs the full pipeline once as a
  short-lived phase, then becomes the same long-running server process
  described below for `chat_api`.
- `repo-scanner serve` (`cli`) is the process that keeps the watcher +
  reindex pipeline running continuously: it loads an already-indexed
  repository's state, starts `repo_watcher` (5) in-process, and hosts the
  same web server `index` does — the concrete case the watcher's own
  contract (017) anticipated ("invoked by a CLI").
- `chat_api` is the one long-running server process, bound to `127.0.0.1` by default
  (constitution 2.2) — no reverse proxy, no container orchestration, no remote
  deployment target. "Deploying" this project means running it on a laptop.
- The local LLM and embedding services (Ollama or compatible) are expected to already
  be running locally; this project never installs or manages them.
- **Getting `cli` onto that laptop** (020, `packaging/`): a standalone,
  single-file binary built with PyInstaller — no separately installed
  Python interpreter needed on the target machine — installed with one
  platform-specific command (`packaging/install.sh` /
  `packaging/install.ps1`) that downloads it from a GitHub Release of this
  repository. An editable `pip install -e .` (019) remains the path for
  contributors working on the source itself; it is not how an end user is
  expected to obtain the tool.
- **Producing that binary** (020, `.github/workflows/release.yml`): built
  on GitHub-hosted Windows/macOS/Linux runners, triggered by a maintainer
  pushing a version tag, since PyInstaller does not cross-compile and a
  single maintainer machine can't build all three OS targets. The
  workflow only publishes on a tag push — nothing runs on ordinary
  commits (research.md §8's superseding decision).

There is no cloud environment this system runs in. That is not a limitation to work
around — it is the product's core guarantee (constitution 2.1): code never leaves the
machine.

## Key architectural principles

These are enforced, not just documented — see `.specify/memory/constitution.md` for
the authoritative source:

1. **Local-only, always.** Every network call this project makes targets
   `localhost`/`127.0.0.1`; the local-AI packages validate this at the URL-parsing
   level (`normalize_endpoint_url`), not just by convention.
2. **No silent cloud fallback.** If the local LLM or embedding service is
   unavailable, every caller fails loudly with a specific error telling the user how
   to fix it — never a quiet degrade to a remote API.
3. **Incremental by design, not by afterthought.** Every stage in the Analysis and
   Knowledge Derivation layers was built with a "just this one file/symbol" mode from
   the start (`store_inventory` per file, `summarizeRepository(changed_paths=...)`,
   `reindexFile(path, chunks)`, `generateRepositoryDocumentation(changedPaths=...)`),
   which is what makes 017/018's watcher+pipeline possible without rewriting the
   layers underneath them.
4. **The analyzed repository is read-only.** Nothing in this system ever writes into
   the repository it's documenting; all output goes to a separate generated-docs
   location and to this project's own local storage.
5. **Traceability.** Every AI-generated summary and every chat answer is attributable
   back to the specific symbols/files that justify it (citations, not bare claims).
6. **Minimal infrastructure.** No database server, no broker, no container
   orchestration — SQLite files and local processes only.

## How a new feature typically fits in

This project is built spec-by-spec (`specs/0NN-feature-name/`, via the `speckit-*`
skills) and, so far, one new top-level package per feature under `src/`, following
the layer table above. A new feature usually:

- Gets its own package under `src/`, added as a dependency of whichever layer it
  belongs to, following the existing packages' pattern rather than reaching into
  another package's internals.
- Gets its own `tests/unit/`, `tests/integration/`, and (if it exposes a
  reusable interface) `tests/contract/` test files, matching the layout every
  existing package already uses.
- If it changes storage, gets its own SQLite file rather than joining another
  component's schema (see "Storage architecture" above) — unless it is extending an
  existing component's own responsibility (e.g. 018 adding
  `RepositoryMetadataStore.delete_source_file` rather than inventing a new store).
- Updates this file, `docs/stack.md`, and `docs/diagrams/` in the same piece of work.

## Current status by layer

- **Ingestion & Analysis, Local AI Services, Knowledge Derivation, Presentation,
  Automation**: implemented (specs 001–018).
- **Entry Point**: implemented (spec 019) — `repo-scanner` is the project's
  `[project.scripts]` console command.
