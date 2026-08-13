# Quickstart: Repository Change Watcher

## Prerequisites

- Python 3.11 or later
- Local project dependencies installed (including `watchdog`)
- A sample local repository (a temporary directory is fine) with a few source
  files and a `.gitignore` plus a `node_modules/` directory, matching the
  scanner's (001) test fixtures
- A `RepositoryWatcher` instance constructed against that repository root, with
  `on_batch` wired to append every received `ChangeBatch` to a list for
  inspection

## Validate a single file change (SC-001)

1. Start the watcher on the sample repository.
2. Modify one existing source file's content.
3. Wait slightly longer than the stabilization delay.
4. Confirm exactly one `on_batch` call occurred.
5. Confirm that batch contains exactly one `FileChange`, for the modified
   file, with `change_type = MODIFIED`.

## Validate burst grouping (SC-002, SC-006)

1. Save the same file five times in quick succession (well within the
   stabilization delay of each other).
2. Wait slightly longer than the stabilization delay after the last save.
3. Confirm exactly one `on_batch` call occurred for that file, not five.
4. Separately, change ten files at once (e.g., simulate a branch switch by
   writing to ten files in a tight loop).
5. Wait for stabilization and confirm exactly one `on_batch` call occurred,
   whose batch lists all ten files.

## Validate exclusion parity (SC-003)

1. Modify a file inside `node_modules/` (or another directory excluded by
   the scanner's rules) in the sample repository.
2. Wait past the stabilization delay.
3. Confirm no `on_batch` call occurred.
4. Modify one excluded file and one relevant file in the same burst.
5. Confirm the resulting batch lists only the relevant file.
6. Index a file, then add it to `.gitignore` and stop the watcher (or don't
   start it yet).
7. Start the watcher.
8. Confirm the resulting catch-up batch reports that file as `DELETED` —
   it must leave the index now that it is excluded.

## Validate create+delete cancellation (edge case)

1. Create a new file, then delete it again before the stabilization delay
   elapses.
2. Wait past the stabilization delay.
3. Confirm no `on_batch` call occurred for that path.

## Validate startup catch-up (SC-005)

1. Index the sample repository once (so `repository_metadata`, 005, records
   its current state), then stop the watcher (or don't start it yet).
2. Modify one file and delete another while the watcher is not running.
3. Start the watcher.
4. Confirm exactly one `on_batch` call occurs before any live-monitoring
   batch, with `origin = "catchup"`, listing the modified file as `MODIFIED`
   and the removed file as `DELETED`.

## Validate first-run catch-up (edge case)

1. Point the watcher at a fresh sample repository that has never been
   indexed (no prior `repository_metadata` record exists for it).
2. Start the watcher.
3. Confirm exactly one `on_batch` call occurs before any live-monitoring
   batch, with `origin = "catchup"`, listing every non-excluded,
   non-binary file in the repository as `CREATED`.

## Validate non-blocking operation (SC-004)

1. Start the watcher on the sample repository.
2. While it runs, perform normal file operations (edit, save, delete,
   create files) directly through the filesystem/editor tooling.
3. Confirm every operation completes immediately, with no observable delay
   or lock contention introduced by the watcher.

## Expected result

Watching a repository detects created, modified, deleted, and renamed files;
groups bursts of related changes into a single handoff per burst; never
reports changes confined to excluded or binary paths; reconciles changes
made while offline — or the repository's entire first-ever indexing — into
one catch-up handoff at startup; and never blocks normal repository usage
while running.
