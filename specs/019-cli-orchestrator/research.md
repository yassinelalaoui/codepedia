# Phase 0 Research: Command-Line Interface Orchestrator

## 1. Language and CLI framework

**Decision**: Python 3.11, using **Typer** (already a project dependency,
`pyproject.toml` line `"typer>=0.12"`), not Node.js.

**Rationale**:
- The user's plan input offered a choice ("Node.js ou Python (Typer/Click),
  installable via npx doc-gen ou pip install"). Every existing package in
  `src/` is Python 3.11 (`pyproject.toml`, `requires-python = ">=3.11"`),
  and `docs/stack.md` §"CLI" already documents Typer as "the standard
  choice for a local dev tool's entry point," used by the existing
  `repo_scanner/cli.py` (001). Introducing Node.js here would split the
  backend into two runtimes for the one component (the orchestrator) that
  most needs to stay simple to invoke, repeating the exact reasoning
  `docs/stack.md` already used to reject `chokidar` for the watcher (017).
- Typer requires no new dependency and gives typed arguments/options,
  automatic `--help`, and subcommand grouping out of the box — a good fit
  for three-plus commands under one entry point.

**Alternatives considered**:
- Node.js CLI (e.g., a `commander`/`yargs`-based tool invoked via
  `npx doc-gen`): rejected — would require packaging and shipping a second
  language runtime and its own dependency tree solely for the entry point,
  while every capability it would call (scanning, parsing, summarizing,
  embedding, serving) is Python-only and in-process. `frontend/` already
  uses Node, but only to *build* a static asset bundle that ships without
  Node at runtime (`README.md` "Prerequisites"); a Node CLI would be a
  different, runtime dependency, not a build-time one.
- Click directly (without Typer): rejected — Typer is Click under the
  hood with typed decorators, and the project has already standardized on
  Typer for `repo_scanner/cli.py`; using Click directly would just be a
  lower-level version of the same choice, for no benefit.

## 2. Distribution / installation method

**Decision**: `pip install`, via the existing `pyproject.toml`
`[project.scripts]` console-script mechanism — no new packaging system.

**Rationale**: The project already installs with `pip install -e .`
(`README.md` "Install") and already declares one console script,
`codepedia = "repo_scanner.cli:app"`. `npx doc-gen` (the plan input's
Node-flavored alternative) has no equivalent meaning for a Python project
and was only offered as a paired example alongside the Node.js language
option, which was not chosen (§1).

**Alternatives considered**: A separate installer script or standalone
binary (e.g., PyInstaller): rejected — no other feature in this project
introduces build/packaging tooling beyond `pyproject.toml` and `pip`, and
nothing in the spec asks for a self-contained executable.

## 3. Console-script entry point: extend or supersede `repo_scanner.cli`

**Decision**: Repoint the existing `codepedia` console script (currently
`repo_scanner.cli:app`) to a new top-level `cli` package
(`codepedia = "cli.main:app"`), whose Typer app registers four
commands: the three the spec requires (`index`, `serve`, `config`) plus
`scan`, which thinly delegates to the same `repo_scanner.scanner.
scan_repository` / `repo_scanner.output.serialize_scan_result` functions
`repo_scanner/cli.py`'s existing `scan` command already calls — so
`codepedia scan <path>` keeps working exactly as spec 001's contract
(`specs/001-local-codepedia/contracts/cli.md`) describes.

**Rationale**:
- The feature's own success criterion (SC-001) is "a developer ... can go
  ... to a browsable documentation wiki by running exactly one command."
  A single command **name** with subcommands (`codepedia index`,
  `codepedia serve`, `codepedia config`, `codepedia scan`) is
  what "one command, no prior knowledge" means in practice — a second,
  differently-named executable for the orchestrator would immediately
  contradict that goal by making the developer choose between two tools.
- No test exercises the `codepedia` console script or
  `repo_scanner.cli.app` directly (confirmed by search across `tests/`);
  only `README.md` and spec 001's own contract document it, and both
  continue to be satisfied since `scan` keeps its exact existing
  behavior, just re-registered under the new umbrella app.
