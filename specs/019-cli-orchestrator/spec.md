# Feature Specification: Command-Line Interface Orchestrator

**Feature Branch**: `019-cli-orchestrator`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "Construire l'interface en ligne de commande qui orchestre l'ensemble du pipeline. La CLI doit proposer au minimum trois commandes : une commande d'indexation initiale d'un dépôt (lance le scan, le parsing, l'extraction, la génération de résumés et du wiki, puis affiche l'URL locale où consulter le résultat), une commande de démarrage du serveur web local avec activation du watcher pour la ré-indexation incrémentale, et une commande de configuration permettant de choisir le modèle LLM local et le modèle d'embedding à utiliser. La CLI doit vérifier explicitement la disponibilité du modèle local avant de lancer toute étape nécessitant l'IA, et afficher des messages clairs en cas de dépendance manquante (modèle non installé, dépôt introuvable). Critère de succès : un développeur sans connaissance préalable de l'outil peut, en exécutant une seule commande depuis un dépôt de code, obtenir un wiki de documentation consultable localement, avec des messages d'erreur exploitables si une dépendance (Ollama, modèle) manque."

## Overview

Build the command-line interface that ties together every pipeline stage
already defined by this project (repository scanning 001, multi-language
parsing 002, symbol extraction 003, dependency graph construction 004,
metadata persistence 005, local vector indexing 006/007, local LLM access
008, local embedding engine 009, code summary generation 010, code RAG
answering 011, wiki generation 012, interactive dependency diagrams 013,
the chat API 014, the local web server 015, the wiki web interface 016, the
repository change watcher 017, and the incremental reindexing pipeline 018)
into a small set of commands a developer runs from a terminal. The CLI is
the single entry point: it is how a developer who has never used the tool
before turns a local code repository into a browsable, locally hosted
documentation wiki, and how they keep that wiki current while they keep
working.

## Goals

- Provide one command that takes a developer from "nothing indexed yet" to
  a browsable local documentation wiki for a repository, printing the URL
  to open it.
- Provide one command that (re)starts the local web server with the
  repository watcher active, so the wiki and chat stay current as files
  change, without repeating the full initial indexing run.
- Provide one command that lets a developer choose which local LLM model
  and which local embedding model the tool uses for every AI-dependent
  step.
- Explicitly verify that the local LLM and embedding model are installed
  and reachable before starting any step that depends on them, every time,
  rather than discovering the failure partway through.
- Give a developer with no prior knowledge of the tool clear, actionable
  error messages whenever a required dependency (the target repository,
  the local LLM, the embedding model) is missing, so they know exactly
  what to fix.

## Non-Goals

- Implementing the underlying pipeline stages themselves (scanning,
  parsing, extraction, dependency graph, persistence, vector indexing,
  local LLM access, embedding generation, summarization, RAG answering,
  wiki generation, diagrams, chat API, web server, wiki interface,
  watcher, incremental reindexing); this feature only sequences and
  exposes the existing stages (001-018) through commands.
- Installing, updating, or managing Ollama or any local LLM runtime; the
  CLI only detects and reports whether it is available and configured
  correctly.
- A graphical installer, desktop application, or IDE plugin; this is a
  terminal-based command-line interface only.
- Indexing or serving more than one repository at a time from a single
  running instance of the tool.
- Any remote or cloud deployment of the CLI or the server it starts; all
  commands operate against the local machine only.

## User Stories

### US1 - One command from a fresh repository to a browsable wiki

As a developer trying this tool for the first time, I want to run a
single command against my local repository and end up with a
documentation wiki I can open in my browser, so that I get value
immediately without first having to learn how the tool's internals fit
together.

Acceptance criteria:

- Running the indexing command against a valid local repository path, with
  a working local LLM and embedding model already available, performs
  scanning, parsing, symbol extraction, and dependency graph construction,
  followed by summary generation and embedding generation, and produces a
  documentation wiki that reflects the completed summaries — all without
  manual intervention.
- Once generation completes, the tool prints a local URL, and opening it
  in a browser shows the generated documentation wiki for that repository.
- Running the command without an explicit path defaults to indexing the
  current directory, provided it is a valid repository.
- Progress toward completion (which stage is currently running) is visible
  in the terminal output while the command runs, so a developer indexing a
  large repository can tell the tool is still working.

### US2 - Resuming work with live updates

As a developer returning to a repository I already indexed, I want to
start the local server with change-watching enabled, so that my
documentation wiki and chat stay current as I keep editing files, without
re-running the full indexing process.

Acceptance criteria:

- Running the server-start command against a repository that was
  previously indexed starts the local web server and activates the
  repository watcher, then prints the local URL to browse the wiki.
- While the server runs, editing a source file in the repository results
  in the watcher detecting the change and the incremental reindexing
  pipeline updating the affected documentation, without any further
  command from the developer.
- Running the server-start command against a repository that has never
  been indexed fails with a message directing the developer to run the
  indexing command first, rather than starting a server with no content.

### US3 - Choosing local models

As a developer with specific local LLM and embedding models installed, I
want to configure which ones the tool uses, so that indexing and chat rely
on the model I intend rather than an unconfigured default.

