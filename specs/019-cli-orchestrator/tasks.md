# Tasks: Command-Line Interface Orchestrator

**Input**: Design documents from `specs/019-cli-orchestrator/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli-interface.md, quickstart.md

## Phase 1: Setup

**Goal:** Create the `cli` package skeleton every downstream task depends on.

**Independent test criteria:** `import cli` succeeds against the empty package.

- [X] T001 [P] Create `src/cli/__init__.py` (empty package marker) per the `Project Structure` in `plan.md`.

## Phase 2: Foundational

**Goal:** Build the shared configuration/state-path/error types, the two small engine extensions, the reusable availability check and web-server-start helpers, and the Typer `app` skeleton (with the carried-over `scan` command) every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

**Independent test criteria:** `cli.config.load_config()` returns documented defaults when no file exists and round-trips through `save_config()`; `cli.paths.state_id(root)` is stable and filesystem-safe; `repo-scanner scan <path>` (via `cli.main.app`) still matches `specs/001-local-repo-scanner/contracts/cli.md`.

- [X] T002 [P] Create `src/cli/config.py` with the `CLIConfiguration` dataclass (`llmModel`, `llmEndpointUrl`, `embeddingModel`, `embeddingEndpointUrl`), a documented default LLM model constant, and `load_config()`/`save_config()` reading/writing `~/.repo-scanner/config.json`, validating endpoint URLs via `local_llm.models.normalize_endpoint_url`/`embedding_engine.models.normalize_endpoint_url`, per `data-model.md` "CLIConfiguration" and `research.md` §4.
- [X] T003 [P] Create `src/cli/paths.py` with `state_id(root: Path) -> str` (first 16 hex chars of `sha256(stable_repository_id(root))`, via `repository_metadata.sqlite_store.stable_repository_id`), `repo_state_dir(root: Path) -> Path` (`~/.repo-scanner/repos/<state_id>/`), and named helpers for that directory's `repository-metadata.sqlite`, `dependency-graph.sqlite`, `vector-index.sqlite`, `vector-metadata.sqlite`, `doc-manifest.sqlite`, and `docs/`, per `data-model.md` "RepositoryState" and `research.md` §4.
- [X] T004 [P] Create `src/cli/errors.py` with `RepositoryNotFoundError`, `LocalModelUnavailableError`, `IndexNotFoundError`, and `ServerBindError`, each accepting a ready-to-print, actionable message, plus a `report_and_exit(err: Exception) -> NoReturn` helper that prints the message to stderr and raises `typer.Exit(code=1)`, per `research.md` §9.
- [X] T005 [P] Add `LocalLLMEngine.listInstalledModels(self) -> tuple[str, ...]` to `src/local_llm/engine.py`, a thin passthrough to the already-existing `self._transport.list_models()` (`local_llm/transport.py:73`), per `data-model.md` "Extension: LocalLLMEngine.listInstalledModels" and `research.md` §5.
- [X] T006 [P] Add `LocalEmbeddingTransport.list_models(self) -> tuple[str, ...]` to `src/embedding_engine/transport.py`, factoring out the `/api/tags` call and name extraction already inlined in `availability()` (`embedding_engine/transport.py:94-111`), and add `EmbeddingEngine.listInstalledModels(self) -> tuple[str, ...]` to `src/embedding_engine/engine.py` as a passthrough to it, per `data-model.md` "Extension: EmbeddingEngine.listInstalledModels" and `research.md` §5.
- [X] T007 Create `src/cli/availability.py` with `check_ai_dependencies(llm_engine: LocalLLMEngine, embedding_engine: EmbeddingEngine) -> None`, calling `checkAvailability()` on each and raising `LocalModelUnavailableError` (T004) using that status's own `message` (distinguishing service-unreachable vs. model-not-installed by construction, since `AvailabilityStatus`/`EmbeddingAvailabilityStatus` already word it that way) without checking the second engine if the first already failed, per `research.md` §7 and §9. Depends on T004.
- [X] T008 Create `src/cli/server.py` with `start_local_server(vector_index, embedding_engine, llm_engine, docs_root: Path, host: str, port: int) -> None`: builds the app via `chat_api.create_app(...)` (014), prints `f"Documentation wiki available at http://{host}:{port}/"`, and calls `uvicorn.run(app, host=host, port=port)`, catching a bind failure and raising `ServerBindError` (T004) naming `host:port`, per `research.md` §8 and §9. Depends on T004.
- [X] T009 Create `src/cli/main.py` with the Typer `app` and a `scan` command that thinly delegates to `repo_scanner.scanner.scan_repository` / `repo_scanner.output.serialize_scan_result`, matching `repo_scanner/cli.py`'s existing `_scan_command` exactly, per `research.md` §3 and `contracts/cli-interface.md`'s `scan` section.

**Checkpoint**: Foundation ready - user story implementation can now begin.

## Phase 3: User Story 1 - One command from a fresh repository to a browsable wiki 🎯 MVP

**Goal:** `repo-scanner index [PATH]` validates the repository, verifies local-model availability, runs the full pipeline (scan → parse/extract → persist → graph → docs → summarize → docs → embed) in the exact order `Harness.full_reindex` already validates — staged so a failed run never corrupts a prior successful index — then starts the local web server and prints its URL.

**Independent test criteria:** `quickstart.md` "Validate the one-command golden path" — running `index` against a valid sample repository with working local LLM/embedding services produces a populated `RepositoryState` and a browsable wiki at the printed URL (SC-001, SC-004).

- [X] T010 [P] [US1] Add a contract test in `tests/contract/test_cli_interface.py` (new file) asserting `cli.main.app` registers an `index` command accepting an optional `PATH` argument (defaulting to `"."`) and `--host`/`--port` options (defaulting to `127.0.0.1`/`8000`), per `contracts/cli-interface.md`'s `index` section. Depends on T009.
- [X] T011 [US1] Create `src/cli/index_command.py` with `run_index(repo_path: Path, *, config: CLIConfiguration) -> IndexRunResult` (`data-model.md`'s dataclass bundling `docsRoot`, `vectorIndex`, `embeddingEngine`, `llmEngine`, `watcher=None`): validates `repo_path` (raises `RepositoryNotFoundError`, T004, if missing/not a directory), builds `LocalLLMEngine`/`EmbeddingEngine` from `config` and calls `check_ai_dependencies` (T007); builds every stage's output into a fresh staging directory (`cli.paths.repo_state_dir(repo_path)` with a `.staging-<pid>` suffix, per `research.md` §10) rather than the final location, then runs `scan_repository` (001); per file, `extract_symbols` + `RepositoryMetadataStore.store_inventory(content_hash=compute_content_hash(...))` (002/003, 005); `DependencyGraph.build_from_inventories(...).save(...)` (004); `DocGenerator.generateRepositoryDocumentation(incremental=False)` (012, structure pass); `CodeSummaryPipeline.summarizeRepository(incremental=False)` (010); `DocGenerator.generateRepositoryDocumentation(incremental=False)` again (012, content pass); per file, `update_embeddings(...)` (018's helper, 006/007/009); printing the current stage via `typer.echo` before each step (`data-model.md`'s `Stage` enum). On success, removes any prior `repo_state_dir(repo_path)` and renames the staging directory onto it (`Path.replace`). On any exception, deletes the staging directory, leaves any prior state untouched, and re-raises. Per `research.md` §6 and §10 and `data-model.md`'s "State flow: `index`". Depends on T002, T003, T007.
- [X] T012 [US1] Wire the `index` Typer command in `src/cli/main.py`: loads `CLIConfiguration` (T002), calls `run_index` (T011), then `start_local_server` (T008) with its result, and catches `RepositoryNotFoundError`/`LocalModelUnavailableError`/`ServerBindError` (T004) via `report_and_exit`. Depends on T008, T009, T011.
- [X] T013 [US1] Add an integration test in `tests/integration/test_cli.py` (new file) calling `run_index` (T011) directly against a small real sample repository (temp dir fixture, matching other features' fixtures) with test-double LLM/embedding engines (matching `test_reindex_pipeline.py`'s `RecordingLLMEngine`/`FakeEmbeddingEngine`), asserting the repository's `RepositoryState` directory (T003) is created and populated (metadata/graph/vector/manifest sqlite files exist, `docs/` contains a home page and one page per module) after one call. Depends on T011.
- [X] T014 [US1] Add an integration test in `tests/integration/test_cli.py` asserting a second `run_index` call against the same repository path replaces the prior state with a fresh full run (spec.md's re-run edge case), and that `run_index` never calls `RepositoryWatcher`/`IncrementalReindexPipeline` (`index` is always a full run, not incremental). Depends on T013 (same file).
- [X] T015 [US1] Add an integration test in `tests/integration/test_cli.py` asserting that if `run_index` (T011) fails partway through a *second* run against an already-indexed repository (e.g., a test double `CodeSummaryPipeline`/`LocalLLMEngine` that raises once summarization starts), the repository's prior, successfully-indexed `RepositoryState` directory (T003) is left completely untouched — same files, same content — and no `.staging-*` directory remains afterward, per spec.md's anti-corruption requirement and `research.md` §10. Depends on T011, T014 (same file, sequential).
- [X] T016 [US1] Add an integration test in `tests/integration/test_cli.py`, using Typer's `CliRunner` with `cli.server.start_local_server`'s `uvicorn.run` call patched (so the process doesn't actually block), invoking `repo-scanner index <path>` and asserting the printed output includes the local URL and each pipeline stage name in order, per `quickstart.md` "Validate the one-command golden path" steps 2-3. Depends on T012.
- [X] T017 [US1] Add an integration test in `tests/integration/test_cli.py` that calls `start_local_server` (T008) for real — no `uvicorn.run` patching — on an ephemeral port in a background thread, against a repository already indexed by `run_index` (T013), then issues an HTTP GET against the printed local URL and asserts the response contains the wiki's home page content, per SC-004. Depends on T008, T013.
- [X] T018 [US1] Add an integration test in `tests/integration/test_cli.py` asserting that when `~/.repo-scanner/config.json` does not exist, `run_index` (T011) still succeeds using the documented default LLM/embedding models (T002) and still calls `check_ai_dependencies` (T007) against those defaults, per spec.md's "no configuration has ever been set" edge case. Depends on T002, T011.
- [X] T019 [US1] Add an integration test in `tests/integration/test_cli.py` asserting that `run_index` (T011) against a repository containing no recognizable source files completes successfully (no error), and that the resulting `docs/` output reflects an effectively empty repository rather than the command failing, per spec.md's "no recognizable source files" edge case. Depends on T011.

**Checkpoint**: US1 is functional and independently testable — the pipeline's core one-command flow works end to end, is verified against the reference `Harness` ordering, never corrupts a prior successful index on failure, and is browsable over real HTTP. This is the MVP.

## Phase 4: User Story 2 - Resuming work with live updates

**Goal:** `repo-scanner serve [PATH]` refuses to run against a never-indexed repository, otherwise loads the existing `RepositoryState`, wires the repository watcher (017) to the incremental reindexing pipeline (018), and starts the same local web server so file changes are reflected without any further command.

**Independent test criteria:** `quickstart.md` "Validate resuming with the watcher" — after `index` has run once, `serve` makes the wiki immediately browsable, and a subsequent file edit is reflected without a manual command (SC-005, SC-007); `serve` against a never-indexed repository fails clearly instead of starting an empty server.

- [X] T020 [P] [US2] Add a contract test in `tests/contract/test_cli_interface.py` asserting `cli.main.app` registers a `serve` command with the same `PATH`/`--host`/`--port` shape as `index`, per `contracts/cli-interface.md`'s `serve` section. Depends on T009.
- [X] T021 [US2] Create `src/cli/serve_command.py` with `run_serve(repo_path: Path, *, config: CLIConfiguration) -> IndexRunResult` (T011's result shape, with `watcher` populated): validates `repo_path` (T004) and availability (T007) as `run_index` does; calls `RepositoryMetadataStore.load_repository_record(repo_path)` and raises `IndexNotFoundError` (T004) if no record exists, directing the developer to run `index` first; otherwise loads the existing `DependencyGraph` (`DependencyGraph.load(graph_db_path, graph_id=state_id)`), `VectorIndex`, `DocPageManifestStore`, and `DocGenerator`/`CodeSummaryPipeline` from `cli.paths` (T003); builds an `IncrementalReindexPipeline` (018); constructs a `RepositoryWatcher` (017) with `on_batch=pipeline.run` and calls `watcher.start()`; returns the result with the started `watcher` for the caller to stop on shutdown, per `research.md` §8 and `data-model.md`'s "State flow: `serve`". Depends on T002, T003, T007.
- [X] T022 [US2] Wire the `serve` Typer command in `src/cli/main.py`: loads `CLIConfiguration`, calls `run_serve` (T021), then `start_local_server` (T008) inside a `try/finally` that calls `watcher.stop()`, and catches `RepositoryNotFoundError`/`LocalModelUnavailableError`/`IndexNotFoundError`/`ServerBindError` via `report_and_exit`. Depends on T008, T009, T021.
- [X] T023 [US2] Add an integration test in `tests/integration/test_cli.py`: `run_index` a sample repository (T011), then `run_serve` it (T021), then call the returned watcher's configured `on_batch` (the `IncrementalReindexPipeline.run`) directly with a `ChangeBatch` for one modified file, asserting the file's stored summary/embedding/documentation page reflect the change afterward — confirming the watcher-to-pipeline wiring is correct, per `quickstart.md` "Validate resuming with the watcher" steps 3-5. Depends on T021.
- [X] T024 [US2] Add an integration test in `tests/integration/test_cli.py` asserting `run_serve` against a repository path with no prior `run_index` call raises `IndexNotFoundError`, and that (via `CliRunner` with `uvicorn.run` patched) `repo-scanner serve <never-indexed-path>` exits non-zero with a message directing the developer to run `index` first, without `uvicorn.run` having been called. Depends on T022 (same file as T023, sequential).

**Checkpoint**: US1 and US2 work together — a repository can be indexed once and then resumed with live updates, and `serve` refuses to run without a prior index.

## Phase 5: User Story 3 - Choosing local models

**Goal:** `repo-scanner config` lets a developer view and change the LLM/embedding model `index`/`serve` use, showing installed-model candidates and warning (without failing) when a selected model isn't installed yet.

**Independent test criteria:** `quickstart.md` "Validate model configuration" — a saved choice persists across commands and is reflected by a subsequent `index`/`serve` run without specifying it again (SC-006).

- [X] T025 [P] [US3] Add a contract test in `tests/contract/test_cli_interface.py` asserting `cli.main.app` registers a `config` command accepting `--llm-model`, `--llm-endpoint`, `--embedding-model`, `--embedding-endpoint`, and `--show`, all optional, per `contracts/cli-interface.md`'s `config` section. Depends on T009.
- [X] T026 [US3] Create `src/cli/config_command.py` with a `run_config(*, llm_model, llm_endpoint, embedding_model, embedding_endpoint, show) -> None`: with no model/endpoint flags (or `--show`), prints the current `CLIConfiguration` (T002) plus `checkAvailability()`/`listInstalledModels()` (T005, T006) for the configured LLM and embedding models and any other installed models found at each endpoint; with one or more model/endpoint flags, validates endpoint URLs, saves the resulting `CLIConfiguration` via `save_config` (T002), and prints a warning (not a failure) for any newly set model absent from that endpoint's `listInstalledModels()` result, per `research.md` §5 and `data-model.md`'s "State flow: `config`". Depends on T002, T005, T006.
- [X] T027 [US3] Wire the `config` Typer command in `src/cli/main.py`, mapping its options to `run_config` (T026) and catching endpoint-validation failures via `report_and_exit` (T004). Depends on T009, T026.
- [X] T028 [P] [US3] Add a unit test in `tests/unit/test_cli.py` (new file) for `cli.config.load_config`/`save_config` (T002): a missing config file yields the documented defaults; saving then loading returns the same values; an invalid endpoint URL raises before anything is written. Depends on T002.
- [X] T029 [US3] Add an integration test in `tests/integration/test_cli.py`, using `CliRunner` with `LocalLLMEngine`/`EmbeddingEngine` availability calls patched: `config` with no flags prints the current configuration and availability; `config --llm-model <installed>` saves silently; `config --embedding-model <not-installed>` saves and prints a warning (exit code `0`); `config --llm-endpoint <invalid>` fails validation and saves nothing (exit code `1`). Depends on T027.
- [X] T030 [US3] Add an integration test in `tests/integration/test_cli.py` asserting that after `config --llm-model <X>` saves successfully, a subsequent `run_index` (T011) call builds its `LocalLLMEngine` with `modelName == "<X>"` (no explicit override needed), per `quickstart.md` "Validate model configuration" step 8. Depends on T011, T029 (same file, sequential).
- [X] T031 [US3] Add an integration test in `tests/integration/test_cli.py`, with both `LocalLLMEngine.checkAvailability` and `EmbeddingEngine.checkAvailability` stubbed to return `serviceReachable=False`, asserting `repo-scanner config` (no flags) still prints the developer's current/intended configuration without failing, showing every candidate model as currently unavailable rather than raising or pretending the configuration is fully usable, per spec.md's "configuration command run before any local LLM or embedding provider is reachable" edge case. Depends on T027 (same file, sequential after T030).

**Checkpoint**: All three primary user stories are independently functional together — a developer can index, resume with live updates, and choose their local models.

## Phase 6: User Story 4 - Actionable errors when a dependency is missing

**Goal:** Every command that can fail on a missing dependency (invalid repository path, unreachable local LLM/embedding service, model not installed, server bind failure) reports a distinct, actionable message and a non-zero exit — never a raw traceback, never a silent failure — across `index` and `serve` alike.

**Independent test criteria:** `quickstart.md` "Validate missing-dependency errors" and "Validate invalid-repository errors" — each of the four failure categories in `contracts/cli-interface.md`'s "Error message expectations" table is produced with distinguishing wording and no partial output (SC-002, SC-003).

- [X] T032 [US4] Add an integration test in `tests/integration/test_cli.py` asserting `repo-scanner index <path-that-does-not-exist>` exits `1`, names the given path and that it doesn't exist, and creates no `~/.repo-scanner/repos/<state_id>/` directory (staging or final) as a side effect. Depends on T012.
- [X] T033 [US4] Add an integration test in `tests/integration/test_cli.py`, with a stub `LocalLLMEngine.checkAvailability` returning `serviceReachable=False`, asserting both `repo-scanner index` and `repo-scanner serve` exit `1` with a message naming the configured endpoint and stating the local service needs to be started, and that neither `scan_repository` nor any AI-dependent call happens first. Depends on T012, T022 (same file as T032, sequential).
- [X] T034 [US4] Add an integration test in `tests/integration/test_cli.py`, with a stub `LocalLLMEngine.checkAvailability` returning `serviceReachable=True, modelInstalled=False`, asserting both commands exit `1` with a message naming the specific missing model, worded distinctly from T033's service-unreachable message. Depends on T012, T022 (same file as T033, sequential).
- [X] T035 [US4] Add an integration test in `tests/integration/test_cli.py`, patching `cli.server`'s `uvicorn.run` to raise `OSError` (simulating a port already in use), asserting `repo-scanner serve` (after a successful prior `index`) exits `1` with a message naming `host:port` and that it's already in use, raised as `ServerBindError` (T004/T008) rather than propagating a raw `OSError`. Depends on T008, T022 (same file as T034, sequential).
- [X] T036 [US4] Add an integration test in `tests/integration/test_cli.py` asserting none of T032-T035's failure scenarios produce a Python traceback in `CliRunner`'s captured output — every one exits through `report_and_exit` (T004) with only the formatted message. Depends on T032, T033, T034, T035 (same file, sequential, last).

**Checkpoint**: All four user stories are independently functional together — indexing, resuming, configuring, and every missing-dependency failure path all behave as the spec requires.

## Phase 7: Polish & Cross-Cutting Concerns

**Goal:** Retarget the console-script entry point, finalize the package's public exports, keep the project's living documentation in sync (per this project's standing rule that `README.md`, `docs/architecture.md`, `docs/stack.md`, and `docs/diagrams/` are updated alongside every implementation), and validate the full quickstart end to end.

**Independent test criteria:** Every `quickstart.md` scenario passes against the finished implementation, including the `scan` regression check; `pip install -e .` followed by `repo-scanner --help` lists `scan`, `index`, `serve`, and `config`.

- [X] T037 Update `pyproject.toml`'s `[project.scripts]` from `repo-scanner = "repo_scanner.cli:app"` to `repo-scanner = "cli.main:app"`, per `research.md` §3. Depends on T009.
- [X] T038 [P] Update `src/cli/__init__.py` to export `CLIConfiguration`, `run_index`, `run_serve`, and `run_config` via `__all__`, matching sibling packages' convention (e.g. `src/repo_watcher/__init__.py`). Depends on T002, T011, T021, T026.
- [X] T039 [P] Update `docs/architecture.md`: add a sixth "Entry Point" layer table entry for `cli` (§"System layers"), update "Runtime & deployment model" to name `repo-scanner index`/`serve` as the concrete processes it previously described only abstractly, and update "Current status by layer" to include this feature. Depends on T012, T022, T027.
- [X] T040 [P] Update `docs/stack.md`'s "CLI" section to note the console-script target now points at `cli/main.py` (T037) and that no new dependency was introduced (Typer reused, research.md §1). Depends on T037.
- [X] T041 [P] Update `docs/diagrams/class-diagram.md` and `docs/diagrams/use-case-diagram.md` to include the `cli` package's classes/relationships and the `index`/`serve`/`config` use cases. Depends on T012, T022, T027.
- [X] T042 [P] Update `docs/diagrams/sequence-diagrams/00-overview.md`, `01-full-indexing.md`, and `02-incremental-reindex.md` to note they are now triggered concretely via `repo-scanner index`/`repo-scanner serve` rather than an unspecified caller. Depends on T012, T022.
- [X] T043 [P] Update `README.md`'s "Running it" section to replace the "not yet wired into a single top-level command" language with the actual `repo-scanner index`/`serve`/`config`/`scan` usage, and confirm no `.gitignore` addition is needed (CLI state lives under `~/.repo-scanner/`, outside the repository, so the existing blanket `*.sqlite` rule and repo-scoped ignores remain sufficient — document this explicitly rather than silently skipping the check). Depends on T012, T022, T027.
- [X] T044 Validate the end-to-end flow against `specs/019-cli-orchestrator/quickstart.md` (golden path, missing-dependency errors, invalid-repository errors, resuming with the watcher, model configuration, and the `scan` regression check) and fix any mismatches. Depends on every prior task.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories.
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion; can then proceed in parallel or in priority order (US1 → US2 → US3 → US4). US2 and US4 both extend behavior US1 first establishes (US2 reuses `run_index`'s result shape and `start_local_server`; US4 tests failure paths both `index` and `serve` already implement), so US1 going first is strongly recommended even though the phases are nominally independent.
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### Task-Level Dependencies

- `T001` has no dependencies.
- `T002`, `T003`, `T004`, `T005`, `T006` each depend only on `T001`/nothing and touch different files, so all five can run in parallel.
- `T007` depends on `T004` (different file, `availability.py`, so parallel-eligible with `T005`/`T006`/`T008`/`T009` once `T004` lands). `T008` depends on `T004` (different file, `server.py`). `T009` depends on nothing new (touches `main.py`) — parallel-eligible with `T002`-`T008`.
- `T010` depends on `T009` (different file, parallel-eligible with `T011`). `T011` depends on `T002`, `T003`, `T007` (new file, `index_command.py`). `T012` depends on `T008`, `T009`, `T011` (touches `main.py`, same file as `T009`; sequential after it). `T013` depends on `T011`. `T014` depends on `T013` (same file, sequential). `T015` depends on `T011`, `T014` (same file, sequential). `T016` depends on `T012` (same file, sequential after `T015`). `T017` depends on `T008`, `T013` (same file, sequential after `T016`). `T018` depends on `T002`, `T011` (same file, sequential after `T017`). `T019` depends on `T011` (same file, sequential after `T018`).
- `T020` depends on `T009` (different file than `T011`-`T019`, parallel-eligible with `T010`'s authoring, though both land in the same contract-test file). `T021` depends on `T002`, `T003`, `T007` (new file, `serve_command.py` — parallel-eligible with `T011`/`T026` since none share a file). `T022` depends on `T008`, `T009`, `T021` (touches `main.py`, sequential after `T012`). `T023` depends on `T021`. `T024` depends on `T022` (same file as `T023`, sequential).
- `T025` depends on `T009` (same contract-test file as `T010`/`T020`, sequential in practice). `T026` depends on `T002`, `T005`, `T006` (new file, `config_command.py`). `T027` depends on `T009`, `T026` (touches `main.py`, sequential after `T022`). `T028` depends on `T002` (different file, parallel-eligible with everything except other `config.py` edits). `T029` depends on `T027`. `T030` depends on `T011`, `T029` (same file as `T029`, sequential). `T031` depends on `T027` (same file as `T030`, sequential, last in this phase).
- `T032` depends on `T012` (first task in this phase to touch `tests/integration/test_cli.py`'s US4 section). `T033` depends on `T012`, `T022` (same file as `T032`, sequential). `T034` depends on `T012`, `T022` (same file as `T033`, sequential). `T035` depends on `T008`, `T022` (same file as `T034`, sequential). `T036` depends on `T032`-`T035` (same file, sequential, last).
- `T037` depends on `T009`. `T038` depends on `T002`, `T011`, `T021`, `T026`. `T039`-`T043` each depend on the commands they document existing (`T012`, `T022`, `T027`, `T037`) but touch different documentation files from each other, so all five can run in parallel once their prerequisites land. `T044` depends on every prior task.

### Parallel Opportunities

- `T002`/`T003`/`T004`/`T005`/`T006`/`T009` (Foundational, first wave).
- `T007`/`T008` (Foundational, second wave, once `T004` lands).
- `T011`/`T021`/`T026` (US1/US2/US3 core implementation, different files, once Foundational completes).
- `T028` (US3 unit test) alongside any of the above.
- `T039`/`T040`/`T041`/`T042`/`T043` (Polish documentation updates, different files).

**Note on `[P]` and shared test files**: Within `tests/integration/test_cli.py`, once a phase's tasks begin landing in that file, later tasks in the *same* phase that also touch it (e.g. `T014`-`T019`, `T023`-`T024`, `T029`-`T031`, `T032`-`T036`) are applied sequentially and are *not* marked `[P]`, even where their assertions are logically independent — only the first task to touch a given test file within a phase, or a task in a different file entirely, carries `[P]`.

## Parallel Execution Examples

### Foundational, first wave

```text
Task: T002 -> CLIConfiguration + load_config/save_config in src/cli/config.py
Task: T003 -> state_id/repo_state_dir path helpers in src/cli/paths.py
Task: T004 -> CLI error types + report_and_exit in src/cli/errors.py
Task: T005 -> LocalLLMEngine.listInstalledModels in src/local_llm/engine.py
Task: T006 -> LocalEmbeddingTransport.list_models + EmbeddingEngine.listInstalledModels
Task: T009 -> Typer app + scan command in src/cli/main.py
```

### After Foundational completes (core command implementations)

```text
Task: T011 -> run_index pipeline orchestration (staged) in src/cli/index_command.py
Task: T021 -> run_serve watcher/reindex wiring in src/cli/serve_command.py
Task: T026 -> run_config read/write in src/cli/config_command.py
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories).
3. Complete Phase 3: User Story 1 - `repo-scanner index` takes a fresh repository to a browsable local wiki in one command, without ever corrupting a prior successful index if a re-run fails.
4. **STOP and VALIDATE**: Run `quickstart.md` "Validate the one-command golden path."

### Incremental Delivery

1. Setup + Foundational → configuration, state paths, error types, the two engine extensions, the availability/server helpers, and the `scan`-carrying `app` skeleton all exist.
2. Add US1 (`index`) → test independently → MVP: one command produces a browsable wiki, safely (staged, HTTP-verified, covering the no-config and empty-repository edge cases).
3. Add US2 (`serve`) → test independently — resuming an indexed repository with live updates via the watcher.
4. Add US3 (`config`) → test independently — choosing and persisting local models across runs, including when no provider is reachable yet.
5. Add US4 (actionable errors) → test independently — every missing-dependency path across `index`/`serve` fails clearly, deliberately last since it verifies behavior US1/US2 already built rather than adding a new command.
6. Polish: console-script retarget, public exports, documentation sync, full quickstart validation.

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together.
2. Once Foundational is done:
   - Developer A: User Story 1 (`index`)
   - Developer B: User Story 3 (`config`) — has no dependency on US1/US2's own files
   - Developer C: starts US4's test scaffolding once US1's `T012` lands
3. User Story 2 depends on US1's `run_index`/`start_local_server` shape existing, so it is best picked up by whoever finishes US1, or started once `T008`/`T011` (not all of US1) have landed.
