# Research: Launcher Homepage with Live Run Progress

**Feature**: 037-launcher-homepage-progress
**Date**: 2026-09-04
**Input**: [spec.md](./spec.md)

Every finding below was verified against the working tree at commit `fa47a43`,
not recalled. File and line references are to that state.

---

## §1 How the hub runs an analysis: a child process, not a worker thread

**Decision**: The hub starts `codepedia index` as a child process
(`sys.executable -m cli index <path> ...`) and never calls `run_index` in its
own process.

**Rationale**: The deciding constraint is FR-012a — the user can stop a run, and
stopping it must end the run "promptly rather than running the current stage to
completion first".

`run_index` (`src/cli/index_command.py:215`) is a synchronous call with no
cooperative cancellation anywhere in it. Its expensive stages block inside
provider HTTP calls: `CodeSummaryPipeline` fans out over a thread pool
(`index_command.py:359-366`) and the embedding loop runs its own pool with a
`threading.Lock` (`:516-533`). Python cannot kill a thread, and none of those
loops polls a stop flag. In-process, "stop" could at best mean "set a flag and
wait for the current provider call to return" — which, against a rate-limited
Groq chain at `summaryConcurrency: 1` with a ~6.5s Ollama fallback, is not
prompt, and against a hung socket is not bounded at all. Out of process,
"stop" is `Popen.terminate()`, which is immediate and total.

Three further consequences all point the same way:

- **Crash isolation.** The pipeline loads Tree-sitter native extensions, and
  `pyproject.toml` pins `tree-sitter>=0.24,<0.26` precisely because 0.26.0
  segfaults on large files. A segfault in a worker thread takes the hub down
  with it and loses the run record; a segfault in a child is an exit code.
- **Staging directory identity.** `run_index` names its staging directory
  `<state_id>.staging-<os.getpid()>` (`index_command.py:234`). In-process, every
  hub run would collide on one pid, so a crashed run's residue would be adopted
  by the next run. Per-child pids keep them distinct and make the residue
  attributable.
- **The disclosure gate.** `cli.main`'s callback runs
  `ensure_disclosure_acknowledged` for `index`, `serve` and `provider`
  (`main.py:41-43`, `:78-80`). Going through the real command means the hub
  inherits that gate rather than needing to reimplement or bypass it — which a
  direct `run_index` call would silently skip.

**Alternatives considered**:

- *A worker thread calling `run_index` directly.* Gives structured progress with
  no parsing, since `_echo_summary_progress` and friends are already callbacks.
  Rejected on cancellation alone: it cannot satisfy FR-012a.
- *A child process running a purpose-built entry point rather than the real
  `index` command.* Rejected — it would be a second code path to keep in step
  with the CLI, and FR-002's guarantee is easiest to keep when the hub runs
  exactly the command a user would type.

**Consequence to handle**: `src/cli/` has no `__main__.py`, so `-m cli` does not
work today. Adding one (`from cli.main import app; app()`) is purely additive.
It is preferred over invoking the installed `codepedia` console script, because
that script is an `exe` launcher with the interpreter path baked in and it
breaks if the virtualenv is ever renamed.

---

## §2 Getting progress out of a child process without changing what the CLI prints

**Decision**: An environment variable, `CODEPEDIA_PROGRESS_STREAM=1`, set by the
hub on the children it launches, makes the CLI additionally emit
sentinel-prefixed single-line JSON events on stdout. Absent the variable —
which is every run a person starts themselves — not one byte of output changes.

Line shape: `@@CODEPEDIA_PROGRESS@@ {"type":"stage","stage":"SUMMARIZING",...}`.
The hub reads the child's stdout line by line: lines carrying the sentinel are
parsed as events, and **every other line is forwarded verbatim to the hub's own
stdout**, which is what satisfies FR-016.

**Rationale**: FR-002 requires the existing commands to behave exactly as they
do now, "same arguments, same output, same effects". An unconditional new line
of output violates that as written. Gating on an environment variable the hub
alone sets makes the guarantee mechanical rather than argued: with the variable
unset the emitting call is a no-op, and that is directly testable.

The emission points already exist and are few, because the pipeline funnels
through one place:

| What | Where | Note |
|---|---|---|
| Stage start | `_stage.__enter__`, `index_command.py:170-173` | Single choke point for 8 of the 10 stages |
| `VALIDATING` | `index_command.py:184` | Echoed directly, outside `_stage` |
| `CHECKING_MODELS` | `index_command.py:239` | Echoed directly, outside `_stage` |
| Summary item | `_echo_summary_progress`, `:126-129` | Already receives `(completed, total, symbol)` |
| Embedding item | `_echo_embedding_progress`, `:132-133` | Already receives `(completed, total, relative_path)` |
| Provider failover | `PathFailoverLog` + `_echo_backoff`, `:135` | Feeds FR-017 |

So the work is an emit alongside each existing `typer.echo`, not new plumbing —
the callbacks the previous brief worried about are already wired
(`summarizeRepository(..., on_progress=_echo_summary_progress)` at `:366`).

**Alternatives considered**:

- *Parsing the human-readable output.* The stage lines are `Stage` enum values
  and the item lines are `  [12/340] function foo`. Parseable, but it makes
  every future wording change a silent breakage of the homepage, and it cannot
  distinguish a symbol named like a progress line from a progress line.
- *A separate file descriptor or a named pipe.* Inherited fd 3 is awkward on
  Windows, and a named pipe is infrastructure constitution 2.6 tells us not to
  reach for when stdout is right there.
- *Writing events to a file the hub tails.* Adds a temporary file per run, with
  its own cleanup and partial-line problems, to solve something a pipe already
  solves.

---

## §3 The catch-up re-index is silent today — this is what FR-019 costs

**Finding**: `IncrementalReindexPipeline` prints nothing. `grep` for `echo`,
`print(`, `progress` or `on_progress` across `src/reindex_pipeline/*.py` returns
no matches at all. The catch-up that runs when a repository is opened —
`compute_catchup_batch` at `repo_watcher/watcher.py:51`, handed straight to
`reindex_pipeline.run` via `on_batch` (`serve_command.py:89-92`) — is therefore
completely invisible, on the terminal as much as anywhere.

**Decision**: Add an optional `on_progress` callback to
`IncrementalReindexPipeline.run`, defaulting to `None` so the pipeline stays
silent by default, and have `serve_command` pass a callback that emits through
the same sentinel channel as §2 — gated by the same environment variable.

**Rationale**: This is the only way to satisfy FR-019 without either changing
what plain `codepedia serve` prints (which FR-002 forbids) or having the hub
perform the catch-up itself. The gating means `codepedia serve` typed by a
person remains byte-identical, while the hub's child reports what it is doing.

The ordering works out favourably. `watcher.start()` runs the catch-up
synchronously (`watcher.py:51-53`) **before** `start_local_server` prints the
URL. So the hub sees, in order: catch-up progress events, then the URL line. It
can show progress while waiting and redirect the moment the URL arrives — which
is exactly FR-019 followed by FR-035, with no extra coordination.

**Alternatives considered**:

- *The hub performs the catch-up in-process before launching the child.*
  Requires rebuilding `run_serve`'s entire object graph — metadata store,
  dependency graph, vector index, doc generator, feature planner, three stage
  executors — in the hub. That is a duplicate of `serve_command.py:28-95` that
  must be kept in step forever, and the child's watcher would redo the scan on
  start anyway. Rejected as the larger change by a wide margin.
- *Leave the catch-up silent and show an indeterminate "bringing up to date"
  state.* Cheapest, and it does address the "looks hung" problem. Rejected
  because FR-019 asks for the same display as a fresh analysis, and because an
  indeterminate spinner for a stage that can take minutes is precisely the
  experience this feature exists to eliminate.

---

## §4 Transport to the browser: server-sent events

**Decision**: One SSE endpoint streaming run state, using Starlette's
`StreamingResponse` with `media_type="text/event-stream"`. Each stream sends a
complete snapshot as its first event, then a new snapshot whenever a version
counter changes.

**Rationale**: SSE is already the house pattern — `chat_api/app.py:77-103` uses
exactly this construction for chat streaming, so there is no new dependency and
no new idiom. Three properties of the problem match it:

- A run can last 40 minutes. Client polling at the 500 ms cadence SC-002 implies
  would be roughly 4,800 requests for one run; a single open stream is one.
- `EventSource` reconnects on its own, which is most of FR-018 for free.
- Sending a full snapshot rather than deltas makes late attach (FR-018), reload,
  and a second tab all the same code path, and removes any possibility of a
  client whose state has drifted from the server's.

