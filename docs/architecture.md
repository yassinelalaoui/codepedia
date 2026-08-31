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
| `local_llm` | Generate text from a prompt via a local (Ollama-compatible) endpoint, streamed as it's produced (`generateStream`, 026; `generate` is a convenience wrapper that drains it); verify availability before every call (`isAvailableLocally`/`isAvailable`). `GroqLLMEngine` implements the same `LLMEngine` interface as a remote provider. |
| `embedding_engine` | Turn text into a vector via the same local-endpoint convention (`EmbeddingEngine`), or via `OpenAIEmbeddingProvider` (029) - both satisfy the `EmbeddingProvider` protocol. |
| `provider_routing` (029) | Sits alongside `local_llm`/`embedding_engine`, depending on both: `ProviderRef`/`ProviderChain` (an ordered, per-stage list of `"<kind>:<model>"` entries), `FailoverExecutor` (tries each configured provider in order, failing over only on a classified network/rate-limit/auth error - never on preference, never outside the configured chain - constitution 2.3), and `failover_log`/`engine_failover_log` (one row per actual switch). This is the deferred implementation of constitution v3.0.0's 2.1/2.3 amendment: every stage now defaults to a named remote provider with automatic, chain-scoped failover, replacing the earlier "local by default, one explicit opt-in remote engine, never a fallback chain" model. |

### 3. Knowledge Derivation

Uses the Analysis layer's facts plus the AI Services layer to produce higher-level,
generated knowledge about the codebase.

| Package | Responsibility |
|---|---|
| `repository_metadata.summary_pipeline` (`CodeSummaryPipeline`) | Generate a natural-language summary per module/public function, using source + imports + direct callers as context; regenerate only impacted summaries on a change. Its `llmEngine` is a `provider_routing.FailoverExecutor` over the configured summary chain (029), not a single engine. |
| `vector_index` | Store and search embedded code chunks, fusing vector similarity with an FTS5 lexical index (BM25) by Reciprocal Rank Fusion so an exact identifier is not buried by merely-similar text; fusion sets the order while `score` stays the raw cosine the chat banners compare against absolute thresholds. Holds a long-lived connection opened with `check_same_thread=False` behind a reentrant lock, since `serve` writes from the watcher thread and searches from the server thread. Each stored chunk carries `embeddingModelId` (029, the `ProviderRef` that computed it); a search excludes vectors from any other model *before* the dimensionality check, so a repository indexed with more than one embedding provider never blends incompatible vectors (and never crashes on the mismatch either). A query embeds through whichever provider's model dominates the index (falling back to the normal failover chain when the index is empty/mixed or that provider errors), rather than whatever the chain would naturally answer with first — keeping a query consistent with what's actually stored despite `FailoverExecutor` not being sticky across calls; if the resulting auto-applied `embeddingModelId` filter still yields zero matches, the search retries once with that filter relaxed rather than surfacing an empty result the index could actually answer. |
| `chat` | Answer a natural-language question by retrieving relevant chunks - reranked by proximity in the dependency graph to symbols the conversation already cited, and trimmed to an explicit token budget (oldest history first, then the README, then evidence bodies - evidence is truncated, never dropped, so every persisted citation stays honest) - - enriched with recent conversation context for follow-up questions (026, local text/citation concatenation only, no LLM call) - and streaming the configured engine's answer (`askStream`, 026) *grounded in* that evidence, with citations attached once generation completes. `askStream` routes generation through a `provider_routing.FailoverExecutor` over the configured chat chain (029) and records which provider actually answered (`ChatMessage.generatedBy`). The repository's README (if one exists) is always attached as unconditional baseline context, unlike retrieved evidence - never subject to retrieval scoring - so a broad, project-level question can still be answered (and cited) even when nothing in the vector index scores as relevant for it. |

### 4. Presentation

Turns the analyzed/derived knowledge into something a human reads or interacts with.

