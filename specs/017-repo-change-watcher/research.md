# Phase 0 Research: Repository Change Watcher

## 1. Filesystem watch library

**Decision**: Use `watchdog` (Python) as the filesystem event source.

**Rationale**:
- The project is a Python codebase (`pyproject.toml`, `requires-python = ">=3.11"`); every
  existing feature (scanner, parser engine, metadata store, embedding engine, chat API, local
  web server) is Python, and the user explicitly selected `watchdog` over the Node.js
  alternative (`chokidar`) for this feature.
- `watchdog` wraps the native OS notification APIs (`ReadDirectoryChangesW` on Windows,
  `FSEvents` on macOS, `inotify` on Linux) behind one cross-platform `Observer` /
  `FileSystemEventHandler` API, which matches "continuous, background, non-blocking" (US2) —
  it runs its own thread and delivers events via callback rather than requiring the caller to
  poll.
- It is a small, pure add-on dependency (no native build step beyond optional platform
  extras already vendored by the library), consistent with the project's "infrastructure
  minimale" principle ([[constitution 2.6]]).

**Alternatives considered**:
- `chokidar` (Node.js): rejected — would require introducing a second language runtime into
  an otherwise all-Python codebase, and the user's instruction named it only as the
  alternative not chosen.
- Polling (`os.stat` loop over the tree on a timer): rejected as the primary mechanism —
  higher latency for "short stabilization delay" (SC-001), higher CPU cost on large
  repositories, and it duplicates work `watchdog`'s native backends already do efficiently.
  A lightweight, bounded walk is still used, but only once at startup for reconciliation
  (see §3), not as the continuous detection mechanism.

## 2. Exclusion rule reuse

**Decision**: Reuse `repo_scanner.ignore.IgnoreMatcher` / `load_ignore_matcher` and
`repo_scanner.binary.is_binary_path` directly from the existing scanner (001) rather than
re-implementing exclusion logic in the watcher.

**Rationale**:
- FR "exclusion parity with the scanner" and US4 require the watcher to never diverge from
  the scanner's rules. Importing the same matcher guarantees this by construction — there is
  only one place `.gitignore` parsing and the default excluded-directory set
  (`.git`, `node_modules`, `dist`, `build`, `out`, `target`) are defined.
- `IgnoreMatcher.ignores(relative_path, is_dir=...)` already evaluates on the full relative
  path, satisfying the edge case where an excluded directory contains a relevant-looking file
  name.
