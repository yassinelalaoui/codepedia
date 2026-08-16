# CLI Contract: Command-Line Interface Orchestrator

## Purpose

Define the command surface a developer invokes to go from a local
repository to a browsable documentation wiki, to keep that wiki current
while working, and to choose which local models power both — the single
entry point (`repo-scanner`) this feature adds to the project, superseding
`repo_scanner.cli:app` as the `[project.scripts]` target (research.md §3).

## Command: `repo-scanner index [PATH] [--host HOST] [--port PORT]`

**Inputs**:
- `PATH` (optional, positional): repository root to index. Defaults to the
  current working directory.
- `--host` (optional): bind address for the web server started at the end
  of a successful run. Defaults to `127.0.0.1`.
- `--port` (optional): bind port. Defaults to `8000`.

**Expected behavior**:
- Validates `PATH` exists and is a readable directory before any other
  work; fails with `RepositoryNotFoundError`'s message otherwise.
- Loads `CLIConfiguration` (defaults if none saved) and verifies both the
  configured LLM model and embedding model are available locally
  (research.md §7) before scanning; fails with a message identifying which
  one is unavailable and why (service unreachable vs. model not
  installed) otherwise.
- Runs the full pipeline in the exact order in `data-model.md`'s "State
  flow: `index`": scan (001) → parse + extract (002/003) → persist
  metadata (005) → build + save dependency graph (004) → generate docs,
  pass 1 (012) → generate summaries (010) → generate docs, pass 2 (012) →
  update embeddings (006/007/009).
- Prints which stage is currently running as the pipeline advances
  (`PipelineRun.stage`, `data-model.md`).
- On success, prints the local URL (`http://<host>:<port>/`) and starts
  serving the generated wiki + chat API at that address, blocking until
  interrupted (Ctrl+C).
- Re-running against an already-indexed repository (same resolved path)
  replaces that repository's prior state (`data-model.md`'s
  `RepositoryState` directory) with a fresh full run.
- Builds the run into a staging directory and only replaces the prior
  `RepositoryState` on full success (research.md §10); if any stage fails,
  a previously-successful `RepositoryState` for the same repository is
  left completely untouched — never partially overwritten.

**Exit behavior**:
- `0`: server shut down cleanly after a successful index (Ctrl+C).
- `1`: `PATH` does not exist or is not a directory.
- `1`: local LLM service unreachable, or configured LLM model not
  installed.
- `1`: local embedding service unreachable, or configured embedding model
  not installed.
- `1`: the web server could not bind to `--host`/`--port` (e.g., already
  in use).
- `1`: any pipeline stage raised after checks passed (e.g., the local LLM
  crashed mid-run) — the staging directory is discarded and any prior
  successful `RepositoryState` is left untouched (research.md §10).

## Command: `repo-scanner serve [PATH] [--host HOST] [--port PORT]`

**Inputs**: identical to `index` (`PATH`, `--host`, `--port`).

**Expected behavior**:
- Same `PATH` validation and local-model availability check as `index`
  (research.md §7).
- Requires a prior successful `index` run for the resolved `PATH`
  (`RepositoryMetadataStore.load_repository_record` finds a record,
  `data-model.md`); fails with a message directing the developer to run
  `repo-scanner index` first otherwise, and does not start a server.
- Loads the existing `RepositoryState` (dependency graph, vector index,
  doc manifest) rather than rebuilding it.
- Starts the repository watcher (017) wired to the incremental reindexing
  pipeline (018), running its startup catch-up batch before the server
  starts accepting requests.
- Prints the local URL and starts serving, blocking until interrupted; a
  file change while running results in the served wiki reflecting that
  change without any further command (spec SC-007).
- On shutdown, stops the watcher cleanly before exiting.

**Exit behavior**:
- `0`: server shut down cleanly (Ctrl+C).
- `1`: `PATH` does not exist or is not a directory.
- `1`: local LLM/embedding service unreachable, or configured model not
  installed.
- `1`: no prior index exists for `PATH`.
- `1`: the web server could not bind to `--host`/`--port`.

## Command: `repo-scanner config [--llm-model NAME] [--llm-endpoint URL] [--embedding-model NAME] [--embedding-endpoint URL] [--show]`

**Inputs**: all optional.
- `--llm-model` / `--llm-endpoint`: new values for the LLM side of
  `CLIConfiguration`.
- `--embedding-model` / `--embedding-endpoint`: new values for the
  embedding side.
- `--show`: print the current configuration and exit without changing
  anything.

**Expected behavior**:
- With no flags at all: prints the current `CLIConfiguration` (defaults if
  none saved yet) together with, for the configured LLM model and
  embedding model, whether each is currently installed and reachable
  (`AvailabilityStatus`/`EmbeddingAvailabilityStatus`, via
  `checkAvailability()`), and also lists every other currently installed
  model at each configured endpoint (`listInstalledModels()`,
  research.md §5) as candidates.
- With `--show`: same read-only report as above, explicitly, with no
  write.
- With one or more model/endpoint flags: validates any given endpoint URL
  (`normalize_endpoint_url`), saves the resulting `CLIConfiguration` to
  `~/.repo-scanner/config.json`, and prints a warning (not a failure) for
  any newly set model name absent from that endpoint's
  `listInstalledModels()` result.
- Never fails solely because a selected model isn't installed yet — saving
  an intended-but-not-yet-installed choice is allowed (spec US3).

**Exit behavior**:
- `0`: configuration displayed and/or saved successfully (including when
  a "model not installed yet" warning was printed).
- `1`: an endpoint URL flag fails local-only validation (points off
  `localhost`/`127.0.0.1`, wrong scheme, etc.).

## Command: `repo-scanner scan PATH`

**Inputs**: `PATH` (required, positional) — unchanged from spec 001.

**Expected behavior**: unchanged — thin delegation to
`repo_scanner.scanner.scan_repository` /
`repo_scanner.output.serialize_scan_result` (research.md §3), preserving
`specs/001-local-repo-scanner/contracts/cli.md` exactly. Included here only
because it now lives under the same `repo-scanner` entry point as
`index`/`serve`/`config`, not because this feature changes its behavior.

## Error message expectations (all commands)

Every failure exit prints, to stderr, a message that states what went
wrong and suggests a concrete next action (spec FR "Error messaging") —
never a raw Python traceback, and never a silent non-zero exit with no
message. The four categories below are distinguished by wording, not by
distinct exit codes (all failures exit `1`):

| Category | Distinguishing detail in the message |
|---|---|
| Repository path invalid | Names the path given and that it does not exist / is not a directory. |
| Local LLM service unreachable | States the endpoint URL and that Ollama (or a compatible service) needs to be started there. |
| Configured model not installed | Names the specific model and states it needs to be pulled/installed, service already reachable. |
| Server bind failure | Names the `host:port` and that it is already in use or otherwise unavailable. |

## Non-goals of this contract

- It does not define `local_llm`/`embedding_engine`/`repo_watcher`/
  `reindex_pipeline`/`doc_generator`/`chat_api`'s own behavior — those
  remain governed by their own contracts (008/009/017/018/012/014).
- It does not define a machine-readable (JSON) output mode for any
  command; all output here is human-readable terminal text, matching the
  spec's "developer with no prior knowledge" framing over a scripting use
  case.