| Package | Responsibility |
|---|---|
| `doc_generator` | Render the wiki: a home page, one page per module, dependency-diagram pages, a single repository-wide class diagram (its structurally major classes, capped for legibility), one bounded call-sequence diagram per identified entry point (CLI command, API route handler, or uncalled public function/method), a single repository-wide use-case diagram (one shared actor per entry-point exposure kind, linked to its use cases), and a single always-reachable Diagrams page aggregating links to every diagram above; every generated page shares a persistent sidebar listing every module, built from `_nav_modules` and rendered through a markdown-escaping filter so module/link names with special characters can't corrupt the page; every page also carries an "On this page" rail of its own H2/H3 sections, derived from Python-Markdown's `toc_tokens` at render time and never persisted; symbol and file mentions inside generated prose are resolved against the same manifest `search_index.py` produces and rewritten as links by a Python-Markdown treeprocessor (`cross_references.py`), which touches only the rendered HTML so the Markdown artifacts never churn; regenerate only the pages a change actually affects. |
| `chat_api` | The one local process (FastAPI) that serves the generated wiki as static files and exposes the chat session endpoints the browser UI calls: creating a session, streaming an answer, listing every existing session, and reading a chosen session's full history. `AskQuestionResponse`/`ChatMessageView` carry `generatedBy`; `GET /providers/failover-log` (029) reads `engine_failover_log`, optionally filtered by stage. |
| `frontend/` (`wiki-ui`) | The React UI running in the browser: symbol search, dependency-diagram click-through, chat panel. The chat panel (028) shows a visible activity indicator from submission until the first streamed fragment arrives, renders answers as structured Markdown with syntax-highlighted code and clickable in-text symbol/file references (resolved the same way as the separate citation list), and carries the current session id as a URL query parameter so a reload, a copied link, or a different browser/device all restore the same conversation via the existing history route. |

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
| `cli` | The `codepedia` command (`index`/`serve`/`config`/`scan`/`provider`) that sequences layers 1–5 into a single-command workflow: `index` runs the full pipeline and starts serving it; `serve` resumes an already-indexed repository with the watcher (5) active; `config` sets connection settings (endpoint/timeout) for any `local:` chain entry; `provider chain set <stage> <provider:model>...`/`provider mode full-local` (029) change which providers a stage's chain actually uses. A Typer-callback-enforced disclosure gate (`cli.disclosure`) blocks `index`/`serve`/`provider` until the operator explicitly acknowledges the three chains' current providers, re-triggered whenever that combination actually changes. |

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

### Where the pipeline fans out

The full-indexing flow is linear in its *stages* but not inside two of them.
`CodeSummaryPipeline` dispatches its symbols, and the CLI's embedding stage
dispatches its files, to a `ThreadPoolExecutor` — both stages are one blocking
remote call per unit of work, so overlapping them is the difference between a
pass measured in tens of minutes and one measured in minutes. Stage *order* is
unchanged: each pool is fully drained before the next stage begins, so nothing
downstream ever observes a half-finished stage.

Three invariants are what let those pools exist without changing any
component's contract, and they are worth keeping true:

- **`vector_index` serializes its own writes.** One reentrant lock guards
  every public mutation and its connection is opened with
  `check_same_thread=False`. It was already so for the watcher's timer thread.
- **`repository_metadata`, `doc_generator` and `dependency_graph` connect per
  call** and hold nothing open between them, so concurrent callers contend
  only inside SQLite — which is why `repository_metadata`'s connections raise
  the busy timeout rather than share a connection.
- **`FailoverExecutor` results are read from the returned value**, never from
  its mutable `providerUsed`/`attempts` attributes, everywhere inside an
  indexing loop. Those attributes race under concurrency; the returned
  `FailoverResult` does not. `chat/session.py` is the one place that reads the
  attribute, and it runs nowhere near these loops.

A rate limit met by those pools is waited out on the same provider before the
chain advances (`provider_routing.BackoffPolicy`). Constitution 2.3's
requirement is unaffected: `engine_failover_log` still records exactly one row
per real provider switch, and a wait — which is the opposite of a switch —
stays out of that table and is surfaced on the console instead.

## Storage architecture

**One SQLite file per owning component**, not one shared database:

- `repository_metadata` — files, symbols, dependency edges, content hashes,
  (025) chat sessions/messages, and (029) `engine_failover_log`:
  `chat_sessions`/`chat_messages`/`engine_failover_log` join this same file
  rather than getting their own — a deliberate exception (see the "own
  store" note below). `chat_messages` gained a `generated_by` column (029);
  `engine_failover_log` is cross-cutting (populated by all three
  AI-consuming stages, not owned by any one later layer), so its own
  row↔object mapping lives in `provider_routing.failover_log`, following
  the same "schema stays in `repository_metadata.sqlite_store`, mapping
  code lives in the later layer that actually populates it" split
  `chat.sqlite_store` already established for `chat_sessions`/`chat_messages`.
- `dependency_graph` — the persisted graph snapshot (nodes/edges).
- `vector_index` — embedded chunks + their vectors, each chunk's row also
  carrying `embedding_model_id` (029) — which provider/model produced it.
  That column is what makes a vector reusable: `index` reads the *previous*
  run's vector store before re-embedding and reuses any vector whose content
  and model both still match (032), so an unchanged file costs no API calls
  on a re-index. It is read and closed immediately, never written — the
  directory holding it is about to be replaced.
- `doc_generator` — the page manifest (what was generated, its content hash, its
  links) used to compute incremental regeneration impact.

Each store is only ever written by its owning package. This trades a small amount of
duplicated connection/schema boilerplate for simple ownership: no component needs to
understand another component's schema, and no migration ever has to touch more than
one file. All are plain files on local disk — no database server, per constitution
2.6.

## Runtime & deployment model

Everything runs as **local processes on the developer's own machine**:

- `codepedia index` (`cli`, layer 6) runs the full pipeline once as a
  short-lived phase, then becomes the same long-running server process
  described below for `chat_api`.
- `codepedia serve` (`cli`) is the process that keeps the watcher +
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
  on a GitHub-hosted Windows runner, triggered by a maintainer pushing a
  version tag, since PyInstaller does not cross-compile and a single
  maintainer machine can't build all OS targets. The workflow only
  publishes on a tag push — nothing runs on ordinary commits (research.md
  §8's superseding decision). The matrix originally also built macOS and
  Linux legs; those were dropped after repeated CI failures fetching
  PyInstaller on those runners and are tracked as future work rather than
  a permanently-red job — see docs/pfa.tex's "Perspectives d'Évolution".

There is no cloud environment this system runs in. That is not a limitation to work
around — it is the product's core guarantee (constitution 2.1): code never leaves the
machine.

## Key architectural principles

These are enforced, not just documented — see `.specify/memory/constitution.md` for
the authoritative source:

1. **Local network exposure stays `localhost`/`127.0.0.1`-only.** The web
   server/`chat_api` never binds anywhere else by default (constitution 2.2);
   `local_llm`/`embedding_engine`'s own local endpoints validate this at the
   URL-parsing level (`normalize_endpoint_url`). This does **not** mean every
   *AI provider* call stays local — a fresh install's default chains lead with
   the local Ollama runtime but keep a named remote provider (Groq, OpenAI)
   behind it as a fallback, so a call can still leave the machine when the
   local entry is unreachable or its model isn't pulled. That fallback is
   disclosed once, blockingly, before first use; `provider mode full-local`
   removes it, which is the only configuration that guarantees no remote call.
2. **No silent, undisclosed, or out-of-chain failover.** A stage automatically
   fails over only within its own explicitly configured provider chain, only on
   a classified network/rate-limit/auth failure — never on preference, never to
   a provider absent from that chain, and every actual switch is both logged
   (`engine_failover_log`) and visible (`generatedBy`, `GET
   /providers/failover-log`). If every provider in the chain is unavailable,
   the caller fails loudly with a specific error (`FailoverExhaustedError`)
   telling the user how to fix it — never a silent, unexplained failure.
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
  `RepositoryMetadataStore.delete_source_file` rather than inventing a new store),
  or a later layer's own state is small enough that a second local db file would
  add more operational surface than it isolates (e.g. 025's `chat_sessions`/
  `chat_messages` joining `repository_metadata`'s file — the schema still stays
  owned by one module, `repository_metadata.sqlite_store`, per the layering rule
  above; only the row↔object mapping lives in the later layer, `chat`).
- Updates this file, `docs/stack.md`, and `docs/diagrams/` in the same piece of work.

## Current status by layer

- **Ingestion & Analysis, Local AI Services, Knowledge Derivation, Presentation,
  Automation**: implemented (specs 001–018, provider chains/failover added by
  029).
- **Entry Point**: implemented (spec 019) — `codepedia` is the project's
  `[project.scripts]` console command; its `provider` subcommands and
  disclosure gate were added by 029.
