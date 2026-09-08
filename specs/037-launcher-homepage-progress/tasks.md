---

description: "Task list for 037 launcher homepage with live run progress"
---

# Tasks: Launcher Homepage with Live Run Progress

**Input**: Design documents from `/specs/037-launcher-homepage-progress/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: Included. SC-003, SC-008, SC-009 and SC-010 are stated as verified
outcomes, and the feature brief asks specifically for a test that a long stage
keeps the display advancing and a test that a failed run ends in a clear
terminal state. Test tasks below are therefore not optional.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US4 from [spec.md](./spec.md)
- Exact file paths in every description

## Path Conventions

Single project. Python under `src/<package>/`, tests under `tests/{unit,integration,contract}/`.
Frontend under `frontend/src/`, with **tests flat in `frontend/tests/`** — not
co-located. The suite uses `fireEvent`; `@testing-library/user-event` is not a
dependency and must not be added.

**Baselines to beat: 808 pytest, 142 vitest.** Run pytest with
`--basetemp=<dir outside the repo> -p no:cacheprovider`.

House style: implementation comments cite their spec artifacts by name and
section (`data-model.md §2`, `research.md §7`, `contracts/hub-http-api.md`,
`spec FR-013`). Match it.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Make the new package and the second bundle buildable.

- [X] T001 Create the `src/hub_server/` package with `__init__.py` exporting `create_hub_app`, per the Structure Decision in plan.md
- [X] T002 Add `hub_server = ["assets/*"]` to `[tool.setuptools.package-data]` in `pyproject.toml` so the bundle and brand assets ship with the package
- [X] T003 [P] Create `frontend/vite.hub.config.ts` reusing the plugins and `styles.css` of `frontend/vite.config.ts`, with entry `src/hub.tsx`, `outDir` `../src/hub_server/assets`, `name` `HubUi`, `fileName` `hub-ui.js`, `emptyOutDir: false`, and the `style.css` → `hub-ui.css` rename (research.md §10)
- [X] T004 [P] Copy `favicon.ico` and the light/dark brand lockups from `docs/brand/` into `src/hub_server/assets/`, so the hub's assets travel with the package rather than being read from the repository (FR-043)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The progress channel, the hub's shared services, and the command
that starts it. Nothing in any user story can be built or tested until these
exist.

**⚠️ CRITICAL**: T005–T008 establish the FR-002 regression guarantee that every
later task relies on. Do them first and prove them before touching anything else.

### The progress channel and its guarantee

- [X] T005 Create `src/cli/__main__.py` containing only `from cli.main import app` and `app()`, so `python -m cli <command>` works (contracts/home-command.md; preferred over the console script, whose `exe` launcher breaks if the virtualenv is renamed)
- [X] T006 Create `src/cli/progress_stream.py`: read `CODEPEDIA_PROGRESS_STREAM` once at import, expose `emit(event: dict) -> None` that is a no-op when unset and otherwise writes the sentinel `@@CODEPEDIA_PROGRESS@@`, a single space, compact JSON and a newline to stdout **with an explicit flush**, plus a monotonic `seq` counter (contracts/run-progress-stream.md)
- [X] T007 [P] Unit test in `tests/unit/test_progress_stream.py`: emits nothing with the variable unset; emits one flushed single-line sentinel per event with it set; `seq` increases monotonically; a payload containing newlines or non-ASCII still yields exactly one line
- [X] T008 Integration test in `tests/integration/test_cli_output_unchanged.py` asserting that `index` and `serve` produce **no** `@@CODEPEDIA_PROGRESS@@` line with the variable unset, and that their existing printed lines are unchanged — this is FR-002's and SC-008's evidence and must fail if anyone makes emission unconditional

### Emitting from the pipeline

- [X] T009 Emit a `stage` event from `_stage.__enter__` and a `stage_end` event with `elapsedSeconds` from `_stage.__exit__` in `src/cli/index_command.py:170-180`, alongside the existing `typer.echo` — never replacing it (FR-016)
- [X] T010 Emit `stage` events for the two stages announced outside `_stage`: `VALIDATING` at `src/cli/index_command.py:184` and `CHECKING_MODELS` at `:239`
- [X] T011 [P] Emit an `items` event from `_echo_summary_progress` (`src/cli/index_command.py:126`) and from `_echo_embedding_progress` (`:132`), keeping both `typer.echo` calls; both call sites are already lock-protected so no new lock is needed (contracts/run-progress-stream.md)
- [X] T012 [P] Emit a `failover` event from the failover/backoff path in `src/cli/index_command.py` (`_echo_backoff`, `:135`) so an automatic provider switch is visible on the page as well as the terminal (FR-017, constitution 2.3)
- [X] T013 Emit a `failed` event carrying stage, message and every provider attempted where the pipeline raises `FailoverExhaustedError` / `LocalModelUnavailableError`, in `src/cli/index_command.py` (FR-022)
- [X] T014 Add an optional `on_progress: Callable | None = None` parameter to `IncrementalReindexPipeline.run` in `src/reindex_pipeline/`, defaulting to `None` so the pipeline stays silent by default (research.md §3)
- [X] T015 Wire a `catchup`-emitting callback into the pipeline construction in `src/cli/serve_command.py:78-92`, and emit `server_ready` beside the existing `startup_lines` output in `src/cli/server.py` (contracts/run-progress-stream.md)
- [X] T016 [P] Integration test in `tests/integration/test_progress_events.py`: with the variable set, a full `index` against `fake_engines` emits `stage` events in the exact `Stage` enum order, `items` events with rising `completed`, and a terminal event

### Hub shared services

- [X] T017 [P] Create `src/hub_server/progress_parse.py`: `parse_line(line) -> ProgressEvent | None`, returning `None` for any non-sentinel line and for a sentinel line whose JSON does not parse, and ignoring unknown `type` or unknown stage names (contracts/run-progress-stream.md, reader obligations 3–4)
- [X] T018 [P] Unit test in `tests/unit/test_progress_parse.py` covering each event type, a non-sentinel line, malformed JSON, an unknown type, an unknown stage, and a line with invalid UTF-8 decoded with `errors="replace"`
- [X] T019 [P] Create `src/hub_server/paths.py` with `validate_submitted_path(raw) -> Path`, applying the six ordered checks in `contracts/hub-http-api.md` (non-empty, expand `~`, resolve absolute, exists, is a directory, is readable, is not `~/.codepedia` nor inside it), raising a distinct message per failure (FR-009, FR-010, constitution 2.7)
- [X] T020 [P] Unit test in `tests/unit/test_hub_paths.py` for every rejection case plus the awkward accepted ones: spaces, non-ASCII, trailing separator, relative path, `..` segments, and a symlink resolving outside itself
- [X] T021 [P] Create `src/hub_server/security.py` with a FastAPI dependency accepting the token from the `X-Codepedia-Token` header or, **only** for the stream route, the `token` query parameter, delegating to `chat_api.security.require_api_token`'s `compare_digest` logic (research.md §9, FR-005)
- [X] T022 [P] Create `src/hub_server/run_log.py`: the `runs` schema from `data-model.md` §2 at `~/.codepedia/runs.sqlite`, with `append`, `close`, `prune` to the newest 50, `sweep_interrupted` for startup, and `recent` — every read wrapped so a missing, unreadable or older-schema database yields `[]` rather than raising (FR-026a–FR-026e)
- [X] T023 [P] Unit test in `tests/unit/test_run_log.py`: insert/close round-trip; pruning keeps exactly 50 and retains the newest; the startup sweep marks a NULL-outcome row `interrupted`; a corrupt file yields `[]` and no exception
- [X] T024 Create `src/hub_server/children.py`: free-port pick by binding port 0 and releasing it, `Popen([sys.executable, "-m", "cli", ...])` with `CODEPEDIA_PROGRESS_STREAM=1`, a reader thread that drains stdout for the child's whole life, forwards every non-sentinel line verbatim to the hub's stdout, terminate-then-kill, and staging-directory cleanup at `~/.codepedia/repos/<state_id>.staging-<child pid>` (research.md §7, §8)
- [X] T025 Integration test in `tests/integration/test_hub_children.py`: a child that prints a lot does not deadlock (proving the drain), a terminated child leaves no `.staging-<pid>` directory behind, and pre-existing residue the hub did not create is left untouched
- [X] T026 Create `src/hub_server/runs.py` with `RunState`, `StageState` and `ProviderSwitch` per `data-model.md` §1, the ten stages seeded from `cli.index_command.Stage` rather than re-declared, a lock, a `version` counter incremented on every mutation, and `apply(event)` mapping each `ProgressEvent` onto the state
- [X] T027 [P] Unit test in `tests/unit/test_run_state.py`: stage transitions mark the previous stage done; item counts land on the right stage; `outcome` is set exactly once and never returns to `None`; `version` increases on every mutation
- [X] T028 Create `src/hub_server/app.py` with `create_hub_app(...)`: `TrustedHostMiddleware` using `allowed_hosts_for`, the shared error shape from `contracts/hub-http-api.md`, and the `StaticFiles` mount at `/` with `html=True` **registered last** so API routes win
- [X] T029 Create `src/cli/home_command.py` with `run_home(host, port)` per `contracts/home-command.md` — run the run-log startup sweep, generate a token, build the app, print the startup lines, `uvicorn.run`, and terminate every child on shutdown (FR-007)
- [X] T030 Register `home` in `src/cli/main.py` with `--host` default `127.0.0.1` and `--port` default `8100`, and add `"home"` to `_DISCLOSURE_GATED_COMMANDS` at `src/cli/main.py:41-43` (constitution 2.1)
- [X] T031 [P] Contract test in `tests/contract/test_home_command.py`: default host and port, the startup lines' wording, the non-loopback warning, and `ServerBindError` on a taken port
- [X] T031a [P] Contract test in `tests/contract/test_hub_allowed_hosts.py` asserting a request carrying a forged `Host` header is rejected while `127.0.0.1`, `localhost` and `::1` are accepted (FR-006). `TrustedHostMiddleware` is the anti-DNS-rebinding half of the security posture `chat_api/security.py` documents, and a mis-registered middleware would fail silently without this test
- [X] T032 [P] Create `src/hub_server/assets/index.html` loading `hub-ui.css` and `hub-ui.js` as a plain script, with the favicon link and a `<title>`
- [X] T033 Create `frontend/src/hub.tsx` mounting a `HubPage` shell that reuses `lib/apiToken.ts` unchanged to read `?token=` into `sessionStorage`, and `lib/theme.ts` for pre-paint appearance (research.md §10)

**Checkpoint**: `codepedia home` starts, serves a themed empty page, and the CLI
is provably unchanged. User story work can begin.

---

## Phase 3: User Story 1 — Analyse a repository without opening a terminal (Priority: P1) 🎯 MVP

**Goal**: Type a path, press go, watch every stage and every item advance, stop
it if you want to.

**Independent Test**: Start the hub, enter a repository path, press the start
control, and confirm the display names the running stage and keeps changing —
without opening a terminal at any point.

### Tests for User Story 1

- [X] T034 [P] [US1] Contract test in `tests/contract/test_hub_runs_api.py` for `POST /api/runs`: `202` with the **resolved** path echoed back; `400 invalid_path` for each rejection with no process started and nothing written; `409 run_in_progress` naming the repository already running (FR-010, FR-012)
- [X] T035 [P] [US1] Contract test in `tests/contract/test_hub_run_stream.py`: the stream's first message is a complete snapshot; a later attach receives current state rather than an empty display; `?token=` is accepted here and a missing token is `401` (FR-018, FR-005)
- [X] T036 [P] [US1] Integration test in `tests/integration/test_hub_long_stage.py` proving the display keeps advancing through a stage that takes minutes — drive a stubbed child emitting `items` events slowly and assert the snapshot's `version` and `completed` rise throughout (SC-002, SC-011; asked for explicitly in the feature brief)
- [X] T037 [P] [US1] Integration test in `tests/integration/test_hub_cancel.py`: cancelling yields a terminal `cancelled` snapshot promptly, discards the staging directory, and leaves the hub ready to start another run (FR-012a, FR-026)
- [X] T037a [P] [US1] Integration test in `tests/integration/test_hub_repo_readonly.py` hashing every file in the analysed repository before and after a full analysis started from the hub, asserting no difference — and that every path written lies under `~/.codepedia/` (FR-011, SC-010, constitution 2.7). Analysis is the operation that writes most, so the read-only guarantee must be verified there and not only on Remove (T070)
- [X] T038 [P] [US1] Frontend test in `frontend/tests/IndexBar.test.tsx` using `fireEvent`: the field and button are keyboard reachable, submit is blocked while empty, and a rejection message renders
- [X] T039 [P] [US1] Frontend test in `frontend/tests/RunProgress.test.tsx`: all ten stages render in order with done/running/pending distinguished, item counts render for the two counting stages, and a terminal snapshot stops presenting the run as in progress

### Implementation for User Story 1

- [X] T040 [US1] Implement `POST /api/runs` in `src/hub_server/app.py`: validate via `hub_server.paths`, refuse a second run, launch the `index` child, insert the run-log row, return `202` (FR-009 to FR-013)
- [X] T041 [US1] Implement `GET /api/runs/current` returning a `RunState` snapshot or `{"run": null}` in `src/hub_server/app.py`
- [X] T042 [US1] Implement `GET /api/runs/stream` in `src/hub_server/app.py` as a `StreamingResponse` with `media_type="text/event-stream"`, sending a full snapshot on connect and on every `version` change polled at 250 ms, with a 15 s heartbeat, continuing to stream after a terminal state (research.md §4)
- [X] T043 [US1] Implement `POST /api/runs/current/cancel` and `POST /api/runs/current/dismiss` in `src/hub_server/app.py`, cancel terminating the child and cleaning its staging directory (FR-012a, FR-026)
- [X] T044 [P] [US1] Create `frontend/src/lib/hubApiClient.ts` wrapping the hub routes with the stored token
- [X] T045 [P] [US1] Create `frontend/src/lib/runStream.ts` wrapping `EventSource` with the token in the query string, reconnect handling, and a typed snapshot callback
- [X] T046 [P] [US1] Create `frontend/src/components/IndexBar.tsx` — path field, start control, keyboard reachable, rendering the server's rejection message verbatim (FR-008, FR-010)
- [X] T047 [US1] Create `frontend/src/components/RunProgress.tsx` — the ten stages with done/running/pending, item counts, provider switches, elapsed timings, and a Stop control (FR-014, FR-015, FR-017, FR-012a)
- [X] T048 [US1] Wire `IndexBar` and `RunProgress` into `frontend/src/hub.tsx` so the running analysis takes over the index control's area on the homepage, with no separate address for a run (FR-013a)

**Checkpoint**: A run can be started, watched item by item, and stopped, from the
browser alone.

---

## Phase 4: User Story 2 — Go straight back to a repository already analysed (Priority: P2)

**Goal**: The analyse history lists what has been analysed, and Open takes you
to its wiki — showing catch-up progress when there is any.

**Independent Test**: With one repository already analysed, open the homepage,
confirm it is listed, choose Open, and confirm the browser arrives at that
repository's documentation with no command typed.

### Tests for User Story 2

- [X] T049 [P] [US2] Unit test in `tests/unit/test_hub_history.py` against a fabricated state root: only `^[0-9a-f]{16}$` directories are listed, every `.staging-<pid>` residue is excluded, an unreadable entry is skipped without failing the listing, ordering is newest first, and `available` is false when the repository folder is gone (FR-030, FR-031, FR-031b, SC-005). Also assert that two different paths holding identical content yield two distinct entries, pinning FR-031a's deliberate absence of move detection so nobody later adds content-based matching unopposed
- [X] T050 [P] [US2] Contract test in `tests/contract/test_hub_repositories_api.py` for `GET /api/repositories` and `POST /api/repositories/{stateId}/open`, including the `502` classification split between FR-038, FR-038a and FR-037 (data-model.md §4)
- [X] T051 [P] [US2] Integration test in `tests/integration/test_hub_open_catchup.py`: a child emitting `catchup` events surfaces them as a run of `kind: "open"`, and a child emitting `server_ready` with no `catchup` produces **no** progress display and reaches the URL (FR-019, FR-020)
- [X] T052 [P] [US2] Frontend test in `frontend/tests/HistoryList.test.tsx`: rows render newest first, an unavailable row is visibly marked, and the empty state renders when nothing has been analysed
- [X] T052a [P] [US2] Performance test in `tests/integration/test_hub_history_scale.py` building 20 fabricated state directories and asserting `GET /api/repositories` completes within 2 seconds (SC-006). This is the bar research.md §6 relies on when it argues the derived scan needs no cache — the question clarification deferred to planning, and the test that settles it. If it fails, the cache decision is reopened, not the criterion

### Implementation for User Story 2

- [X] T053 [P] [US2] Create `src/hub_server/history.py` implementing the scan, filter, ordering and `available` check from `data-model.md` §3, reading `repositories.root_path` and `last_indexed_at` from each state directory's `repository-metadata.sqlite`
- [X] T054 [US2] Implement `GET /api/repositories` in `src/hub_server/app.py` (FR-028)
- [X] T055 [US2] Implement `POST /api/repositories/{stateId}/open` in `src/hub_server/app.py`: launch the `serve` child with an explicit `--host 127.0.0.1` and a free port, surface `catchup` progress, return the URL parsed from the child's startup line, and return an existing ready child's URL rather than launching a second (FR-035, FR-037)
- [X] T056 [US2] Implement the child-failure classification from `data-model.md` §4 in `src/hub_server/children.py`, separating `IndexNotFoundError` (FR-038), `LocalModelUnavailableError` (FR-038a), `ServerBindError` (FR-037) and a missing repository folder (FR-039)
- [X] T057 [P] [US2] Create `frontend/src/components/HistoryList.tsx` rendering rows beneath the index control, newest first, with the unavailable marker and an empty state (FR-028, FR-031b)
- [X] T058 [US2] Wire Open into `frontend/src/hub.tsx`: navigate on the returned URL, or follow the stream and navigate on `server_ready` when catch-up work started, and refresh the listing when a run completes without a manual reload (FR-032)

**Checkpoint**: The homepage is a launcher — analyse something new, or return to
something old.

---

## Phase 5: User Story 3 — A failing run says so, and says why (Priority: P3)

**Goal**: No run ever spins forever, and a failure names the stage, the cause,
the providers tried, and the fact that nothing was kept.

**Independent Test**: Start an analysis with a provider unreachable and confirm
the display reaches a stopped, clearly failed state naming the stage and cause,
rather than continuing to appear busy.

### Tests for User Story 3

- [X] T059 [P] [US3] Integration test in `tests/integration/test_hub_failed_run.py` proving a failed run ends in a clear terminal state: the stage is named, every provider attempted is named, the run stops being presented as in progress, and the hub accepts a new analysis afterwards (FR-021 to FR-026, SC-003, SC-004; asked for explicitly in the feature brief)
- [X] T060 [P] [US3] Integration test in `tests/integration/test_hub_terminal_states.py` covering the full SC-003 matrix — success, provider failure, invalid input, user cancellation, and a child killed with no `failed` event — asserting every case reaches a terminal state and that a non-zero exit is authoritative even when no event arrived (contracts/run-progress-stream.md, reader obligation 6)
- [X] T061 [P] [US3] Integration test in `tests/integration/test_hub_run_log_restart.py`: an outcome survives a hub restart, and a run whose hub died reads `interrupted` rather than still-running and does not block a new analysis (FR-026a, FR-026d, SC-013)
- [X] T062 [P] [US3] Test in `tests/integration/test_hub_config_untouched.py` asserting `~/.codepedia/config.json` is byte-identical after a provider-caused failure (FR-025)
- [X] T063 [P] [US3] Frontend test in `frontend/tests/RunOutcome.test.tsx`: a failed snapshot renders the stage, cause, providers, the explicit "no documentation was kept" statement, and a retry control; the outcome does not clear itself on a timer

### Implementation for User Story 3

- [X] T064 [US3] Implement terminal-state resolution in `src/hub_server/children.py` and `runs.py`: process exit is authoritative, the last `failed` event supplies the diagnosis, and a child killed before emitting anything still terminates the run (FR-021)
- [X] T065 [US3] Close the run-log row on every terminal outcome in `src/hub_server/app.py`, writing stage, message and providers attempted (FR-026a)
- [X] T066 [US3] Implement `GET /api/run-log` in `src/hub_server/app.py`, degrading to `{"runs": []}` with a `200` when the database is missing or unreadable (FR-026b, FR-026e)
- [X] T067 [P] [US3] Create `frontend/src/components/RunOutcome.tsx` rendering succeeded, failed and cancelled, with the explicit statement that nothing was kept, a retry that reuses the same path, and a dismiss control (FR-023, FR-024, FR-026, FR-027)
- [X] T068 [P] [US3] Create `frontend/src/components/RunLogList.tsx` showing recent run outcomes newest first on the homepage (FR-026b)

**Checkpoint**: Every ending is legible. This is the path most runs take on a
machine with an unreachable provider.

---

## Phase 6: User Story 4 — Inspect or forget a repository (Priority: P4)

**Goal**: A three-dots menu with exactly Properties, Open and Remove — and no
re-analyse action.

**Independent Test**: With two repositories listed, open a row's menu, read its
properties, remove it, and confirm the row and its stored analysis are gone
while the repository's own files are untouched.

**Depends on**: User Story 2 (the listing and `hub_server/history.py`).

### Tests for User Story 4

- [X] T069 [P] [US4] Contract test in `tests/contract/test_hub_repository_delete.py`: `204` deletes only `~/.codepedia/repos/<stateId>/`; `409 conflict` while that repository is being analysed or has a running child, with nothing deleted; `401` without a token (FR-041, FR-042, SC-009)
- [X] T070 [P] [US4] Integration test in `tests/integration/test_hub_remove_readonly.py` hashing every file in the analysed repository before and after a Remove and asserting no difference (FR-041, SC-010, constitution 2.7)
- [X] T071 [P] [US4] Frontend test in `frontend/tests/HistoryRowMenu.test.tsx` using `fireEvent`: the menu offers exactly Properties, Open and Remove and **no** re-analyse action; Properties shows the full path and last-analysed time; Remove requires a confirmation naming the repository, and declining deletes nothing

### Implementation for User Story 4

- [X] T072 [US4] Implement `DELETE /api/repositories/{stateId}` in `src/hub_server/app.py`, refusing entirely on conflict rather than deleting in part (FR-040 to FR-042)
- [X] T073 [P] [US4] Create `frontend/src/components/HistoryRowMenu.tsx` — the overflow menu, keyboard reachable, with Properties, Open, Remove, and a confirmation naming the repository (FR-033, FR-034, FR-040)
- [X] T074 [US4] Wire the menu into `frontend/src/components/HistoryList.tsx` and remove the row from the listing on a successful delete (FR-041)

**Checkpoint**: All four stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T075 [P] Add the three-state appearance control to the hub page by reusing `frontend/src/components/ThemeToggle.tsx` and `lib/theme.ts` unchanged, remembered for the homepage's own origin and applied before first paint, falling back to the operating system preference if storage is unavailable (FR-044a to FR-044c)
- [X] T076 [P] Frontend test in `frontend/tests/HubTheme.test.tsx`: all three states reachable, the current state identifiable, the choice applied without a reload, and the OS preference used when storage throws
- [X] T077 [P] Apply the shared visual tokens and the brand lockup at a size where the wordmark is legible, per the policy in `docs/brand/README.md`, in `frontend/src/hub.tsx` and `src/hub_server/assets/index.html` (FR-043)
- [X] T078 Rebuild both bundles — `npx vite build` and `npx vite build --config vite.hub.config.ts` — and confirm `git status` shows no unexpected drift in `src/doc_generator/assets/` or `src/hub_server/assets/`
- [X] T079 Verify a generated wiki still issues **zero** network requests when opened over `file://`, confirming this feature leaked nothing into it (FR-045)
- [X] T080 Browser-verify the homepage per [quickstart.md](./quickstart.md) — headless Chrome over CDP with `Emulation.setDeviceMetricsOverride`, letting the page settle before reading geometry; both appearances, narrow and wide, zero horizontal overflow, ≥ 4.5:1 text contrast (SC-012). Kill only your own `--user-data-dir` processes
- [X] T081 Run scenarios 1–12 in `specs/037-launcher-homepage-progress/quickstart.md` and record the results
- [X] T082 Confirm `tests/` is green at or above 808 pytest and `frontend/tests/` at or above 142 vitest, with no existing test modified — a test that had to change to accommodate this feature is an FR-002 failure, not a test that needed updating

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup. **Blocks every user story.**
  Within it, T005–T008 come first: they establish the FR-002 guarantee the rest
  of the feature is built on top of.