- `src/repo_scanner/cli.py` itself is left untouched — `python -m
  repo_scanner scan` (`README.md`'s documented alternative invocation)
  keeps working unmodified. Only `pyproject.toml`'s script target moves.
- This matches the layering `docs/architecture.md` already describes:
  later layers depend on earlier ones, never the reverse. The new `cli`
  package is the outermost layer (an "Entry Point" layer, §9), free to
  depend on `repo_scanner` (layer 1) and every other layer, exactly as
  `repo_watcher`/`reindex_pipeline` (layer 5) already depend on layers
  1–4 without those earlier layers knowing they exist.

**Alternatives considered**:
- Add `index`/`serve`/`config` directly into `repo_scanner/cli.py`:
  rejected — `repo_scanner` (001) is an Ingestion & Analysis-layer
  package; giving it knowledge of `local_llm`, `doc_generator`,
  `chat_api`, `repo_watcher`, and `reindex_pipeline` would invert the
  project's layering rule for the sake of file convenience.
- A second, separately named console script (e.g. `doc-gen`) alongside
  `codepedia`: rejected per SC-001 above — two entry points for one
  tool undermines "one command, no prior knowledge."

## 4. Where CLI-managed state lives on disk

**Decision**: Two locations, both under the user's home directory, never
inside the analyzed repository:

- `~/.codepedia/config.json` — the persisted `CLIConfiguration`
  (chosen LLM model/endpoint, embedding model/endpoint), machine-wide.
- `~/.codepedia/repos/<state-id>/` — one directory per indexed
  repository, holding that repository's `repository-metadata.sqlite`
  (005), `dependency-graph.sqlite` (004), `vector-index.sqlite` +
  `vector-metadata.sqlite` (006/007), `doc-manifest.sqlite` (012's
  `DocPageManifestStore`), and `docs/` (the `DocGenerator` `outputRoot`
  served by the local web server). `<state-id>` is the first 16 hex
  characters of `sha256(stable_repository_id(root))`
  (`repository_metadata.sqlite_store.stable_repository_id` already
  produces a stable-but-not-filesystem-safe string like
  `repo::/abs/posix/path`; hashing it yields a short, safe directory
  name while staying collision-resistant per repository path).

**Rationale**:
- Constitution 2.7 ("le dépôt de code analysé reste en lecture seule ...
  la seule écriture autorisée concerne la documentation générée, dans un
  dossier séparé du dépôt source") is satisfied unambiguously: nothing
  this feature writes ever touches a path under the analyzed repository
  root, full stop — not even the sqlite index files.
- `DocGenerator.generateRepositoryDocumentation`'s own guard
  (`_ensure_output_root_is_separate`, `doc_generator/generator.py:411`)
  already *requires* `outputRoot` not to equal or overlap
  `repositoryRoot`; a home-directory location satisfies this by
  construction for any repository path, with no per-repository
  configuration needed.
- The developer's local LLM/embedding model choice is a fact about their
  *machine* (which models Ollama has installed), not about any one
  repository, so a single global `config.json` means configuring once
  covers every repository the developer indexes with this tool — matching
  spec.md's Assumption that the configuration command is optional on a
  first run and, once set, applies to "subsequent indexing and
  server-start runs" without qualifying that by repository.
- One directory per repository (rather than one flat set of files) keeps
  multiple indexed repositories from colliding, without requiring the
  developer to pass explicit `--index-db`/`--docs-root`/etc. paths for
  every command the way `chat_api/server.py`'s existing flags require —
  consistent with SC-001's "no prior knowledge" bar.

**Alternatives considered**:
- Reusing `chat_api/server.py`'s existing default,
  `<repo_root>/.codepedia/{vector-index.sqlite,vector-metadata.sqlite}`
  (writing inside the analyzed repository): rejected for this new code —
  it is an existing, already-shipped default for *that module's own*
  optional flags (unchanged by this feature), but adopting the same
  pattern for `index`/`serve`/`config` would write the *entire* new state
  set (metadata, graph, manifest, docs, and generated wiki output) inside
  the developer's source tree, which is a much larger footprint than the
  two vector-index files that pattern currently covers, and would read as
  the project's own default rather than one flag's default. A clean
  home-directory layout avoids re-litigating or duplicating that existing
  flag default, which this feature does not change.
- A per-repository config file (e.g.
  `<repo_root>/.codepedia/config.json` or the home-directory
  equivalent nested under `repos/<state-id>/config.json`): rejected —
  would force re-selecting the same LLM/embedding model for every
  repository indexed, with no benefit, since the model choice is a
  machine-level fact.
- Using the raw `stable_repository_id(root)` string
  (`"repo::/abs/posix/path"`) directly as a directory name: rejected — `:`
  and `/` inside it are invalid or structurally meaningful path
  separators on at least one target OS (Windows disallows `:` in path
  segments other than a drive letter); hashing avoids this entirely.

## 5. Listing installed local models for the `config` command

**Decision**: Add one small, compatible extension method to each existing
engine, mirroring the "small extension" pattern 017/018 already used for
`DependencyGraph`/`RepositoryMetadataStore`:

- `LocalLLMEngine.listInstalledModels(self) -> tuple[str, ...]` — thin
  passthrough to `self._transport.list_models()`, which already exists
  (`local_llm/transport.py:73`, calls Ollama's `/api/tags`) but was not
  previously exposed on the public `LocalLLMEngine` façade.
- `EmbeddingEngine.listInstalledModels(self) -> tuple[str, ...]` — new
  method on `EmbeddingEngine`, backed by a new
  `LocalEmbeddingTransport.list_models(self) -> tuple[str, ...]` that
  factors out the same `/api/tags` call and name-extraction
  `EmbeddingEngine`'s own `availability()` already performs inline
  (`embedding_engine/transport.py:94-111`) into a reusable method, rather
  than duplicating that parsing a second time inside the new `cli`
  package.

**Rationale**:
- Spec FR ("Configuration command") requires showing, "for each candidate
  model, whether it is currently installed and reachable locally" — this
  needs an enumeration of installed models, not just a yes/no check on one
  typed-in name. `local_llm/transport.py` already has exactly this
  (`list_models`); `embedding_engine` has the same data available inside
  `availability()` but not as its own callable.
- Both additions are pure, read-only, local-only HTTP calls to the same
  already-validated `endpointUrl` these classes already call for every
  other method — no new network surface, no change to existing behavior
  or signatures.

**Alternatives considered**:
- Reaching into `LocalLLMEngine._transport` from the `cli` package
  directly: rejected — `_transport` is a private, `repr=False` field;
  every other cross-package call in this codebase goes through a public
  method (e.g., `isAvailableLocally`, `checkAvailability`), and `cli`
  should follow the same rule rather than being the first caller to break
  encapsulation.
- Requiring the developer to already know exact installed model names
  (no listing at all, `config` only validates a typed name): rejected —
  contradicts the spec's explicit "shows ... whether it is currently
  installed" requirement, and defeats the point of a discoverable,
  no-prior-knowledge configuration step.

## 6. `index` command orchestration order

**Decision**: Reproduce, stage for stage, the order
`tests/integration/test_reindex_pipeline.py`'s `Harness.full_reindex`
already uses and validates (and which
`docs/diagrams/sequence-diagrams/01-full-indexing.md` documents at a
higher level):

1. `scan_repository(root)` (001) → candidate file list.
2. Per file: `extract_symbols` (002/003) → `RepositoryMetadataStore.
   store_inventory(..., content_hash=compute_content_hash(...))` (005).
3. `DependencyGraph.build_from_inventories(inventories, id=state_id,
   sourceFile=str(root))` (004), then `.save(graph_db_path)`.
4. `DocGenerator.generateRepositoryDocumentation(root, incremental=False)`
   (012) — first pass, before summaries exist.
5. `CodeSummaryPipeline.summarizeRepository(root, incremental=False)`
   (010).
6. `DocGenerator.generateRepositoryDocumentation(root, incremental=False)`
   again — second pass, so pages reflect the summaries just generated.
7. Per file: `update_embeddings(...)` (`reindex_pipeline.embeddings`,
   018) — the same already-wired per-file embedding helper the
   incremental pipeline uses, rather than calling `EmbeddingEngine.embed`
   + `VectorIndex.addChunks` directly a second, parallel way.
8. Start the local web server (`chat_api.create_app` + `uvicorn.run`,
   014/015) serving `docs/` from the same state directory, printing the
   local URL before blocking.

**Rationale**: This exact sequence is already implemented, already
exercised by the full existing `tests/integration/test_reindex_pipeline.py`
suite (every US1-US4 test in that file depends on `Harness.full_reindex`
having produced a correct baseline first), and already documented as the
intended flow in `docs/diagrams/sequence-diagrams/01-full-indexing.md`.
Reusing it exactly — including the two-pass doc-generation call and the
`update_embeddings` helper (rather than the sequence diagram's more literal
`embed` + `addChunks` reading) — means `index` has no new orchestration
logic to independently verify; it is calling already-tested library code
in an already-tested order.

**Alternatives considered**:
- Calling `EmbeddingEngine.embed` + `VectorIndex.addChunks` directly per
  the sequence diagram's literal reading: rejected — `update_embeddings`
  already wraps exactly this (chunking + embedding + indexing) as a single
  tested call used by `reindex_pipeline` (018); calling the lower-level
  primitives directly in `cli` would duplicate that wiring for no benefit
  and risk drifting from the incremental path's behavior.
- Generating documentation only once, after summaries: rejected — the
  `Harness` reference implementation and its passing tests generate twice
  (structure, then content-with-summaries); a single post-summary pass is
  unverified and risks producing pages before dependency/graph-derived
  content each page needs is ready, consistent with the two-pass approach.

## 7. When to check local-model availability

**Decision**: For `index` and `serve`, check `LocalLLMEngine.
isAvailableLocally()` and `EmbeddingEngine.isAvailableLocally()` once,
immediately after validating the repository path and before any other
work (scanning, parsing, starting the server) begins — not just
immediately before the first AI-dependent stage deep inside the pipeline.

**Rationale**: `index`'s pipeline (§6) always reaches an AI-dependent
stage (summary generation, embedding) — there is no successful `index` run
that skips them. Checking only right before step 5/7 would let a
large-repository scan and parse (potentially the most time-consuming
non-AI part of the run) complete first, only to fail afterward — wasted
work a no-prior-knowledge developer has no way to anticipate. Checking
upfront satisfies the letter of the requirement ("before starting any step
that depends on the local LLM/embedding model") at the earliest possible
point, which directly serves SC-002 ("stops before performing any
AI-dependent processing... before wasted work").

**Alternatives considered**:
- Checking lazily, right before each AI-dependent stage only: rejected
  for `index`/`serve` specifically, per the wasted-work reasoning above.
  (`CodeSummaryPipeline`/`EmbeddingEngine` still perform their own
  availability check internally too, since that behavior is theirs to
  keep per 010/009's own contracts — the CLI's upfront check is an
  additive, earlier fast-fail, not a replacement for those.)

## 8. `serve` command: hosting the watcher alongside the web server

**Decision**: In one process: build the same set of objects `index`
would reuse to construct an `IncrementalReindexPipeline` (018) —
`RepositoryMetadataStore`, the loaded `DependencyGraph`
(`DependencyGraph.load(graph_db_path, graph_id=state_id)`), `VectorIndex`,
`EmbeddingEngine`, `CodeSummaryPipeline`, `DocGenerator` — then construct
a `RepositoryWatcher` (017) with `on_batch=reindex_pipeline.run`, call
`watcher.start()` (runs the startup catch-up batch synchronously, then
starts its own background `Observer` thread per 017's contract), then call
`chat_api.create_app(...)` and `uvicorn.run(app, host=host, port=port)` —
the same blocking call `chat_api/server.py` already uses — in a
`try/finally` that calls `watcher.stop()` on shutdown (Ctrl+C or any other
exit from `uvicorn.run`).

**Rationale**: `RepositoryWatcher.start()` (`repo_watcher/watcher.py:50`)
is documented to return once its own catch-up pass completes, running its
continuous detection on its own thread — it does not need `serve` to
provide an event loop or scheduler of its own. `uvicorn.run(...)`
(synchronous, blocking) is exactly the mechanism that already keeps the
process alive for `chat_api/server.py`'s existing `main()`; reusing it
here means `serve` needs no new concurrency model, just the watcher
started before the blocking call and stopped after it returns.

**Alternatives considered**:
- Running the watcher and the web server as two separate OS processes:
  rejected — the constitution's "infrastructure minimale" principle (2.6)
  and `docs/architecture.md`'s "Runtime & deployment model" both frame
  017 as "designed to be embedded in the same process as the web server or
  invoked by a CLI," which `serve` is exactly the CLI-side half of.
- An `asyncio`-based server loop driving the watcher: rejected —
  `RepositoryWatcher` already manages its own thread; adding `asyncio`
  would be a second concurrency model layered on top for no capability
  gain, and `chat_api`'s existing `uvicorn.run(...)` call is already
  synchronous.

## 9. Error message design

**Decision**: One small `cli.errors` module defining one exception per
failure category the spec's FR "Error messaging" names — repository path
invalid, local LLM service unreachable, configured model not installed,
server bind failure — each carrying a human-readable message and a
suggested next action, caught at the top of each Typer command and
reported via `typer.echo(..., err=True)` followed by `raise typer.Exit(
code=1)`. Messages reuse the *reason* already distinguished by
`AvailabilityStatus`/`EmbeddingAvailabilityStatus`'s
`serviceReachable`/`modelInstalled` fields (009/010) rather than
re-deriving that distinction.

**Rationale**: `local_llm`/`embedding_engine` already distinguish "service
unreachable" from "model not installed" at the `AvailabilityStatus` level
(`serviceReachable: bool`, `modelInstalled: bool`) with an actionable
`message` field already worded for a human reader
(`local_llm/transport.py:82-108`). The CLI's job is to route that existing
detail to the terminal with a non-zero exit code, not to reclassify it.

**Alternatives considered**:
- Letting underlying exceptions (`ServiceUnavailableError`,
  `ModelMissingError`, etc. from `local_llm.errors`/`embedding_engine.
  errors`) propagate as raw Python tracebacks: rejected — spec FR
  explicitly requires messages "a developer with no prior knowledge of the
  tool can act on," which a raw traceback is not, and every other command
  in this project that can fail already converts its errors into a clear,
  addressed message before exiting.

## 10. Not corrupting a prior successful index when a re-run fails partway

**Decision**: `run_index` writes every stage's output to a fresh, sibling
staging directory — `repo_state_dir(root) + ".staging-<pid>"`, next to
(never inside) the real `~/.codepedia/repos/<state_id>/` — rather than
directly into the final `RepositoryState` location. Only after every stage
(scan through the final embedding pass, §6) has completed successfully
does `run_index` atomically replace the final location with the staging
directory: remove the prior `<state_id>/` (if any, via `shutil.rmtree`)
and rename `<state_id>.staging-<pid>/` to `<state_id>/` (`Path.replace`,
which `os.rename`s a directory onto a non-existent or just-removed target
on every platform this project supports). If any stage raises, `run_index`
deletes the staging directory and leaves the prior `<state_id>/` — success
or absence — completely untouched, then re-raises so `cli.main`'s
`report_and_exit` (research.md §9) reports the failure.

**Rationale**: spec.md's FR is explicit: "If any stage fails, the indexing
command MUST stop and MUST NOT leave partial or corrupted index or wiki
output in place of the previous successful state (if one existed)." Every
component `run_index` calls (`RepositoryMetadataStore`, `DependencyGraph`,
`VectorIndex`, `DocPageManifestStore`, `DocGenerator`) writes incrementally
as it goes — there is no single transaction boundary inside any of them to
rely on. Building into an unpublished sibling directory and only swapping
it in on full success is the smallest change that satisfies the
requirement without modifying any of those five components: from the
perspective of `serve` or a second `index` run, `<state_id>/` either still
holds the last fully-successful run's output, or (first run only) does not
exist yet — it is never observed half-written.

**Alternatives considered**:
- Writing directly into `<state_id>/` and attempting to roll back
  individual stores on failure: rejected — would require adding rollback
  logic to `RepositoryMetadataStore`/`DependencyGraph`/`VectorIndex`/
  `DocPageManifestStore` (each its own SQLite file with its own writes
  already committed incrementally), which is exactly the "modify existing
  components" cost the staging-directory approach avoids entirely.
- Per-component transactions (e.g., a single SQLite transaction spanning
  all four stores plus the filesystem `docs/` writes): rejected — SQLite
  transactions cannot span multiple database files or plain filesystem
  writes atomically, and `docs/` output is files, not rows, so this
  doesn't compose the way the requirement needs.
- Accepting the requirement as satisfied by `index` always performing a
  fresh full run (research.md's original reasoning for the "no incremental
  index" Assumption): rejected — a fresh full run only produces a correct
  *end* state when it succeeds; a full run that fails partway through
  still leaves whatever it already wrote, which is exactly the corruption
  the requirement rules out. "Always full" and "never corrupts on
  failure" are independent guarantees.
