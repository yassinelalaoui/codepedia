# Contract: Hub HTTP API

**Feature**: 037-launcher-homepage-progress
**Surface**: `src/hub_server/app.py` — `create_hub_app()`
**Consumer**: the hub page bundle (`frontend/src/hub.tsx`)

Every route below is served by the hub only. `chat_api.create_app` is not
extended and not modified (research §9, §12).

## Authentication

| | |
|---|---|
| Token | Fresh per hub run, `secrets.token_urlsafe(32)` via `chat_api.security.generate_token`. Never written to disk (FR-004) |
| Header | `X-Codepedia-Token` — required on every route below except the static mount and `GET /api/runs/stream` |
| Query | `?token=` accepted **only** on `GET /api/runs/stream`, because `EventSource` cannot set headers (research §4, §9) |
| Missing/wrong | `401` with `{"error": {"kind": "unauthorized", "message": "..."}}` (FR-005) |
| Host check | `TrustedHostMiddleware` with `allowed_hosts_for(host)`; a mismatched `Host` yields `400` (FR-006) |

Comparison uses `secrets.compare_digest`, inherited from `require_api_token`.

## Errors

One shape everywhere: `{"error": {"kind": "<slug>", "message": "<sentence>"}}`.
Messages are written for a person reading them in a browser with no terminal
open — that is what SC-004 measures.

| `kind` | Status | Raised when |
|---|---|---|
| `unauthorized` | 401 | No/invalid token (FR-005) |
| `invalid_path` | 400 | Path fails validation (FR-010) |
| `run_in_progress` | 409 | A run is already non-terminal (FR-012) |
| `not_found` | 404 | Unknown `stateId` |
| `conflict` | 409 | Remove while open or being analysed (FR-042) |
| `server_start_failed` | 502 | Child could not start (FR-037, FR-038, FR-038a) |

---

## `POST /api/runs` — start an analysis

**Request**: `{"path": "<string>"}`

**Path validation, before any process is started** (FR-009, FR-011,
constitution 2.7). Ordered; the first failure wins, and each produces a distinct
message naming what is wrong (FR-010):

1. Non-empty after trimming.
2. Expands `~`, resolves to an absolute real path (resolving symlinks and `..`).
3. Exists.
4. Is a directory, not a file.
5. Is readable.
6. Is not `~/.codepedia` nor contained in it — no analysing the tool's own
   state into itself.

**Then**: `409 run_in_progress` if a run is already non-terminal, its message
naming the repository currently being analysed (FR-012). Otherwise a child is
launched (`contracts/run-progress-stream.md`), a run row is inserted, and:

**`202`** → `{"runId": "...", "repositoryPath": "<resolved absolute path>"}`

The path echoed back is the **resolved** one, so the page shows what will
actually be analysed rather than what was typed.

**Guarantee**: on any 4xx from this route, no process was started, no file was
created, and the run log is unchanged.

## `GET /api/runs/current` — snapshot

**`200`** → a `RunState` snapshot (`data-model.md` §1), or `{"run": null}` when
none has run this session. Serves a client that cannot use `EventSource`, and
gives the tests a synchronous read.

## `GET /api/runs/stream` — live progress (SSE)

`text/event-stream`. Emits a full `RunState` snapshot immediately on connect,
then a fresh snapshot whenever `version` changes, polled at 250 ms
(research §4). Full snapshots, never deltas — so a late attach, a reload and a
second tab are one code path (FR-018).

Accepts `?token=`. Sends a comment heartbeat every 15 s so a dropped connection
is detected rather than hanging. Continues streaming after a run reaches a
terminal state — the terminal snapshot is exactly what FR-021 requires arrive.

## `POST /api/runs/current/cancel` — stop the running analysis

**`200`** → the terminal snapshot, `outcome: "cancelled"`.
**`409`** if no run is in progress.

Terminates the child, waits briefly, kills if needed, then deletes
`~/.codepedia/repos/<state_id>.staging-<child pid>` (research §8) so FR-012a's
"discard its partial work" is true and no new residue is created.

## `POST /api/runs/current/dismiss` — clear a terminal run

**`204`**. Returns the page to the index bar. Valid only on a terminal run —
`409` otherwise, since dismissing a live run would be a cancel in disguise.
FR-026 forbids clearing on a timer; this is the only way a terminal run leaves
the display.

---

## `GET /api/repositories` — the analyse history

**`200`** → `{"repositories": [HistoryEntry, ...]}`, newest `lastIndexedAt`
first (FR-028). Built by the scan in `data-model.md` §3: only
`^[0-9a-f]{16}$` directories (FR-030), unreadable entries skipped (FR-031),
each carrying `available` (FR-031b).

Fields are exactly what the row and its Properties view need (FR-034); there is
no second call to open a row's properties.

## `POST /api/repositories/{stateId}/open` — start a server and go there

Launches `python -m cli serve <path> --host 127.0.0.1 --port <free port>` with
the progress environment variable set, and drains its stdout (research §7).

Because the child's watcher runs its catch-up **before** printing the startup
line, the hub reports that work as a run of `kind: "open"` (FR-019) and
redirects when `server_ready` arrives.

**`200`** → `{"url": "http://127.0.0.1:<port>/?token=<child token>"}` when the
child is ready with nothing to catch up (FR-020).
**`202`** → `{"runId": "..."}` when catch-up work started; the page follows the
stream and navigates on `server_ready`.
**`502 server_start_failed`** with the classification in `data-model.md` §4 —
FR-038 (analysis unusable), FR-038a (provider chain unavailable, naming the
stage), FR-037 (could not bind another server).

An already-running, ready child for this `stateId` returns its existing URL
rather than launching a second (FR-037's independence is per repository).

## `DELETE /api/repositories/{stateId}` — forget a repository

Deletes `~/.codepedia/repos/<stateId>/` and nothing else. The analysed
repository is never touched (FR-041, constitution 2.7).

**`409 conflict`** if that repository is being analysed or has a running child
(FR-042) — the deletion is refused entirely, never performed in part.
**`204`** on success.

Confirmation is the page's responsibility (FR-040): this route is the
already-confirmed action, so it takes no "are you sure" parameter and must not
be reachable without the token.

---

## `GET /api/run-log` — recent run outcomes

**`200`** → `{"runs": [RunRecord, ...]}`, newest first (FR-026b). Reads
`~/.codepedia/runs.sqlite`. A missing, unreadable or older-schema database
yields `{"runs": []}` and a `200` — never a `500` (FR-026e).

Includes `interrupted` records written by the startup sweep (FR-026d).

---

## `GET /` and static assets

`StaticFiles` mounted at `/` with `html=True`, registered **last** so the API
routes above win. Unguarded, matching `chat_api`'s reasoning: the bundle and the
brand assets are public files, and everything that is not — starting a run,
opening a repository, deleting an analysis — is behind the token.

Serves `index.html`, `hub-ui.js`, `hub-ui.css`, `favicon.ico` and the brand
lockups from `src/hub_server/assets/` (FR-043).

The page reads `?token=` on first load and moves it into `sessionStorage`,
reusing `frontend/src/lib/apiToken.ts` unchanged — the same handling the wiki
already uses.
