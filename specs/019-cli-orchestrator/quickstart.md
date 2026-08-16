# Quickstart: Command-Line Interface Orchestrator

## Prerequisites

- Python 3.11 or later, project installed (`pip install -e .`), matching
  `README.md` "Install."
- A local Ollama-compatible service running at `http://localhost:11434`,
  with a small LLM model and an embedding model pulled (e.g. the tool's
  documented defaults — `data-model.md`'s `CLIConfiguration`).
- A sample local repository (a temporary directory with a handful of
  source files works, matching the fixtures other features' tests use).

## Validate the one-command golden path (SC-001, SC-004)

1. Run `repo-scanner index /path/to/sample-repo`.
2. Confirm terminal output shows each stage starting in order (scanning,
   parsing, building the dependency graph, generating summaries, updating
   embeddings, generating documentation), per `data-model.md`'s
   `PipelineRun.stage` sequence.
3. Confirm the command prints a local URL (`http://127.0.0.1:8000/` by
   default) before it starts blocking.
4. Open that URL in a browser. Confirm the generated documentation wiki
   is immediately visible — a home page and at least one page per
   indexed module — with no further setup step.

## Validate missing-dependency errors (US4, SC-002)

1. Stop the local Ollama service (or point `config` at an endpoint with
   nothing listening — see the `config` scenario below).
2. Run `repo-scanner index /path/to/sample-repo`.
3. Confirm the command exits non-zero, prints a message identifying that
   the local LLM (or embedding) service is unreachable and how to start
   it, and performs no scanning/parsing/summarization/embedding work
   before exiting.
4. Restart the local service, but rename/remove the configured model so
   the service is reachable yet the model isn't installed.
5. Run `repo-scanner index /path/to/sample-repo` again.
6. Confirm the message this time specifically names the missing model
   (not a generic "service unreachable" message), distinguishing the two
   failure kinds per `contracts/cli-interface.md`.

## Validate invalid-repository errors (US4, SC-003)

1. Run `repo-scanner index /path/does/not/exist`.
2. Confirm the command exits non-zero immediately, with a message naming
   the given path and stating it doesn't exist — and that no
   `~/.repo-scanner/repos/<state-id>/` directory is created as a result
   (no partial output left behind).

## Validate resuming with the watcher (US2, SC-005, SC-007)

1. With the sample repository already indexed (golden-path scenario
   above completed at least once, then the `index` process stopped), run
   `repo-scanner serve /path/to/sample-repo`.
2. Confirm the command prints the local URL and that the previously
   generated wiki is immediately browsable there (no re-indexing wait).
3. Edit one source file in the sample repository (change a function body
   or add a new function).
4. Wait briefly (past the watcher's stabilization delay, per 017).
5. Refresh the wiki page for the changed file in the browser. Confirm it
   reflects the edit, without running any further command.
6. Stop the server (Ctrl+C). Run `repo-scanner serve
   /path/to/a-never-indexed-repo`.
7. Confirm the command exits non-zero with a message directing you to run
   `repo-scanner index` first, and that no server starts.

## Validate model configuration (US3, SC-006)

1. Run `repo-scanner config`.
2. Confirm it prints the current configuration (defaults, if this is the
   first run) and, for the configured LLM/embedding model, whether each
   is currently installed and reachable, plus a list of other installed
   models found at the same endpoint(s).
3. Run `repo-scanner config --llm-model <a-different-installed-model>`.
4. Confirm it saves successfully and that a subsequent `repo-scanner
   config --show` reflects the new value.
5. Run `repo-scanner config --embedding-model
   some-model-that-is-not-installed`.
6. Confirm it still saves (no failure) but prints a clear warning that the
   model isn't installed yet.
7. Run `repo-scanner index /path/to/sample-repo` again.
8. Confirm the run now uses the newly configured LLM model (for example,
   by checking the local LLM service's own request log, if available) —
   demonstrating the saved configuration is honored without specifying it
   again on the command line.

## Validate the existing `scan` command is unaffected (regression check)

1. Run `repo-scanner scan /path/to/sample-repo`.
2. Confirm the output still matches
   `specs/001-local-repo-scanner/contracts/cli.md` exactly (a JSON
   document with `root_path`, `generated_at`, `entries`, `summary`),
   unchanged by this feature.

## Expected result

Running one command (`repo-scanner index`) against a valid local
repository with a working local LLM/embedding setup produces a browsable
documentation wiki at a printed local URL, with no other command needed.
Missing dependencies (repository path, local LLM/embedding service or
model) are reported clearly and stop the command before any wasted or
partial work. `repo-scanner serve` resumes an already-indexed repository
with live updates. `repo-scanner config` lets a developer choose and
persist their local models across runs.
