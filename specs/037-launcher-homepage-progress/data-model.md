# Data Model: Launcher Homepage with Live Run Progress

**Feature**: 037-launcher-homepage-progress
**Source**: [spec.md](./spec.md) Key Entities, resolved against [research.md](./research.md)

Three stores, deliberately distinct, because collapsing any two of them breaks a
requirement:

| Store | Lives | Survives hub restart | Why separate |
|---|---|---|---|
| Current run | Memory, `hub_server/runs.py` | No | FR-018 needs one authoritative snapshot; FR-012 guarantees there is only ever one |
| Run log | `~/.codepedia/runs.sqlite` | Yes | FR-026a. Must outlive the analysis it describes — a failed run leaves no state directory at all |
| Analyse history | Derived by scanning `~/.codepedia/repos/` | Yes (it *is* the state) | FR-029. Deriving it means it cannot disagree with what is on disk |

The run log and the history are the pair most at risk of being merged. They must
not be: a **run record** describes one *attempt*, including attempts that
produced nothing, while a **history entry** describes a repository that
*currently has stored analysis*. Merging them makes a failed run appear as a
repository, which is exactly what FR-030 forbids.

---

## 1. `RunState` — the current run (in memory)

One instance at most, guarded by a lock, held on the hub app's state. Mutated by
the child's stdout reader thread; read by HTTP handlers (research §4).

| Field | Type | Notes |
|---|---|---|
| `runId` | str | Opaque id, also the run log's primary key |
| `kind` | `"index"` \| `"open"` | An analysis, or the catch-up during an Open (FR-019) |
| `repositoryPath` | str | Absolute, already validated |
| `stages` | list[StageState] | All ten, in pipeline order, present from the start |
| `currentStage` | str \| None | None before the first stage and after the last |
| `providerSwitches` | list[ProviderSwitch] | FR-017 |
| `outcome` | None \| `"succeeded"` \| `"failed"` \| `"cancelled"` | None while running (FR-021) |
| `failedStage` | str \| None | FR-022 |
| `failureMessage` | str \| None | FR-022 |
| `providersAttempted` | list[str] | FR-022, populated on a provider failure |
| `startedAt` / `endedAt` | ISO-8601 str | `endedAt` set exactly when `outcome` is |
| `version` | int | Incremented on every mutation; what the SSE loop polls (research §4) |
| `childPid` | int \| None | Needed to find the staging directory on cancel (research §8) |

### StageState

| Field | Type | Notes |
|---|---|---|
| `name` | str | `Stage` enum member name, e.g. `SUMMARIZING` |
| `label` | str | The enum's value, e.g. `"Generating summaries"` — one source of wording with the terminal |
| `status` | `"pending"` \| `"running"` \| `"done"` \| `"failed"` | FR-014's three-way distinction, plus failure |
| `completed` / `total` | int \| None | Both None for stages that do not count items (FR-015) |
| `elapsedSeconds` | float \| None | Set on completion, from the existing `_stage` timing |

**Stage list** — taken from `Stage` at `src/cli/index_command.py:92-107`, not
re-declared, so the two cannot drift:

`VALIDATING → CHECKING_MODELS → SCANNING → PARSING → BUILDING_GRAPH →
GENERATING_DOCS_STRUCTURE → SUMMARIZING → GENERATING_DOCS_CONTENT → EMBEDDING →
STARTING_SERVER`

Only `SUMMARIZING` and `EMBEDDING` carry item counts. That is why FR-015 exists:
those two dominate the wall clock, and a bar that moved only between stages
would sit still through both.

### State transitions

```
            ┌── cancel (FR-012a) ──────────────► cancelled
            │
none ──► running ──► succeeded                  (terminal)
            │
            └── non-zero exit / error ────────► failed
```

Invariants, each traceable to a requirement:

- **At most one non-terminal `RunState` exists at a time** (FR-012). A second
  `POST /runs` while one is non-terminal is refused; it does not queue.
- **`outcome` is set exactly once, and never back to None** (FR-021). Reaching a
  terminal state is what frees the hub (FR-026).
- **A terminal `RunState` stays readable until replaced or dismissed** (FR-026).
  It is not cleared on a timer.
- **`cancelled` and `failed` are equivalent in what they keep**: nothing
  (FR-012a, FR-023).

### ProviderSwitch

| Field | Type |
|---|---|
| `stage` | str |
| `fromProvider` / `toProvider` | str |
| `reason` | str |
| `at` | ISO-8601 str |

Sourced from the existing failover logging (`PathFailoverLog`) and the backoff
hook `_echo_backoff` (`index_command.py:135`), so what the homepage shows and
what constitution 2.3 requires be visible are the same events.

---

## 2. `RunRecord` — the run log (`~/.codepedia/runs.sqlite`)

```sql
CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    repository_path     TEXT NOT NULL,
    kind                TEXT NOT NULL,           -- 'index' | 'open'
    started_at          TEXT NOT NULL,           -- ISO-8601
    ended_at            TEXT,                    -- NULL while running
    outcome             TEXT,                    -- NULL while running
    failed_stage        TEXT,
    failure_message     TEXT,
    providers_attempted TEXT                     -- JSON array, or NULL
);
CREATE INDEX IF NOT EXISTS runs_started_at ON runs (started_at DESC);
```

**Lifecycle**

1. **Insert** on run start, with `ended_at` and `outcome` NULL.
2. **Update** on termination, setting `ended_at`, `outcome` and, on failure, the
   diagnosis fields (FR-026a).
3. **Prune** after each insert: delete all but the newest 50 by `started_at`.
   FR-026c requires at least 20; 50 keeps the file at tens of kilobytes.