**Internally the generator polls a version counter rather than waiting on a
cross-thread primitive.** The run state is mutated by the stdout-reader thread
and read by the async endpoint; a 250 ms poll of an integer is simpler than
bridging a thread to an event loop with `call_soon_threadsafe`, has no
lost-wakeup failure mode, and beats SC-002's 2-second bound by 8x and SC-011's
one-minute bound by 240x. Simplicity is the right trade at these tolerances.

**Alternatives considered**: WebSockets (bidirectional, which this is not, and a
heavier protocol for a one-way feed); plain client polling (rejected on request
volume, though it would work); long-polling (all of SSE's complexity, none of
its browser support).

**Consequence to handle**: `EventSource` cannot set request headers, so it
cannot present `X-Codepedia-Token`. See §9.

---

## §5 Where the run log lives

**Decision**: A new SQLite database at `~/.codepedia/runs.sqlite`, holding one
row per run, pruned to the most recent 50.

**Rationale**: Constitution 2.6 forbids an external database server, a broker,
or cloud storage, and expressly permits embedded local storage — "SQLite et un
index vectoriel local sur fichier". A local SQLite file is squarely inside that,
so FR-026a through FR-026e need no Complexity Tracking entry. SQLite over a JSON
file for two reasons that matter here: writes are atomic, so a hub killed
mid-write cannot leave a truncated log; and pruning is one `DELETE` rather than
a read-modify-write of the whole file.

It is deliberately a **separate** database from any repository's
`repository-metadata.sqlite`. A run record must outlive the analysis it
describes — a failed run produces no state directory at all, and FR-041's Remove
deletes a repository's directory entirely. Storing run history inside per-repo
state would lose exactly the records most worth keeping.

50 rows satisfies FR-026c's floor of 20 with room, and bounds the file at a few
tens of kilobytes.

**FR-026d falls out of the schema**: a run row is inserted with `ended_at` and
`outcome` NULL when it starts and updated when it ends. On hub startup, any row
still NULL belongs to a run whose hub died; a single `UPDATE` marks those
`interrupted`. No separate liveness tracking is needed.

**Alternatives considered**: a JSON-lines file (simple, but a partial final line
after a kill is a real case and SQLite removes it); keeping only the last run in
memory (what was recommended in clarification and rejected by the owner);
per-repository run history (rejected as above).

---

## §6 Building the history listing, and whether it needs a cache

**Decision**: Scan `~/.codepedia/repos/` at request time. No cache.

**Rationale**: `repositories` in each `~/.codepedia/repos/<state_id>/repository-metadata.sqlite`
has `root_path TEXT NOT NULL UNIQUE` and `last_indexed_at`, written by
`upsert_repository` (`repository_metadata/sqlite_store.py:279-311`, schema at
`:35-40`). One row per state directory is all the listing needs, so the scan is
N small SQLite opens for N repositories. At SC-006's bar of 20 repositories
inside 2 seconds this is not close: the state directory on this machine
currently holds 4 real entries and the read is sub-millisecond each.

A cache would be a second source of truth that can disagree with the directory —
a repository removed by FR-041, or a state directory deleted outside the tool,
would leave the cache wrong. The clarification session deferred this question to
planning; the answer is that the measurement does not justify the invalidation
problem.

**Filtering is the part that needs care.** `~/.codepedia/repos/` currently holds
7 `.staging-<pid>` directories against 4 real ones:

```
3d82e509c5da9263            <- real
3d82e509c5da9263.staging-16056   <- residue
3d82e509c5da9263.staging-18600   <- residue
...
a47b5ea9c5a22795.staging-21160   <- residue
```

`state_id` is `sha256(...)[:16]` (`cli/paths.py`), so a real state directory
name always matches `^[0-9a-f]{16}$` exactly. Matching that pattern — rather
than excluding a `.staging-` substring — is the safer test, because it admits
only what the tool itself produces. That is FR-030, and it is also why FR-031
(skip an unreadable entry) is separate: a directory can have the right name and
still hold a database this version cannot read.

---

## §7 Launching and supervising a per-repository server