Acceptance criteria:

- Running the configuration command lets the developer choose which local
  LLM model is used for summary generation and chat, and the choice is
  saved for future commands.
- Running the configuration command lets the developer choose which local
  embedding model is used for embedding generation, and the choice is
  saved for future commands.
- The configuration command shows, for each candidate model, whether it is
  currently installed and reachable locally, so the developer can make an
  informed choice.
- Selecting a model that is not currently installed is still allowed (so a
  developer can prepare their configuration ahead of installing it), but
  the tool warns clearly that the model must be installed before it can
  actually be used.
- A subsequent indexing or server-start command uses the configured models
  without the developer having to specify them again.

### US4 - Actionable errors when a dependency is missing

As a developer who has not installed or started the local LLM service, I
want the tool to tell me clearly what is missing and how to fix it when I
try to index a repository, so that I am not left guessing why nothing
happened.

Acceptance criteria:

- Running the indexing command while the local LLM service is not running
  stops before any AI-dependent work starts and displays a message
  identifying that the local LLM service is unreachable, along with what
  to do about it.
- Running the indexing command while the configured model is not installed
  locally stops and displays a message identifying the specific missing
  model and how to install it.
- Running the indexing command against a path that does not exist or is
  not a valid repository stops immediately with a message identifying the
  invalid path, before any scanning, parsing, or AI-dependent work is
  attempted.
- None of these failure cases leave partial or corrupted index/wiki output
  behind, and none of them hang indefinitely or fail silently.

### Edge Cases

- What happens when the indexing command is run again against a repository
  that was already indexed? The tool performs a fresh full run and
  replaces the existing index and wiki output, rather than silently doing
  nothing or requiring a separate command.
- What happens when the server-start command is run while a server for the
  same repository is already running (for example, a leftover process, or
  the configured port is already in use)? The tool reports the conflict
  clearly instead of starting a second, conflicting instance or failing
  with a low-level network error.
- What happens when the configuration command is run before any local LLM
  or embedding provider is reachable at all? The developer can still see
  and record their intended choice, but every candidate model is shown as
  currently unavailable, and the tool does not pretend the configuration
  is fully usable yet.
- What happens if the local LLM or embedding model becomes unavailable
  partway through a long indexing run (for example, the local service
  crashes or is stopped)? The command stops with a clear error identifying
  what became unavailable, rather than hanging or silently producing
  incomplete output.
- What happens when no configuration has ever been set and the developer
  runs the indexing command directly? The tool uses its documented default
  local LLM and embedding models, still verifying their availability
  before proceeding, rather than requiring the configuration command to be
  run first.
- What happens when the repository path is valid but contains no
  recognizable source files? The tool completes without error but reports
  that no relevant files were found, and the resulting wiki reflects an
  effectively empty repository rather than the command failing.

## Requirements *(mandatory)*

### Functional Requirements

#### Command surface

- The CLI MUST provide at least three distinct commands: initial
  indexing, server start, and configuration.
- Each command MUST be runnable non-interactively with a single
  invocation (arguments/flags), so it can be used without an interactive
  wizard, in addition to any interactive prompts the configuration command
  may also offer.
- Every command MUST be usable by a developer with no prior exposure to
  the tool, without requiring them to read source code or internal
  documentation first.

#### Initial indexing command

- The indexing command MUST accept a path to a local repository, and MUST
  default to the current working directory when no path is given.
- The indexing command MUST validate that the given path exists and is a
  readable repository directory before doing any other work, and MUST
  stop with a clear error if it is not.
- The indexing command MUST run repository scanning (001), multi-language
  parsing (002), symbol extraction (003), dependency graph construction
  (004), and metadata persistence (005) before summary generation (010)
  and embedding generation (009), and MUST generate the documentation
  wiki (012, 013) such that it reflects the completed summaries. The
  precise ordering of summarization, embedding, and any intermediate
  documentation-generation passes among themselves is an implementation
  detail (see `plan.md`/`research.md`), not a constraint this requirement
  imposes.
- The indexing command MUST report which stage is currently running as the
  pipeline progresses, so long-running indexing on large repositories is
  visibly making progress.
- On successful completion, the indexing command MUST make the generated
  wiki browsable locally and MUST print the local URL at which it can be
  viewed.
- If the indexing command is run again against a repository that already
  has an index, it MUST perform a fresh full run and replace the existing
  index and wiki output.
- If any stage fails, the indexing command MUST stop and MUST NOT leave
  partial or corrupted index or wiki output in place of the previous
  successful state (if one existed).

#### Server-start command

- The server-start command MUST start the local web server (015) serving
  the previously generated wiki (016) and exposing the chat API (014),
  bound to the local machine only, consistent with the project's
  zero-external-exposure-by-default principle.
- The server-start command MUST activate the repository watcher (017) and
  the incremental reindexing pipeline (018), so that subsequent file
  changes in the repository are reflected in the served wiki without a
  further manual command.
- The server-start command MUST fail with a clear, actionable error if no
  prior index exists for the target repository, directing the developer to
  run the indexing command first, and MUST NOT start a server with no
  indexed content.
