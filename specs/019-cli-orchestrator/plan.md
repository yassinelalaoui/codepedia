# Implementation Plan: Command-Line Interface Orchestrator

**Branch**: `019-cli-orchestrator` | **Date**: 2026-08-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/019-cli-orchestrator/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add a new `cli` package that becomes the project's single entry point
(`repo-scanner`, replacing `repo_scanner.cli:app` as the `pyproject.toml`
console-script target — research.md §3), exposing four commands: `index`
(runs the full pipeline — scan 001, parse/extract 002/003, persist 005,
build the dependency graph 004, summarize 010, embed 006/007/009, generate
the wiki 012 — reusing the exact order `tests/integration/
test_reindex_pipeline.py`'s `Harness.full_reindex` already validates,
staged into a sibling directory and swapped in only on full success so a
failed re-run never corrupts a prior successful index — research.md §10 —
then starts the local web server 014/015 and prints its URL); `serve` (loads an
already-indexed repository's state, wires the repository watcher 017 to
the incremental reindexing pipeline 018, and starts the same local web
server); `config` (reads/writes a new machine-wide `CLIConfiguration` at
`~/.repo-scanner/config.json`, choosing the local LLM model and embedding
model `index`/`serve` use); and the pre-existing `scan` (001, unchanged,
re-registered under the same entry point). Every command that touches the
local LLM or embedding model checks availability
(`isAvailableLocally`/`checkAvailability`, 008/009) before doing any
AI-dependent work and fails with a specific, actionable message otherwise
— never a raw traceback, never a silent fallback.

## Technical Context

