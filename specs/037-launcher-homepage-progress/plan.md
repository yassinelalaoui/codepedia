# Implementation Plan: Launcher Homepage with Live Run Progress

**Branch**: `037-launcher-homepage-progress` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/037-launcher-homepage-progress/spec.md`

## Summary

Add a `codepedia home` command that starts a loopback hub server owning `/`. The
hub's page carries an index bar, a live progress display for the current run,
and an analyse history reconstructed by scanning `~/.codepedia/repos/`.

The hub never runs the pipeline itself. It launches the real CLI as a child
process — `index` to analyse, `serve` to open — and reads structured progress
events from that child's stdout, emitted only when the hub sets
`CODEPEDIA_PROGRESS_STREAM=1`. That single decision delivers three requirements
at once: cancellation becomes `terminate()` rather than an uninterruptible
thread (FR-012a), a pipeline crash cannot take the hub down, and the CLI's own
output is provably unchanged because the emitting call is a no-op without the
variable (FR-002). Progress reaches the browser over server-sent events, the
same construction chat already uses.

`serve` and `chat_api.create_app` are not modified. The only edits outside the
new package are additive and environment-gated.

## Technical Context

**Language/Version**: Python 3.13 (`.venv`; must stay 3.11–3.13 — Pydantic
schema generation hangs on 3.14). TypeScript 5.6 / React 18 for the page.

**Primary Dependencies**: No new ones. FastAPI, uvicorn, Starlette
`StreamingResponse`, Typer, stdlib `subprocess`/`sqlite3`/`threading` on the
Python side; Vite 5, React 18, Tailwind v4 on the frontend side — all already in
`pyproject.toml` and `frontend/package.json`.

**Storage**: A new `~/.codepedia/runs.sqlite` for the run log (research §5). The
history listing is derived, not stored (research §6).

**Testing**: `pytest` (`tests/unit`, `tests/integration`, `tests/contract`) and
`vitest` (`frontend/tests/`, flat). Baseline to beat: **808 pytest / 142
vitest**. Run pytest with `--basetemp=<dir outside the repo> -p no:cacheprovider`
to avoid ~17 spurious `PermissionError`s on this machine.

**Target Platform**: Windows 11 primary, loopback only. Path handling and
process termination are the two places where platform differences bite.

**Project Type**: Local CLI plus a loopback web server with a bundled React
page — the same shape as the existing `serve`.

**Performance Goals**: Progress visible within 2 s of each item (SC-002);
history listed within 2 s at 20 repositories (SC-006); a visible change at least
once a minute in a long stage (SC-011).

**Constraints**: Bind `127.0.0.1` by default. Never write inside an analysed
repository. Introduce no runtime fetch into a generated wiki. Do not modify
`~/.codepedia/config.json`.

**Scale/Scope**: One user, one machine, one analysis at a time, tens of
repositories in the history, several servers open at once.

## Constitution Check

*GATE: passed before Phase 0, re-checked after Phase 1 design. Constitution
v3.0.0.*

| Principle | Applies how | Verdict |
|---|---|---|
| **2.1** Remote engines by default, local on explicit choice; disclosure must be clear | The hub starts analyses, so the disclosure gate must not be bypassed. It is not: the hub launches the real `index`/`serve` commands, and `cli.main`'s callback runs `ensure_disclosure_acknowledged` for exactly those (`main.py:41-43`). Going through the CLI inherits the gate rather than reimplementing it — a direct `run_index` call would have skipped it. | **PASS** |
| **2.2** Zero inbound network exposure by default | The hub binds `127.0.0.1` unless the user passes `--host` (FR-003), reuses `allowed_hosts_for`/`is_loopback_host` from `chat_api.security`, and prints the same non-loopback warning `serve` prints. Child servers are launched with `--host 127.0.0.1` explicitly. | **PASS** |
| **2.3** Automatic failover only inside a configured chain, and never silent | The hub only *reports*. FR-017 surfaces provider switches in the run display and FR-022 names every provider attempted in a failure — which strengthens 2.3's visibility requirement rather than straining it. FR-025 forbids the hub changing provider configuration. | **PASS** |
| **2.4** AI answers traceable to source | Untouched. This feature generates no AI content; it starts the processes that do. | **N/A** |
| **2.5** Incremental re-indexing, never full re-analysis on every change | The reason the row menu has no re-analyse action. Open goes through `serve`, whose watcher runs `compute_catchup_batch` and reprocesses only what changed (FR-036). A full rebuild happens only when the user deliberately submits a path to the index bar (FR-013). | **PASS** |
| **2.6** Minimal infrastructure, embedded local storage only | One new SQLite file under `~/.codepedia/` for the run log. 2.6 forbids an external database server, a broker or cloud storage and expressly permits SQLite on disk, so this is inside the principle, not an exception to it (research §5). No cache is introduced in front of the history scan (research §6). No daemon, no queue, no broker. | **PASS** |
| **2.7** Analysed repository is read-only | The new surface is an untrusted path from a browser. FR-009 validates it before any work starts, including refusing the tool's own state location. All writes stay under `~/.codepedia/`, enforced downstream by `_ensure_output_root_is_separate` (`doc_generator/generator.py:739`), which is unchanged. FR-041's Remove deletes only `~/.codepedia/repos/<state_id>/`. SC-010 verifies the repository byte-for-byte. | **PASS** |
| **3.3** Conformance review before implementation | This table, re-checked after Phase 1. | **PASS** |

**No violations.** The Complexity Tracking table below is therefore empty, which
is the intended outcome — no principle needed an exception.

Two points recorded so a reviewer does not have to re-derive them:

- **The run log is new stored state**, chosen by the owner over an in-memory
  alternative. It is compliant with 2.6 as argued above, but it is the single
  place this feature adds durable state, so `data-model.md` specifies its
  schema, its bound, and its pruning explicitly.
- **The hub may fetch; the wiki still may not.** The `file://` zero-fetch rule
  binds generated wikis, not a loopback-served page. FR-045 and research §10
  keep the leniency from leaking: the two bundles are separate and the hub build
  never writes into `src/doc_generator/assets/`.