- The server-start command MUST fail with a clear, actionable error if the
  server cannot bind (for example, because another instance is already
  running or the port is in use), rather than exiting with a low-level
  network error.
- On successful start, the server-start command MUST print the local URL
  at which the wiki can be viewed.

#### Configuration command

- The configuration command MUST allow selecting which local LLM model
  (008) is used for summary generation and chat.
- The configuration command MUST allow selecting which local embedding
  model (009) is used for embedding generation.
- The configuration command MUST persist the selected models so that
  subsequent indexing and server-start commands use them without the
  developer repeating the choice.
- The configuration command MUST indicate, for each candidate model,
  whether it is currently installed and reachable locally at the time the
  command runs.
- The configuration command MUST allow saving a selection for a model that
  is not currently installed, while clearly warning that the model must be
  installed before it can actually be used.
- When no configuration has ever been saved, the indexing and server-start
  commands MUST use a documented default local LLM model and embedding
  model rather than requiring the configuration command to be run first.

#### Local-model availability checks

- Before starting any step that depends on the local LLM or the local
  embedding model, every command MUST explicitly verify that the
  configured (or default) model is installed and reachable, and MUST NOT
  proceed into that step if it is not.
- The availability check MUST distinguish between the local model service
  being unreachable at all (for example, Ollama not running) and the
  service being reachable but the specific configured model not being
  installed, and MUST report which of these occurred.
- No command MUST ever fall back to a remote or cloud AI service when the
  local model is unavailable; unavailability MUST always be surfaced to
  the developer as an error to resolve, never silently worked around.

#### Error messaging

- The CLI MUST produce a distinct, actionable message for each of at
  least the following failure categories: repository path not
  found/invalid, local LLM service unreachable, configured model not
  installed, and server unable to start (for example, port already in
  use).
- Every error message MUST state what specifically went wrong and MUST
  suggest a concrete next action to resolve it, in language a developer
  with no prior knowledge of the tool can act on without consulting its
  source code.
- No command MUST hang indefinitely or exit silently on a failure; every
  failure MUST produce a visible message and a non-zero exit outcome.

### Key Entities

- **CLICommand**: One of the CLI's entry points (indexing, server start,
  configuration), with the arguments it accepts and the pipeline stages or
  actions it triggers.
- **CLIConfiguration**: The developer's persisted choice of local LLM
  model and local embedding model, read by the indexing and server-start
  commands and written by the configuration command.
- **PipelineRun**: A single execution of the indexing command against a
  repository: which stage is currently active, its progress, and its
  final success/failure outcome.
- **LocalModelAvailability**: The result of checking whether a given local
  model is installed and reachable at the moment a command needs it,
  including which specific problem (service unreachable vs. model not
  installed) was found, if any.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer with no prior knowledge of the tool can go from
  a local code repository and a working local LLM/embedding setup to a
  browsable documentation wiki by running exactly one command.
- **SC-002**: When the local LLM service or the configured model is
  unavailable, the indexing command stops before performing any
  AI-dependent processing and displays a message that correctly identifies
  which dependency is missing and how to resolve it.
- **SC-003**: Pointing the indexing command at a path that is not a valid
  repository produces a clear, specific error and leaves no partial index
  or wiki output behind.
- **SC-004**: The local URL printed after a successful indexing or
  server-start command, when opened in a browser, immediately shows the
  generated documentation wiki without any additional setup step.
- **SC-005**: Starting the server command against a repository that was
  never indexed always produces a clear error directing the developer to
  run indexing first, and never starts a server serving no content.
- **SC-006**: After a developer selects a local LLM model and an embedding
  model through the configuration command, every subsequent indexing and
  server-start run uses those models without the developer specifying them
  again.
- **SC-007**: Editing a file in a repository whose server is running with
  the watcher active results in the browsable wiki reflecting that change
  without the developer running any further command.

## Assumptions

- The three required commands are exposed as subcommands of a single CLI
  tool (for example, an `index`/`serve`/`config` style grouping); exact
  command names and flag syntax are an implementation detail left to
  planning.
- The indexing command's own local web server is what satisfies the "one
  command produces a browsable wiki" success criterion; the separate
  server-start command exists for resuming or continuing to serve an
  already-indexed repository with the watcher active, matching the feature
  description's split between the two commands.
- "Local model available" checking reuses the availability capability
  already established for local LLM access (008) and applies an
  equivalent check for the local embedding engine (009), rather than
  introducing a new detection mechanism.
- Sensible default local LLM and embedding models exist out of the box, so
  the configuration command is optional for a developer's first run,
  consistent with the "single command, no prior knowledge" success
  criterion.
- The indexing command performs a full run every time it is invoked; the
  incremental, partial-reprocessing path is exclusively triggered by the
  watcher (017) through the server-start command, per the incremental
  reindexing pipeline (018).
- The configuration command's list of candidate models is drawn from what
  the local LLM/embedding providers (008/009) already expose, not a
  hardcoded list maintained separately by this feature.
- This feature is a single-user, single-machine, single-repository-at-a-time
  tool, consistent with the project's minimal-infrastructure and
  local-only principles.