**Language/Version**: Python 3.11 (matches `pyproject.toml`, consistent
with every sibling feature; research.md §1 — Node.js, offered as an
alternative in the plan's own input, was not chosen)

**Primary Dependencies**: No new third-party dependency. **Typer**
(already `pyproject.toml`'s `"typer>=0.12"`, already used by
`repo_scanner/cli.py`, 001) for the CLI itself (research.md §1). Reuses
in-repo packages directly: `repo_scanner` (001), `parser_engine`
(002/003), `repository_metadata` (005, incl. `fingerprints.
compute_content_hash` and `sqlite_store.stable_repository_id`),
`dependency_graph` (004), `repository_metadata.summary_pipeline.
CodeSummaryPipeline` (010), `vector_index`/`embedding_engine` (006/007/009,
plus `embedding_engine`'s new `listInstalledModels` — research.md §5),
`local_llm` (008, plus its new `listInstalledModels` — research.md §5),
`doc_generator` (012), `chat_api.create_app` + `uvicorn` (014/015),
`repo_watcher` (017), and `reindex_pipeline` (018).

**Storage**: One new machine-wide JSON file, `~/.repo-scanner/config.json`
(`CLIConfiguration` — research.md §4), plus one new per-repository
directory tree, `~/.repo-scanner/repos/<state-id>/`, holding the same
SQLite files (`repository_metadata`, `dependency_graph`, `vector_index`,
`doc_generator`'s manifest) and generated `docs/` output every existing
component already produces — just written to a new, home-directory
location rather than caller-supplied paths, so the analyzed repository is
never written to (research.md §4, constitution 2.7). `index` writes each
run to an unpublished sibling staging directory first and only replaces
the prior directory tree on full success (research.md §10).

**Testing**: `pytest`, matching the existing `tests/unit`,
`tests/integration`, `tests/contract` layout; Typer's `CliRunner`
(bundled via `typer.testing`) for command-level tests.

**Target Platform**: Local developer machine (Windows/macOS/Linux) — this
is the process a developer actually runs; it starts and hosts the local
web server (014/015) and, for `serve`, the watcher (017) in the same
process, per `docs/architecture.md`'s "Runtime & deployment model," which
already anticipated a CLI filling exactly this role.

**Project Type**: Single Python library/package added to the existing
`src/` layout, as a new outermost "Entry Point" layer that depends on
every existing layer (research.md §3) — no frontend/backend split.

**Performance Goals**: `index`'s own added overhead (argument parsing,
config load, availability checks, stage orchestration) is negligible
next to the pipeline stages it calls, which already have their own
performance goals from 001/002/003/010/009/012 — this feature does not
introduce a new performance target, only sequences existing ones.

**Constraints**: Every command that reaches an AI-dependent step MUST
check local-model availability first and MUST NOT proceed if unavailable,
with no cloud fallback ([[constitution 2.3]]); the analyzed repository
MUST NOT be written to by any command ([[constitution 2.7]]); the web
server both `index` and `serve` start MUST bind to `127.0.0.1` by default
([[constitution 2.2]]); `serve` MUST refuse to start against a repository
with no prior index rather than serving an empty result (spec FR).

**Scale/Scope**: One CLI process per invocation (`index`/`serve` run as a
single long-lived foreground process once started; `config` and `scan`
are short-lived); one `~/.repo-scanner/repos/<state-id>/` directory per
distinct repository path a developer has indexed, with no ceiling assumed
beyond normal local disk usage.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
| --- | --- | --- |
| 2.1 Confidentialité absolue | The CLI only calls already-local components (scanner, parser, metadata store, dependency graph, local LLM/embedding via existing engines, doc generator, watcher, reindex pipeline, chat API); no new network calls beyond what those components already make to `localhost` | PASS |
| 2.2 Zero exposition réseau | `index`/`serve` bind the web server they start to `127.0.0.1` by default (`--host` override available, matching `chat_api/server.py`'s existing flag, never on by default) | PASS |
| 2.3 Jamais de repli silencieux vers le cloud | `index`/`serve` explicitly check `isAvailableLocally()` for both the LLM and embedding model before any AI-dependent step and stop with an actionable error if unavailable (research.md §7); no command ever falls back to a remote service | PASS (directly implements this principle, per spec FR) |
| 2.4 Traçabilité des réponses IA | The CLI does not change how summaries/chat answers are attributed to source symbols — it only triggers `CodeSummaryPipeline` (010) and `chat_api` (014), whose existing citation behavior is untouched | PASS |
| 2.5 Ré-indexation incrémentale | `serve` never re-runs the full pipeline on a change — it wires the existing watcher (017) and incremental pipeline (018), which already guarantee this; `index` itself is always a full run, by design (spec Assumptions) | PASS |
| 2.6 Infrastructure minimale et stockage local | No new dependency; `CLIConfiguration` is one small JSON file; per-repository state reuses the exact SQLite files every underlying component already owns (research.md §4) | PASS |
| 2.7 Dépôt analysé en lecture seule | All CLI-managed state (`config.json`, per-repository SQLite files, generated `docs/`) is written under `~/.repo-scanner/`, never under the analyzed repository root — stricter than `chat_api/server.py`'s existing default, which this feature does not use (research.md §4) | PASS |

No violations identified; Complexity Tracking is not needed for this feature.

## Project Structure

### Documentation (this feature)

```text
specs/019-cli-orchestrator/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/             # Phase 1 output (/speckit-plan command)
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── cli/                               # New package for this feature
│   ├── __init__.py
│   ├── main.py                        # Typer `app`; registers scan/index/serve/config
│   │                                  # (pyproject.toml [project.scripts] target)
│   ├── config.py                      # CLIConfiguration dataclass + load_config()/
│   │                                  # save_config() at ~/.repo-scanner/config.json
│   │                                  # (research.md §4), plus documented default
│   │                                  # LLM/embedding model constants
│   ├── paths.py                       # state_id(root), repo_state_dir(root), and the
│   │                                  # per-file paths under it (research.md §4)
│   ├── availability.py                # check_ai_dependencies(llm_engine,
│   │                                  # embedding_engine) -> None, raising the
│   │                                  # cli.errors types below (research.md §7, §9)
│   ├── server.py                      # start_local_server(...): chat_api.create_app +
│   │                                  # uvicorn.run, catching bind failures as
│   │                                  # ServerBindError (research.md §8, §9); shared
│   │                                  # by index_command.py and serve_command.py
│   ├── index_command.py               # run_index(...): full-pipeline orchestration
│   │                                  # (research.md §6), staged into a sibling
│   │                                  # directory and swapped in on success
│   │                                  # (research.md §10), reusing update_embeddings
│   │                                  # (reindex_pipeline.embeddings, 018)
│   ├── serve_command.py               # run_serve(...): loads RepositoryState, wires
│   │                                  # RepositoryWatcher (017) to
│   │                                  # IncrementalReindexPipeline (018) and the web
│   │                                  # server (research.md §8)
│   ├── config_command.py              # run_config(...): reads/writes CLIConfiguration
│   │                                  # (config.py) and reports installed-model
│   │                                  # candidates via listInstalledModels()
│   │                                  # (research.md §5)
│   └── errors.py                      # RepositoryNotFoundError, LocalModelUnavailableError,
│                                      # IndexNotFoundError, ServerBindError
│                                      # (research.md §9)
│
├── local_llm/
│   └── engine.py                      # + LocalLLMEngine.listInstalledModels()
│                                      # (research.md §5) — small, compatible extension
│
└── embedding_engine/
    ├── transport.py                   # + LocalEmbeddingTransport.list_models()
    │                                  # (research.md §5) — factors out the /api/tags
    │                                  # parsing already inlined in availability()
    └── engine.py                      # + EmbeddingEngine.listInstalledModels()

tests/
├── unit/
│   └── test_cli.py                    # config load/save, path/state-id derivation,
│                                      # availability-check error formatting, in isolation
├── integration/
│   └── test_cli.py                    # `index` end-to-end against a sample repository
│                                      # (Typer CliRunner), `serve`'s watcher hand-off,
│                                      # `config`'s save/show round-trip, missing-
│                                      # dependency and invalid-path error scenarios
│                                      # (US1-US4, all spec edge cases)
└── contract/
    └── test_cli_interface.py          # Verifies the `index`/`serve`/`config`/`scan`
                                      # command surface matches
                                      # contracts/cli-interface.md (exit codes, error
                                      # message categories, unchanged `scan` output)

pyproject.toml                         # [project.scripts]: repo-scanner =
                                      # "repo_scanner.cli:app" -> "cli.main:app"
                                      # (research.md §3)
```

**Structure Decision**: Single project layout, consistent with every prior
feature in this codebase. `cli` is added as its own top-level package under
`src/`, following the same one-package-per-feature convention already used
by `repo_watcher` (017) and `reindex_pipeline` (018) — it is the project's
outermost "Entry Point" layer (`docs/architecture.md` will gain a sixth
layer table entry for it), depending on every existing layer rather than
being depended on by any of them. `local_llm` and `embedding_engine` each
gain one small new method (research.md §5) rather than being forked or
reimplemented, matching the precedent 017/018 already set for
`DependencyGraph`/`RepositoryMetadataStore`. `repo_scanner/cli.py` (001)
is left entirely unchanged; only `pyproject.toml`'s console-script target
moves to the new package (research.md §3).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — this section is not applicable.