4. **Sweep** on hub startup: `UPDATE runs SET outcome='interrupted',
   ended_at=<now> WHERE outcome IS NULL`. This is FR-026d in one statement — a
   row still NULL can only belong to a run whose hub died, because FR-012
   guarantees there was only one and this process is new.

**Degradation** (FR-026e): every read is wrapped so that a missing file, a
`DatabaseError`, or an unrecognised schema yields an empty list rather than an
exception. The homepage then shows no past runs and remains fully usable. The
file is created on first write, so a fresh install has no run log and that is
not an error state.

**`outcome` values**: `succeeded`, `failed`, `cancelled`, `interrupted`. The
fourth exists only in the log — a live `RunState` never holds it, because the
process that would have written it is gone.

---

## 3. `HistoryEntry` — derived, never stored

Built by scanning `~/.codepedia/repos/` on request (research §6). Nothing is
written; nothing needs invalidating.

| Field | Type | Source |
|---|---|---|
| `stateId` | str | The directory name — the 16 hex chars from `cli.paths.state_id` |
| `repositoryPath` | str | `repositories.root_path` in that directory's `repository-metadata.sqlite` |
| `lastIndexedAt` | ISO-8601 str | `repositories.last_indexed_at`, same row |
| `available` | bool | Whether `repositoryPath` still exists as a directory (FR-031b) |

Schema and writer confirmed at `repository_metadata/sqlite_store.py:35-40`
(`root_path TEXT NOT NULL UNIQUE`, `last_indexed_at`) and `:279-311`
(`upsert_repository`, called on every index).

**Selection rules**

1. **Include a directory only if its name matches `^[0-9a-f]{16}$` exactly**
   (FR-030). This admits only what `state_id` produces and therefore excludes
   every `<id>.staging-<pid>` residue — of which `~/.codepedia/repos/` currently
   holds 7 against 4 real entries. Matching the positive pattern is safer than
   excluding a `.staging-` substring, because it cannot be defeated by a form of
   residue nobody anticipated.
2. **Skip an entry that cannot be read** — absent database, absent
   `repositories` row, `sqlite3.DatabaseError` — without failing the listing
   (FR-031).
3. **Order by `lastIndexedAt` descending** (FR-028).
4. **Identity is `repositoryPath`** (FR-031a). No move detection: a renamed
   folder yields a stale entry plus, once re-analysed, a second one.

**Remove** (FR-040, FR-041) deletes `~/.codepedia/repos/<stateId>/` and nothing
else. It never touches `repositoryPath`. It is refused while that repository is
being analysed or has a running child server (FR-042), which the hub can answer
from `RunState.repositoryPath` and the child table without any stored flag.

---

## 4. `ChildServer` — a launched `serve` process (in memory)

| Field | Type | Notes |
|---|---|---|
| `stateId` | str | Which history entry it serves |
| `repositoryPath` | str | |
| `pid` | int | |
| `port` | int | Chosen by binding port 0 and releasing it (research §7) |
| `url` | str \| None | Parsed from the child's startup line; None until ready |
| `status` | `"starting"` \| `"ready"` \| `"failed"` \| `"stopped"` | |
| `failureMessage` | str \| None | FR-038, FR-038a |

Several may exist at once (FR-037) — unlike runs, servers are not exclusive. All
are terminated when the hub stops (FR-007).

`url` arrives by matching the line `startup_lines` prints
(`chat_api/security.py:95-112`), which carries host, port **and** the child's
own token. The hub neither mints nor stores that token beyond this record: the
child generates its own per run (`cli/server.py:35`), and supplying one would
mean adding an option to `serve`, which FR-002 forbids.

**Failure classification**, because FR-038 and FR-038a are different messages:

| Child exit | Classified as | Requirement |
|---|---|---|
| `IndexNotFoundError` | Stored analysis missing or unusable; offer to analyse fresh | FR-038 |
| `LocalModelUnavailableError` | Provider chain unavailable; name the stage | FR-038a |
| `ServerBindError` | Could not start another server | FR-037 |
| Repository path gone | Documentation readable, cannot be brought up to date | FR-039 |

FR-038a exists because of research §11: `run_serve` calls
`check_ai_dependencies` for all three chains at `serve_command.py:36` before it
does anything else, so a provider outage refuses to serve a wiki that is
complete on disk. That is a provider problem, and saying "your analysis is
unusable" would be a false diagnosis.

---

## 5. `ProgressEvent` — the child-to-hub wire type

The parsed form of one sentinel line. Full wire format in
[contracts/run-progress-stream.md](./contracts/run-progress-stream.md); the
shape the hub works with:

| `type` | Payload | Applied to `RunState` |
|---|---|---|
| `stage` | `stage`, `label` | Previous stage → `done`; named stage → `running` |
| `stage_end` | `stage`, `elapsedSeconds` | Stage → `done` with its timing |
| `items` | `stage`, `completed`, `total` | Item counts on that stage (FR-015) |
| `failover` | `stage`, `from`, `to`, `reason` | Appended to `providerSwitches` (FR-017) |
| `failed` | `stage`, `message`, `providers` | Terminal `failed` (FR-022) |
| `server_ready` | `url` | Child server ready; drives the redirect (FR-035) |

Every event carries a monotonic `seq`. Ordering is guaranteed by the pipe
already, but a gap in `seq` is a diagnosable symptom rather than a silent
mis-render.

**Unparseable lines are not events.** Any stdout line without the sentinel — and
any sentinel line whose JSON does not parse — is forwarded verbatim to the hub's
own stdout and otherwise ignored (FR-016). The failure mode is "the terminal
still shows everything, the page shows less", never a crash.