## Project Structure

### Documentation (this feature)

```text
specs/037-launcher-homepage-progress/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── hub-http-api.md
│   ├── run-progress-stream.md
│   └── home-command.md
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit-tasks output — NOT created here
```

### Source Code (repository root)

```text
src/
├── hub_server/                 # NEW package — everything the hub owns
│   ├── __init__.py
│   ├── app.py                  # create_hub_app(): routes, SSE, static mount
│   ├── security.py             # token-from-header-or-query dependency
│   ├── runs.py                 # RunState, the in-memory current run, snapshots
│   ├── run_log.py              # ~/.codepedia/runs.sqlite: append, prune, sweep
│   ├── history.py              # scan ~/.codepedia/repos/, filter, sort, remove
│   ├── children.py             # Popen supervision, port pick, stdout drain
│   ├── progress_parse.py       # sentinel line -> ProgressEvent
│   ├── paths.py                # repo_path validation for untrusted input
│   └── assets/                 # index.html, hub-ui.js, hub-ui.css, brand, favicon
├── cli/
│   ├── __main__.py             # NEW — enables `python -m cli`, purely additive
│   ├── home_command.py         # NEW — run_home(): builds app, starts uvicorn
│   ├── progress_stream.py      # NEW — env-gated sentinel emitter, no-op by default
│   ├── main.py                 # EDIT — register `home`; add to disclosure gate set
│   ├── index_command.py        # EDIT — emit alongside existing typer.echo calls
│   └── serve_command.py        # EDIT — pass on_progress into the reindex pipeline
├── reindex_pipeline/
│   └── ...                     # EDIT — optional on_progress on run(), default None
└── doc_generator/              # UNTOUCHED

frontend/
├── vite.hub.config.ts          # NEW — second lib build, entry src/hub.tsx
├── src/
│   ├── hub.tsx                 # NEW — hub page entry
│   ├── components/
│   │   ├── IndexBar.tsx        # NEW
│   │   ├── RunProgress.tsx     # NEW
│   │   ├── HistoryList.tsx     # NEW
│   │   ├── HistoryRowMenu.tsx  # NEW
│   │   ├── RunOutcome.tsx      # NEW
│   │   ├── RunLogList.tsx      # NEW
│   │   └── ThemeToggle.tsx     # REUSED as-is
│   ├── lib/
│   │   ├── hubApiClient.ts     # NEW
│   │   ├── runStream.ts        # NEW — EventSource wrapper
│   │   ├── apiToken.ts         # REUSED as-is
│   │   └── theme.ts            # REUSED as-is
│   └── styles.css              # REUSED — shared theme tokens
└── tests/                      # flat; new hub specs land here

tests/
├── unit/                       # progress parsing, history filtering, run log pruning
├── integration/                # hub routes, child supervision, cancel, CLI regression
└── contract/                   # the three contracts under contracts/
```

