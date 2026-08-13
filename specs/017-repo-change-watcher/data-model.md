# Phase 1 Data Model: Repository Change Watcher

## ChangeType

Enumeration of the three change kinds the spec requires (US1, FR "change detection").

| Value      | Meaning                                             |
|------------|------------------------------------------------------|
| `CREATED`  | A new, non-excluded, non-binary file appeared.        |
| `MODIFIED` | An existing, non-excluded, non-binary file's content changed. |
| `DELETED`  | A previously-indexed file no longer exists.           |

A rename is represented as one `DELETED` entry for the old relative path and one `CREATED`
entry for the new relative path (research §4 / spec edge case).

## FileChangeEvent (raw, pre-stabilization)

Corresponds to `spec.md`'s Key Entity of the same name: the raw signal the watcher reacts to,
before any debouncing. This is not a class of its own — `src/repo_watcher/watcher.py`'s
watchdog handler (T007) produces it as the `(relative_path, ChangeType)` pair it feeds into
the debouncer (T004), and `src/repo_watcher/debouncer.py` holds it only as pending, per-path
state (see "State Transitions" below) until it either stabilizes into a `FileChange` or is
cancelled out (create+delete). It never appears in `models.py` as a standalone dataclass
because nothing outside the debouncer ever observes it directly — the `RepositoryWatcher`
contract (`contracts/repository-watcher-interface.md`) only exposes the post-stabilization
`ChangeBatch`.

| Field           | Type         | Notes                                                        |
|-----------------|--------------|-----------------------------------------------------------------|
| `relative_path` | `str`        | Same path format as `FileChange.relative_path`.                  |
| `change_type`   | `ChangeType` | The raw kind reported by watchdog for this occurrence (a `moved` event is split into a `DELETED` occurrence for the old path and a `CREATED` occurrence for the new path before reaching the debouncer, per the spec's rename edge case). |

## FileChange

A single, stabilized change to one file, ready to be reported.

| Field           | Type         | Notes                                                        |
|-----------------|--------------|---------------------------------------------------------------|
| `relative_path` | `str`        | Path relative to the repository root, POSIX-separated, matching the format the scanner (001) and metadata store already use. |
| `change_type`   | `ChangeType` | One of `CREATED` / `MODIFIED` / `DELETED`.                    |

Validation rules:
- `relative_path` MUST NOT resolve to a path excluded by `IgnoreMatcher` (001) — enforced
  before a raw event is ever accepted into the debounce window, not just at flush time.
- `relative_path` MUST NOT identify a binary file for `CREATED` or `MODIFIED` (checked via
  `is_binary_path` at flush time, since a file's binary-ness can only be sampled while it
  still exists); binary-ness is not evaluated for `DELETED` since the file's content is no
  longer available.
- A given `relative_path` appears at most once per `ChangeBatch`.

## ChangeBatch

The stabilized, deduplicated group of `FileChange` entries handed to the reindexing pipeline
after one burst window settles (the "reindexing handoff" of the spec).

| Field    | Type                 | Notes                                                              |
|----------|----------------------|----------------------------------------------------------------------|
| `changes`| `tuple[FileChange, ...]` | Non-empty; one entry per impacted file, per the validation rules above. |
| `origin` | `"live" \| "catchup"`| `"catchup"` for the one batch produced by startup reconciliation (SC-005); `"live"` for every batch produced while the watcher is actively running. |

Validation rules:
- A `ChangeBatch` is never emitted empty — if a burst window settles with no net change (e.g.,
  a create+delete of the same path cancelled out within the window), no batch is produced for
  it at all.
- Within a single batch, `relative_path` values are unique (no duplicate entries for the same
  file even if it changed more than once before stabilizing — only its net/latest
  `ChangeType` is kept).

## LastIndexedState (reused, not new storage)

Not a new entity introduced by this feature — this is the existing per-repository,
per-file content-hash record already maintained by `repository_metadata`
(`RepositoryMetadataStore`, feature 005), consulted read-only by the watcher's startup
reconciliation to compute the `"catchup"` `ChangeBatch` (research §3).

| Field (existing)   | Source                                                | Used for                                   |
|---------------------|--------------------------------------------------------|---------------------------------------------|
| per-file content hash | `RepositoryMetadataStore.has_file_changed` / `get_source_file_content_hash` | Detect `MODIFIED` files whose content actually changed since indexing. |
| known file set        | `RepositoryMetadataStore.load_repository(...).files`   | Detect files that existed in the last index but are now absent → `DELETED`. |
| current file set      | Scanner walk (001) over the repository, exclusions applied | Detect files present now but never indexed → `CREATED`; the diff base for the rest. |

First-run behavior: if `RepositoryMetadataStore` has no record at all for the repository yet
(known file set and every content hash are empty), the diff above naturally reports every
non-excluded, non-binary file in the current walk as `CREATED` — no special case is needed
(research §3), matching the first-run edge case in `spec.md`.

## WatcherConfiguration

The parameters a caller supplies to start a `RepositoryWatcher` (not persisted; in-memory
only for the life of the process).

| Field                 | Type                          | Notes                                                        |
|------------------------|--------------------------------|----------------------------------------------------------------|
| `repository_root`      | `Path`                          | Same repository root the scanner (001) and metadata store (005) already operate on. |
| `stabilization_delay`  | `float` (seconds)               | Per-path debounce window (research §4); defaults to a short, fixed value (on the order of 1–2 s) per the spec's Assumptions. |
| `on_batch`             | `Callable[[ChangeBatch], None]` | Handoff callback invoked once per stabilized, non-empty batch (research §5). |

## State Transitions (per watched path, within the debounce window)

```
(no pending change)
      │ raw create/modify/delete event (path not excluded)
      ▼
 pending(change_type) ──(further event on same path, timer reset)──▶ pending(new change_type)
      │ stabilization_delay elapses with no further event
      ▼
 included in next ChangeBatch, then cleared back to (no pending change)
```

Special case: `pending(CREATED)` followed by a `delete` event before the timer elapses
transitions directly back to `(no pending change)` — nothing is queued for that path
(create+delete cancellation, spec edge case).