**Decision**: `Popen([sys.executable, "-m", "cli", "serve", <path>, "--host",
"127.0.0.1", "--port", <port>])`, with stdout piped and drained by a reader
thread. The hub learns the child is ready — and learns its token — by parsing
the startup line the child prints.

`startup_lines` (`chat_api/security.py:95-112`) prints:

```
Documentation wiki available at http://127.0.0.1:<port>/?token=<token>
```

That line is the readiness signal and the credential in one. The hub does not
generate the child's token and does not need to: `serve` mints its own per run
(`cli/server.py:35`), and having the hub supply one would mean adding an option
to `serve`, which FR-002 forbids.

**Port allocation**: bind a socket to port 0, read the assigned port, close it,
and pass that number to the child. The window between close and the child's bind
is a race in principle; in practice on a loopback interface with a single user
it is negligible, and FR-037 already requires a failure to start a further
server to be reported rather than silent, so the race degrades into a message.

**Draining stdout is mandatory, not optional.** The child's watcher keeps
printing for as long as it runs. An undrained pipe fills and blocks the child
permanently — the server would simply stop responding. The reader thread that
exists for §2's progress events is the same thread that prevents this.

**FR-007** (the hub stops its children when it stops) is a `terminate()` over
the child table in a shutdown handler, with a short join and a `kill()` fallback.

**Alternatives considered**: `uvicorn` in a thread inside the hub serving each
wiki (rejected — it is re-hosting, which the owner ruled out, and it would
duplicate `create_app`); asking the user for a port (rejected against FR-035's
"without the user typing any command").

---

## §8 Cancelling a run, and cleaning up after it

**Decision**: `terminate()` the child, then delete the staging directory it left
behind, identified by the child's own pid.

**Rationale**: `run_index` cleans up its staging directory in an
`except Exception:` handler (`index_command.py:254-256`), which a `terminate()`
does not run — on Windows `terminate()` is `TerminateProcess`, which no Python
handler intercepts. So the hub must do it: after the child exits, remove
`~/.codepedia/repos/<state_id>.staging-<child pid>` if present. The hub knows
both halves, and `state_id(root)` is a pure function of the path
(`cli/paths.py`).

This is what makes FR-012a's "discard its partial work exactly as a failure
does" true rather than aspirational, and it stops cancellation from being a
new source of the residue §6 has to filter.

The same cleanup runs after a child that exits non-zero, for the same reason:
finding 1 of the feature brief observed that these directories are already left
behind on some failures, and a hub that supervises children can tidy the ones it
started. It deliberately does **not** touch residue it did not create — that is
listed as out of scope, and deleting directories belonging to another process's
live run would be a genuine bug.

---

## §9 Authenticating the hub

**Decision**: Reuse `chat_api.security` — `generate_token`, `require_api_token`,
`allowed_hosts_for`, `is_loopback_host` — with one addition: a dependency that
accepts the token from either the `X-Codepedia-Token` header or the `token`
query parameter.

**Rationale**: FR-004 and FR-005 describe the scheme `security.py` already
implements, and its module docstring already reasons through both defences —
the token against another local process, the allowed-hosts check against DNS
rebinding (FR-006). Reusing it is strictly better than restating it.

The query-parameter fallback is forced by §4: `EventSource` cannot set headers,
so the progress stream cannot present one. `TOKEN_QUERY_PARAM` already exists in
`security.py:38` for the equivalent reason on the wiki side, and
`frontend/src/lib/apiToken.ts` already implements the browser half — read the
token from the URL on first load, move it into `sessionStorage`, send it
thereafter. The hub reuses that module unchanged.

The fallback is scoped to the SSE endpoint only. Every other state-changing
route takes the header, so a token cannot leak into a browser history entry or a
`Referer` for a request that did not need it there.

**What is deliberately not reused**: `chat_api.create_app` mounts `StaticFiles`
at `/` with `html=True` as its last route (`chat_api/app.py:159`), unguarded, on
the reasoning that the wiki pages are already readable on disk. The hub's static
assets are equally public, so the same shape is right — but the hub builds its
own app rather than extending the chat app, because the two have no routes in
common and FR-002 is easiest to keep when `create_app` is not touched at all.

---

## §10 The hub's page

**Decision**: A second Vite build from the existing `frontend/` project, entry
`src/hub.tsx`, emitting `hub-ui.js` and `hub-ui.css` into
`src/hub_server/assets/`, served alongside a static `index.html`.