**Structure Decision**: A new top-level `src/hub_server/` package, parallel to
`src/chat_api/`. `pyproject.toml` discovers packages under `src/` automatically,
so only a `package-data` entry (`hub_server = ["assets/*"]`) needs adding. The
hub is kept out of `chat_api` because the two share no routes and no state, and
because FR-002 is easiest to keep true when `create_app` is not touched at all.

The frontend stays one project with two builds. The hub's bundle shares
`styles.css`, `ThemeToggle.tsx`, `theme.ts` and `apiToken.ts` with the wiki —
that sharing is what makes FR-043 and FR-044a reuse rather than reimplementation
— but emits to `src/hub_server/assets/`, never to `src/doc_generator/assets/`.

## Implementation Sequence

Ordered so each step is independently verifiable, and so the CLI-regression
guarantee is proven before anything depends on it.

1. **`cli/progress_stream.py` + `cli/__main__.py`.** The env-gated emitter and
   the module entry point. Prove first that with the variable unset, `index` and
   `serve` output is byte-identical to today — this is FR-002's evidence and
   everything else builds on it.
2. **Emit sites.** `_stage.__enter__`, the two direct stage echoes, the two item
   callbacks, the failover hook (research §2 table); and the new optional
   `on_progress` through `IncrementalReindexPipeline` wired in `serve_command`
   (research §3).
3. **`hub_server/progress_parse.py`.** Pure function, sentinel line to event.
   Unit-testable with no process at all.
4. **`hub_server/history.py`.** The `^[0-9a-f]{16}$` scan, ordering, unreadable-
   entry tolerance, and Remove. Unit-testable against a fabricated state root.
5. **`hub_server/run_log.py`.** Schema, append, close, prune to 50, and the
   startup sweep that marks orphaned rows interrupted.
6. **`hub_server/children.py`.** Port pick, `Popen`, stdout drain and forward,
   URL-line detection, terminate, staging cleanup by child pid.
7. **`hub_server/runs.py` + `app.py`.** Current-run state, the SSE snapshot
   stream, the routes in `contracts/hub-http-api.md`, the static mount.
8. **`cli/home_command.py` + `main.py` registration.** Including adding `home`
   to `_DISCLOSURE_GATED_COMMANDS`.
9. **The page.** `vite.hub.config.ts`, `hub.tsx`, components, `vitest` specs.
10. **Rebuild bundles and verify in Chrome** per the quickstart, both
    appearances, narrow and wide.

## Complexity Tracking

> Filled only if the Constitution Check has violations that must be justified.

**None.** The Constitution Check above records no violations, so this table is
intentionally empty. The two decisions most likely to be mistaken for violations
— the new SQLite run log, and the hub being allowed to make network requests —
are argued in place there and in `research.md` §5 and §10 respectively.

## Post-Design Constitution Re-Check

Re-run after `data-model.md` and `contracts/` were written. Nothing in the
design changed a verdict. Three specifics worth confirming:

- **2.6**: `data-model.md` bounds `runs.sqlite` at 50 rows and prunes on every
  append. No other durable state was introduced during design — the history
  remains derived, and the current run remains in memory.
- **2.7**: the contracts put path validation ahead of every side effect. The
  `POST /runs` contract rejects a bad path with no process started, and the
  Remove contract names the exact directory it deletes and asserts the analysed
  repository is untouched.
- **2.2**: no contract exposes a route that binds or reaches anything beyond
  loopback; `POST /repositories/{id}/open` launches its child with an explicit
  `--host 127.0.0.1`.
