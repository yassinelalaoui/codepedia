# Contract: Child-to-Hub Progress Stream

**Feature**: 037-launcher-homepage-progress
**Producer**: `src/cli/progress_stream.py`, called from `cli/index_command.py`
and `cli/serve_command.py`
**Consumer**: `src/hub_server/progress_parse.py`

This is the contract that lets the hub see inside a running `index` or `serve`
**without changing what either command prints when a person runs it**
(research §2, §3).

## Activation

| | |
|---|---|
| Trigger | Environment variable `CODEPEDIA_PROGRESS_STREAM=1` |
| Set by | The hub, on children it launches — and by nothing else |
| When unset | Every emit call is a no-op. Not one byte of stdout differs from today |

**This is FR-002's evidence, and it is mechanically testable**: run `index` and
`serve` with the variable unset and compare captured stdout against the current
behaviour. A test that asserts no sentinel line appears without the variable is
the regression guard, and it must exist.

## Line format

One event per line on **stdout**, interleaved with ordinary human output:

```
@@CODEPEDIA_PROGRESS@@ {"seq":12,"type":"items","stage":"SUMMARIZING","completed":37,"total":412}
```

| Rule | Reason |
|---|---|
| Sentinel `@@CODEPEDIA_PROGRESS@@` then one space then compact JSON | Unambiguous against any real output; a symbol named like a progress line cannot be mistaken for one |
| Exactly one line per event, no embedded newlines | The reader is line-oriented; JSON string escaping guarantees this |
| Flushed immediately | Python block-buffers stdout when it is a pipe. Without an explicit flush, events arrive in 8 KB clumps and SC-002's 2-second bound fails |
| `seq` monotonic from 1 per process | A gap is a diagnosable symptom rather than a silent mis-render |
| stdout, not stderr | stderr carries real errors and must stay legible as such |

**Why not a separate file descriptor**: inherited fd 3 is awkward on Windows,
and a named pipe or a temp file is infrastructure constitution 2.6 says not to
reach for when a pipe already exists.

## Event types

All fields required unless marked optional.

### `stage` — a pipeline stage started

```json
{"seq":1,"type":"stage","stage":"SUMMARIZING","label":"Generating summaries"}
```

`stage` is the `Stage` enum **member name**; `label` is its **value**. Both are
sent so the page never re-derives wording the terminal already prints — one
source of truth (`index_command.py:92-107`).

Emitted from `_stage.__enter__` (`index_command.py:170-173`), which covers eight
stages, plus the two echoed directly: `VALIDATING` (`:184`) and
`CHECKING_MODELS` (`:239`).

### `stage_end` — a stage finished

```json
{"seq":8,"type":"stage_end","stage":"PARSING","elapsedSeconds":4.12}
```

From `_stage.__exit__`, which already computes this timing. Emitted on failure
too — how far a failed run got, and how long that took, is what makes it
diagnosable.

### `items` — progress within a stage

```json
{"seq":9,"type":"items","stage":"SUMMARIZING","completed":37,"total":412}
```

The FR-015 event, and the one SC-002 measures. Emitted from the two existing
callbacks, which already receive exactly these numbers:

- `_echo_summary_progress(completed, total, symbol)` — `index_command.py:126`,
  wired at `:366`. Already serialised under `CodeSummaryPipeline`'s own lock.
- `_echo_embedding_progress(completed, total, relative_path)` — `:132`, called
  under the embedding loop's `threading.Lock` at `:516-533`.

Both are already lock-protected at their call sites, so emission needs no lock
of its own.

### `failover` — an automatic provider switch

```json
{"seq":22,"type":"failover","chain":"summary","fromProvider":"local:qwen2.5-coder:1.5b","toProvider":"groq:openai/gpt-oss-20b","reason":"provider unavailable"}
```

FR-017, and the homepage half of constitution 2.3's "never silent in practice".
Sourced from the existing failover logging and the `_echo_backoff` hook
(`index_command.py:135`).

### `failed` — the run is ending in failure

```json
{"seq":40,"type":"failed","stage":"EMBEDDING","message":"No provider in the 'embeddings' chain is currently available.","providers":["local:nomic-embed-text:latest","openai:text-embedding-3-small"]}
```

Carries what FR-022 requires: the stage, the cause, and every provider
attempted. `providers` is `[]` when the cause was not a provider.

The hub does not depend on this event to detect failure — a non-zero exit code
is authoritative, and a child killed before it can emit anything still ends in a
terminal state (FR-021). This event supplies the *diagnosis*; the exit code
supplies the *fact*.

### `server_ready` — a child server is up (serve only)

```json
{"seq":51,"type":"server_ready","url":"http://127.0.0.1:51734/?token=..."}
```

Emitted alongside the existing `startup_lines` output. The hub also matches the
human-readable line as a fallback, so an older child still works.

### `catchup` — bringing a repository up to date (serve only)

```json
{"seq":2,"type":"catchup","completed":3,"total":11,"path":"src/thing.py"}
```

FR-019. Requires the new optional `on_progress` on
`IncrementalReindexPipeline.run`, defaulting to `None` so the pipeline stays
silent by default (research §3). Wired in `serve_command.py` beside the existing
`RepositoryWatcher(... on_batch=reindex_pipeline.run ...)` at `:89-92`.

Ordering is favourable and load-bearing: `watcher.start()` runs the catch-up
synchronously at `repo_watcher/watcher.py:51-53`, **before**
`start_local_server` prints the URL. So the hub sees every `catchup` event, then
`server_ready` — which is FR-019 followed by FR-035 with no coordination. When
there is nothing to catch up, no `catchup` event is emitted at all and
`server_ready` arrives directly, which is precisely FR-020's "no empty progress
display".

## Reader obligations

The hub's stdout reader thread MUST:

1. **Drain continuously for the child's whole life.** Not optional: a child
   server's watcher keeps printing, and a full pipe blocks the child
   permanently — the server would silently stop responding (research §7).
2. **Forward every non-sentinel line verbatim to the hub's own stdout.** This is
   FR-016: the terminal keeps everything it prints today.
3. **Treat an unparseable sentinel line as a non-event.** Forward it, ignore it,
   do not raise. Degradation is "the page shows less"; never a crash.
4. **Ignore an event naming an unknown stage or type.** Forward-compatibility,
   so a newer child cannot break an older hub.
5. **Decode as UTF-8 with `errors="replace"`.** A repository path or symbol name
   can carry anything; a decode error must not kill the reader and with it the
   child.
6. **Treat process exit as authoritative.** When the child exits, the run
   reaches a terminal state regardless of which events did or did not arrive
   (FR-021). Exit code 0 with no `failed` event is success; anything else is
   failure, diagnosed from the last `failed` event if there was one and from the
   exit code and forwarded output if not.
