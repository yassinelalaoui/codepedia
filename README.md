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
- **Renders a browsable wiki**: a home page, one page per module, clickable
  dependency diagrams, a repository-wide class diagram of its structurally
  major classes, one bounded call-sequence diagram per identified entry
  point (CLI command, API route handler, or uncalled public function/method),
  a repository-wide use-case diagram (one shared actor per entry-point
  exposure kind, linked to its use cases), and a single "Diagrams" page
  reachable in one click from anywhere in the wiki that lists every diagram
  above.
- **Answers questions in chat**, grounded in the indexed code, with
  clickable citations back to the wiki. Conversations persist locally, so
  they survive a server restart or a wiki page reload.
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

- **A supported OS/architecture for the standalone binary**: Windows,
  macOS, or Linux, x86_64. This is the *only* thing the installer below
  needs already present on the machine — no Python, no cloned repository,
  no manually built development environment (specs/020-cli-packaging).
- A **local LLM and embedding engine** for the AI-backed features
  (summaries, chat) — anything exposing an Ollama-compatible API on
  `localhost` (e.g. [Ollama](https://ollama.com) itself). This is a
  **separate, external prerequisite the installer below does not and
  cannot include** — a local LLM runtime is a large, independently
  updated piece of software, not something a small CLI package should
  vendor. Install and start it yourself; `repo-scanner index`/`serve`
  detect and report clearly if it isn't reachable, rather than silently
  falling back to a remote service.
  - **Needs it**: `repo-scanner index`, and the AI-backed parts of
    `repo-scanner serve` (summarization, embedding, chat).
  - **Doesn't need it**: `repo-scanner scan`, `repo-scanner config`
    (configuring or viewing your model choice works even before the
    engine is installed).
- **Node.js 18+ / npm** — only needed if you're working on the wiki UI
  (`frontend/`); the built UI bundle is already committed, so browsing a
  generated wiki doesn't need Node at all.

## Install

Install `repo-scanner` as a standalone binary with one command — no
Python, no `git clone`, no manually created virtual environment:

```bash
curl -fsSL https://github.com/yassinelalaoui/repo-scanner/releases/latest/download/install.sh | sh
```

```powershell
irm https://github.com/yassinelalaoui/repo-scanner/releases/latest/download/install.ps1 | iex
```

Then verify it worked:

```bash
repo-scanner --version
```

Running the same command again upgrades an existing install to the latest
release in place. To uninstall, delete the single installed file:

```bash
rm ~/.local/bin/repo-scanner                                     # macOS/Linux
Remove-Item "$env:LOCALAPPDATA\repo-scanner\repo-scanner.exe"    # Windows
```

Per-repository state and configuration `repo-scanner` writes (see
`~/.repo-scanner/` below) is untouched by either command.

See `specs/020-cli-packaging/contracts/packaging-interface.md` for the
full install/uninstall contract and [`packaging/README.md`](packaging/README.md)
for how releases are built and published.

### Installing from source (for contributors)

Working on `repo-scanner` itself, rather than just using it, still uses an
editable Python install:

```bash
git clone <this repository>
cd "repo scanner"
pip install -e .          # runtime install
pip install -e ".[test]"  # add pytest, to also run the test suite
pip install -e ".[build]" # add PyInstaller, to build the standalone binary (packaging/build.py)
```

For frontend work only:

```bash
cd frontend
npm install
```

## Running it

`repo-scanner` is the single command-line entry point, with four subcommands:

**Index a repository** — the one-command path from a fresh repository to a
browsable wiki. Scans, parses, extracts symbols, builds the dependency
graph, generates summaries and embeddings, renders the wiki, then starts
serving it and prints the local URL:

```bash
repo-scanner index /path/to/some/repository
```

This requires a local LLM and embedding service (e.g. [Ollama](https://ollama.com))
to be running; `index` checks their availability up front and fails with a
clear, actionable message (naming what's missing and how to fix it) before
doing any work if either isn't reachable — never a silent fallback to a
remote service. Which model each of them uses comes from `config` below
(sensible defaults apply if you haven't run it).

**Resume an indexed repository with live updates**: serves the wiki + chat
API from the previous `index` run and activates the repository watcher, so
saved edits are reflected automatically without re-running `index`:

```bash
repo-scanner serve /path/to/some/repository
```

**Choose the local LLM/embedding model** `index`/`serve` use:

```bash
repo-scanner config --llm-model <your-local-model-name> --embedding-model <your-embedding-model-name>
repo-scanner config --show   # view the current configuration
```

**Scan a repository only** (no local LLM needed) — prints a JSON inventory
of its source files, unchanged from the original scanner (001):

```bash
repo-scanner scan /path/to/some/repository
# or: python -m repo_scanner scan /path/to/some/repository
```

Both `index` and `serve` bind to `127.0.0.1` by default (`--host`/`--port`
to override). See `specs/019-cli-orchestrator/contracts/cli-interface.md`
for the full command contract, `docs/diagrams/sequence-diagrams/01-full-indexing.md`
for `index`'s flow as a diagram, and
`docs/diagrams/sequence-diagrams/02-incremental-reindex.md` for what `serve`
keeps running in the background.

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
                 reindex_pipeline, vector_index, cli) - see docs/architecture.md
                 for what each one owns. cli/ is the repo-scanner console
                 entry point ([project.scripts] in pyproject.toml).
frontend/       The wiki UI (React + TypeScript + Vite), built into
                 src/doc_generator/assets/.
packaging/      Standalone-binary packaging: the PyInstaller build spec,
                 the maintainer build helper, and the install.sh/
                 install.ps1 one-line installers - see packaging/README.md.
tests/          unit/, integration/, contract/ - one set per package.
specs/          Per-feature spec/plan/tasks, numbered in build order.
docs/           architecture.md, stack.md, diagrams/ - kept in sync with
                 every implementation.
.specify/       The spec-driven workflow's own config/templates/memory.
```