- **US1 (Phase 3)**: depends on Foundational.
- **US2 (Phase 4)**: depends on Foundational. Independent of US1 — the listing
  and Open do not need the index route — though both share `children.py`.
- **US3 (Phase 5)**: depends on Foundational, and is only *observable* once US1
  can start a run. Its terminal-state logic is what makes US1 trustworthy.
- **US4 (Phase 6)**: depends on **US2**, which owns `hub_server/history.py` and
  the listing the row menu attaches to.
- **Polish (Phase 7)**: depends on every story to be shipped.

### Within Each User Story

Tests first and failing, then parsing and state, then routes, then components,
then wiring. Nothing depends on a real successful index — every test uses the
`fake_engines` fixture pattern already in `tests/integration/test_cli.py:33-44`,
because on this machine no provider chain completes (research.md §11).

### Parallel Opportunities

- T003, T004 in Setup.
- T007, T011, T012 and, once T006 lands, T017–T023 — all different files.
- Every test task marked [P] within a story.
- US1 and US2 can be built concurrently once Foundational is done; US4 cannot
  start before US2.

---

## Parallel Example: User Story 1

```bash
# All US1 tests together, before implementation:
Task: "Contract test for POST /api/runs in tests/contract/test_hub_runs_api.py"
Task: "Contract test for the stream in tests/contract/test_hub_run_stream.py"
Task: "Long-stage advance test in tests/integration/test_hub_long_stage.py"
Task: "Cancel test in tests/integration/test_hub_cancel.py"
Task: "Repository-unchanged test in tests/integration/test_hub_repo_readonly.py"
Task: "IndexBar test in frontend/tests/IndexBar.test.tsx"
Task: "RunProgress test in frontend/tests/RunProgress.test.tsx"

# Then the independent client modules and components:
Task: "hubApiClient in frontend/src/lib/hubApiClient.ts"
Task: "runStream in frontend/src/lib/runStream.ts"
Task: "IndexBar in frontend/src/components/IndexBar.tsx"
```

---

## Implementation Strategy

### MVP (User Story 1 only)

1. Phase 1 Setup.
2. Phase 2 Foundational — with T005–T008 proven before anything else.
3. Phase 3 User Story 1.
4. **Stop and validate**: quickstart scenarios 1–5.

That MVP already replaces the terminal for the feature's headline job: type a
path, press go, watch it, stop it.

### Incremental Delivery

1. Setup + Foundational → `codepedia home` starts and serves a themed page.
2. **+ US1** → analyse and watch (MVP).
3. **+ US2** → the launcher becomes a launcher.
4. **+ US3** → every ending is legible. On a machine with an unreachable
   provider this is what makes US1 and US2 usable rather than baffling, so do
   not defer it far.
5. **+ US4** → housekeeping.

### Notes

- `[P]` means different files with no incomplete dependency.
- Commit after each task or logical group.
- Do **not** modify `~/.codepedia/config.json` at any point (FR-025).
- Do **not** add `@testing-library/user-event`; the suite uses `fireEvent`.
- The one known-flaky existing test —
  `tests/integration/test_cli.py::test_config_before_any_provider_reachable_still_reports_without_failing`
  — makes a live Groq call. Re-run before investigating.