- Binary-file exclusion is out of scope for the watcher's own filtering pass at the raw-event
  level (deletion events can't be sampled for content), but is applied identically to how the
  scanner applies it: at handoff time, `is_binary_path` is checked for create/modify events
  before a file is included in a batch, so binary files never reach the reindexing pipeline.

**Alternatives considered**:
- Re-deriving exclusion patterns independently inside the watcher: rejected — guarantees
  drift between scanner and watcher over time, which the spec explicitly calls out as a
  correctness requirement (US4).

## 3. "Since the last indexation" baseline and startup catch-up

**Decision**: Reuse `repository_metadata`'s existing per-file content hash and
`last_indexed_at` bookkeeping (`RepositoryMetadataStore.has_file_changed`,
`get_source_file_content_hash`) as the `LastIndexedState`. On startup, the watcher performs
one bounded walk of the repository (via the scanner's traversal + exclusion rules) and diffs
the current file set and content hashes against what the metadata store has recorded, then
emits a single catch-up `ChangeBatch`.

**Rationale**:
- This bookkeeping already exists and is already the system's definition of "indexed"
  ([[constitution 2.5]] re-indexation incrémentale), so reusing it avoids introducing a second,
  competing notion of "last indexed" that could disagree with the metadata store.
- It satisfies principle 2.7 (repository stays read-only): the reconciliation state lives in
  the existing SQLite store outside the watched repository, not in a marker file written into
  the repo.
- A hash comparison (not just mtime) means a file touched but saved with identical content is
  correctly treated as unchanged, avoiding a spurious catch-up handoff entry.

**Alternatives considered**:
- A separate watcher-owned snapshot file written under the repository root: rejected —
  violates the read-only-repository principle ([[constitution 2.7]]).
- mtime-only comparison: rejected — less reliable across platforms/tools that rewrite files
  without content changes (e.g., some formatters, git checkouts), and the metadata store
  already tracks content hashes.

**First run (no prior `RepositoryMetadataStore` record)**: The same diff requires no special
case. An empty known-file-set and no stored hashes naturally diff to "every non-excluded,
non-binary file currently present is new," so reconciliation reports them all as `CREATED` in
one catch-up batch — the general algorithm already produces this result without a distinct
code path. This is the behavior specified in `spec.md`'s first-run edge case and FR.

**Exclusion-rule changes are legitimate deletions from the index's perspective**: Because the
"current state" side of the diff (§2) is computed by walking the repository through the same
`IgnoreMatcher`, a file that has become excluded since the last index (e.g., a `.gitignore`
edit) is simply absent from that walk. It is still present in the stored known-file-set, so the
general diff reports it as `DELETED` — and this is the *correct* outcome, not a
misclassification: the file should no longer be part of the index, and `DELETED` is exactly the
signal that tells the reindexing pipeline to drop it. No special case is needed here either; the
same general diff that handles genuine deletions already produces the right answer for
exclusion-rule changes.

## 4. Burst grouping / stabilization strategy

**Decision**: Per-path debounce with a short, fixed stabilization window (on the order of
1–2 seconds). Each raw filesystem event resets a per-file timer; a file is only added to the
next outgoing batch once its timer elapses without a further event. Batches are flushed once
no file has a pending timer (all touched files have stabilized), so a burst that touches many
files (e.g., a branch switch) still yields exactly one batch once everything settles, and a
single edited file yields its own batch shortly after its own timer elapses without waiting
on unrelated files.

**Rationale**:
- Directly implements US3 and SC-001/SC-002: N rapid saves of the same file reset the same
  timer instead of each scheduling a separate handoff, collapsing to exactly one batch.
- A create immediately followed by a delete of the same path within the window is resolved by
  collapsing the two raw events for that path before the timer elapses, so it never appears in
  the outgoing batch (edge case in the spec).
- Per-path timers (rather than one global timer restarted by any event) prevent a
  continuously-active repository (e.g., a long build writing many files over minutes) from
  starving out an unrelated single-file edit indefinitely.

**Alternatives considered**:
- A single global debounce timer reset by any event: rejected — an unrelated steady trickle
  of changes elsewhere in the repo could indefinitely delay an isolated single-file edit's
  handoff, working against SC-001's "short delay" guarantee.
- No debouncing (emit on every raw event): rejected — this is the exact behavior the feature
  exists to avoid (one reindex per keystroke/save).

## 5. Handoff contract

**Decision**: The watcher's public surface is a `RepositoryWatcher` that accepts a
caller-supplied callback (`Callable[[ChangeBatch], None]`) at construction time and invokes it
once per stabilized batch. It does not import or call the reindexing pipeline
(`repository_metadata.summary_pipeline.CodeSummaryPipeline`) directly.

**Rationale**:
- Keeps the watcher decoupled from any single downstream consumer, matching the spec's
  Non-Goal ("implementing or modifying the incremental reindexing pipeline itself"). The
  existing `CodeSummaryPipeline.summarizeRepository(..., changed_paths=...)` already accepts
  exactly the shape this callback can supply (a list of relative paths), so wiring the two
  together is a one-line adapter left to the integration/task that composes them, not part of
  this feature's contract.
- A plain callback (versus, say, a message queue) matches the project's "infrastructure
  minimale" principle — no new broker or process boundary is introduced.

**Alternatives considered**:
- Direct dependency on `CodeSummaryPipeline`: rejected — couples the watcher to one specific
  pipeline implementation and makes the watcher untestable without a local LLM available.
