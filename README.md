# Repo Scanner

A local tool that turns a source code repository into a browsable,
AI-summarized, searchable documentation wiki — and keeps that wiki current
automatically as the repository changes. Everything runs on your own
machine: no code, summary, embedding, or question ever leaves it. See
[`docs/architecture.md`](docs/architecture.md) for the full technical
picture and *why* it's built this way.

## What it does

- **Scans** a repository, applying `.gitignore`/exclusion rules and
  detecting each file's language.
- **Parses** every source file into an AST (Tree-sitter, or Python's own
  `ast`) and extracts its modules, classes, functions, imports, and call
  relations.
- **Builds a dependency graph** of the whole codebase — "what calls what,"
  "what imports what."
- **Generates a summary** for each module/function using a local LLM
  (Ollama-compatible), with the symbol's code, imports, and callers as
  context.
- **Embeds and indexes** code so it can be found by meaning, not just
  keyword.
- **Renders a browsable wiki**: a home page, one page per module, and
  clickable dependency diagrams.
- **Answers questions in chat**, grounded in the indexed code, with
  clickable citations back to the wiki.
- **Watches the repository** in the background and **incrementally
  re-indexes** just what a change actually affects — never a full
  repository re-analysis.

## Documentation

| Doc | Covers |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Global/technical architecture: layers, package responsibilities, data flow, storage, runtime model, enforced principles |
| [`docs/stack.md`](docs/stack.md) | Every technology used and why it was chosen |
| [`docs/diagrams/class-diagram.md`](docs/diagrams/class-diagram.md) | Project-wide class diagram |
| [`docs/diagrams/use-case-diagram.md`](docs/diagrams/use-case-diagram.md) | Project-wide use-case diagram |
| [`docs/diagrams/sequence-diagrams/`](docs/diagrams/sequence-diagrams/) | System overview + one sequence diagram per major function |
| [`specs/`](specs/) | Per-feature specs, plans, and tasks (this project is built spec-by-spec) |

> **These docs — this README included — are living documents.** Whenever a
> feature is implemented or its design changes, the relevant doc(s) get
> updated in the same piece of work, not as an afterthought.

## Prerequisites

- **Python 3.11+**
- A **local LLM and embedding service** for the AI features (summaries,
  chat) — anything exposing an Ollama-compatible API on `localhost` (e.g.
  [Ollama](https://ollama.com) itself). Scanning, parsing, and the
  dependency graph work without one; summarization, embedding, and chat
  require one running and will fail clearly (not silently fall back to a
  remote service) if it isn't reachable.
- **Node.js 18+ / npm** — only needed if you're working on the wiki UI
  (`frontend/`); the built UI bundle is already committed, so browsing a
  generated wiki doesn't need Node at all.

## Install

```bash
git clone <this repository>
cd "repo scanner"
pip install -e .          # runtime install
pip install -e ".[test]"  # add pytest, to also run the test suite
```

For frontend work only:

```bash
cd frontend
npm install
```

## Running it

Two pieces are wired up as runnable commands today:

**Scan a repository** (no local LLM needed) — prints a JSON inventory of
its source files:

```bash
repo-scanner scan /path/to/some/repository
# or: python -m repo_scanner scan /path/to/some/repository
```

**Serve an already-generated wiki + chat API**, bound to `127.0.0.1` by
default:

```bash
python -m chat_api.server \
  --repo /path/to/some/repository \
  --llm-model <your-local-model-name> \
  --docs-root /path/to/generated/wiki/output
```

**The rest of the pipeline — parsing, building the dependency graph,
persisting metadata, generating summaries, embedding, and rendering the
wiki — is exposed as tested library APIs, not yet wired into a single
top-level "index my repo" command.** Every piece is independently usable
from Python; see `tests/integration/test_reindex_pipeline.py`'s `Harness`
class for a complete, working example that wires all of them together
(scan → parse → graph → metadata → summarize → embed → generate docs)
against a sample repository, and `docs/diagrams/sequence-diagrams/01-full-indexing.md`
for the same flow as a diagram. Once you have a repository indexed and a
wiki generated that way, `repo_watcher.RepositoryWatcher` +
`reindex_pipeline.IncrementalReindexPipeline` (per
`docs/diagrams/sequence-diagrams/02-incremental-reindex.md`) keep it
current as files change.

## Running the tests

Backend (`pytest`, after `pip install -e ".[test]"`):

```bash
pytest
```

This runs everything under `tests/unit/`, `tests/integration/`, and
`tests/contract/` (the layout every feature in this project follows).
Some integration tests exercise real local-LLM/embedding calls end to end
and are skipped or will fail without one running — most of the suite,
including everything under `tests/unit/` and `tests/contract/`, does not
need one.

> Three pre-existing tests under `tests/contract/test_parser_interface.py`
> and `tests/integration/test_multi_language_batch.py` /
> `test_parse_failures.py` currently fail on a fresh checkout, due to a
> Tree-sitter grammar version mismatch (AST node naming) unrelated to any
> single feature. Everything else should pass.

Frontend (`vitest`):

```bash
cd frontend
npm test        # run the component test suite
npm run build   # produce the committed wiki-ui bundle
```

## Project layout

```text
src/            One Python package per feature (repo_scanner, parser_engine,
                 dependency_graph, repository_metadata, embedding_engine,
                 local_llm, chat, doc_generator, chat_api, repo_watcher,
                 reindex_pipeline, vector_index) - see docs/architecture.md
                 for what each one owns.
frontend/       The wiki UI (React + TypeScript + Vite), built into
                 src/doc_generator/assets/.
tests/          unit/, integration/, contract/ - one set per package.
specs/          Per-feature spec/plan/tasks, numbered in build order.
docs/           architecture.md, stack.md, diagrams/ - kept in sync with
                 every implementation.
.specify/       The spec-driven workflow's own config/templates/memory.
```
