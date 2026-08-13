# Repository Watcher Contract

## Purpose

Define the public interface of the background watcher that detects file changes in the local
repository and hands off stabilized batches of impacted files to a caller-supplied
reindexing consumer.

## Core type

### `RepositoryWatcher`

Constructor inputs:

- `repository_root` — the local repository path already used by the scanner (001).
- `on_batch` — a callback invoked with one `ChangeBatch` per stabilized burst of changes.
- `stabilization_delay` — optional override of the default per-path debounce window.

Required methods:

- `start()` — begins background monitoring and runs the startup reconciliation pass
  described below; returns once monitoring is active (does not block for the life of the
  watch).
- `stop()` — stops background monitoring; safe to call once `start()` has returned.
- `isRunning()` — reports whether the watcher is actively monitoring.

Expected behavior:

- Applies the scanner's (001) exclusion rules — `.gitignore`, VCS metadata, default
  dependency/build directories, and binary-file detection — to every raw event before it is
  ever considered for a batch.
- Groups changes that occur within a short stabilization window into a single `ChangeBatch`
  per burst (research §4), instead of invoking `on_batch` once per raw filesystem event.
- On `start()`, reconciles the repository's current state against the existing
  `repository_metadata` (005) record of what was last indexed, and — if anything changed
  while the watcher was not running — invokes `on_batch` once with a `ChangeBatch` whose
  `origin` is `"catchup"` before live monitoring events begin.
- Never invokes `on_batch` with an empty batch.
- Never blocks or restricts normal filesystem access to the repository by other processes
  (editors, build tools, version control).

## Handoff expectations

- `on_batch` receives exactly the files that changed net of debouncing and exclusion — no
  excluded or binary files, no unchanged files, no duplicate entries for the same path
  within one batch.
- A single file changed once results in exactly one `on_batch` call carrying a `ChangeBatch`
  with exactly one `FileChange` for that file (SC-001).
- Several rapid changes to the same file within the stabilization window collapse into the
  same single `on_batch` call for that file (SC-002).
- `on_batch` is the watcher's only channel for reporting impacted files; the watcher does not
  call any reindexing pipeline directly (research §5), so this contract is what a consumer
  (e.g., `repository_metadata.summary_pipeline.CodeSummaryPipeline.summarizeRepository`,
  wired via its `changed_paths` argument) implements against.

## Failure expectations

- If `repository_root` does not exist or is not a readable directory, `start()` raises before
  any monitoring begins (matches the scanner's (001) existing validation behavior).
- If the watcher loses access to the repository after `start()` (e.g., the volume becomes
  unavailable), it surfaces a clear error through a means the caller can observe rather than
  stopping silently or hanging indefinitely.
- `on_batch` raising an exception does not crash the watcher's monitoring loop; the error is
  surfaced to the caller without silently dropping subsequent batches.

## Non-goals of this contract

- It does not define how a consumer reindexes the impacted files — only the shape and
  guarantees of the file list handed to it.
- It does not define a configuration UI or file for exclusion rules or debounce timing; those
  are read from the scanner's existing rules and a short internal default, respectively.