**Rationale**: FR-043 asks the homepage to share the wiki's visual language, and
FR-044a asks for the same three-state appearance control. Both already exist in
`frontend/`: `src/styles.css` holds the Tailwind v4 theme tokens,
`components/ThemeToggle.tsx` is the three-state control, and `lib/theme.ts` is
the pre-paint application logic FR-044b needs. Sharing the project makes these
literal reuse rather than reimplementation, and puts the hub's tests in the same
`vitest` suite as the wiki's.

A second build invocation is required rather than a second entry in the existing
one: `vite.config.ts` uses `build.lib` with `formats: ["iife"]`, and a library
build in IIFE format takes exactly one entry. So `vite.hub.config.ts` reuses the
same plugins and `styles.css` and changes only `entry`, `outDir`, `name` and
`fileName`. Note `emptyOutDir: false` matters in the existing config because the
wiki assets directory also holds `mermaid.min.js` and `favicon.ico`; the hub's
output directory needs the same setting for the brand assets that sit beside it.

**The hub is not bound by the wiki's zero-fetch rule** — it is served over
loopback and talks to its own origin. But the constraint is one-directional:
FR-045 requires that nothing in this feature introduces a fetch into a generated
wiki, so the two bundles stay separate and the hub's build never writes into
`src/doc_generator/assets/`.

**Alternatives considered**: a server-rendered Jinja page with hand-written
vanilla JS (avoids a second bundle, but re-implements the theme control and
forfeits the 142-test vitest suite's idioms); putting the hub UI in a new
frontend project (duplicates the Tailwind theme, which is the specific thing
FR-043 wants shared).

---

## §11 Finding: no repository can be opened on this machine either

**This changes what the homepage will actually show the owner, and it is not
something the feature can fix.**

`run_serve` calls `check_ai_dependencies(embeddings=..., summary=..., chat=...)`
at `serve_command.py:36`, before it does anything else.
`check_ai_dependencies` (`cli/availability.py`) raises
`LocalModelUnavailableError` if **any** named stage's chain has no available
provider. The configured `embeddingChain` is
`["local:nomic-embed-text:latest", "openai:text-embedding-3-small"]`; Ollama is
not running and the OpenAI key is quota-exhausted.

So on this machine `codepedia serve` fails before serving anything — which means
FR-035's Open fails too, for every repository in the history, even though the
generated wiki is sitting complete on disk. The previously known consequence was
that indexing could not finish; the same check makes *opening* impossible as
well.

**Decision**: Report it, do not work around it. Three candidate workarounds were
considered and all rejected:

- *Changing the provider chains.* Out of scope by explicit instruction, mutates
  `~/.codepedia/config.json`, and re-triggers the disclosure gate.
- *Passing a flag to `serve` to skip the check.* Changes `serve`, which FR-002
  forbids, and would ship a way to start a server whose chat cannot work.
- *Having the hub serve the static wiki files when `serve` cannot start.* This
  is re-hosting, which the owner ruled out, and it would silently produce a wiki
  with a dead chat panel — worse than a clear refusal.

What the feature does instead is make the refusal legible: an Open that fails
this way must name the unavailable stage chain, exactly as FR-022 requires of a
failed run. This needs a requirement of its own, since FR-038 covers a *missing
or unusable stored analysis* and this is neither — the analysis is perfect and
the provider is not. **Recorded as FR-038a in the amended spec.**

**Testing consequence**: no automated test may depend on a real successful index
or serve. The existing suite already solves this — `tests/integration/test_cli.py`
uses a `fake_engines` fixture with `local:test-embed` / `local:test-llm` chains
(`test_cli.py:33-44`). Every hub test follows the same pattern, and the browser
verification drives the homepage against a hub whose children are stubs.

---

## §12 What this feature does not change

Stated explicitly because each was considered and deliberately left alone:

- `cli/main.py`'s existing commands, and `cli/serve_command.py`'s behaviour
  under a plain invocation. The only edits are additive and environment-gated
  (§2, §3).
- `chat_api/app.py`'s `create_app` and its static mount (§9).
- The atomic promote-or-discard contract in `run_index` (out of scope by
  decision; §8 only cleans up after children the hub itself killed).
- The generated wiki's zero-fetch guarantee (§10, FR-045).
