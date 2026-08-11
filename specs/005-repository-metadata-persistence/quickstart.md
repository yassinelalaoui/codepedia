# Quickstart: Repository Metadata Persistence

## Prerequisites

- Python 3.11 or later
- Local project dependencies installed in an isolated environment
- A repository with at least one previously indexed source file
- A writable local path for the SQLite persistence file

## Store the initial repository state

1. Index a repository and persist its metadata to a local SQLite file.
2. Confirm that the repository record, source-file records, stored symbols, and
   dependency relations are present.
3. Capture the file content fingerprint for at least one source file.

## Validate incremental updates

1. Modify one source file in the repository.
2. Re-index only the changed file.
3. Confirm that the stored record for the modified file changes.
4. Confirm that unrelated files keep their stored metadata unchanged.

## Validate file and module lookups

1. Request the stored metadata for a specific file.
2. Request the stored metadata for a specific module.
3. Confirm that each lookup returns all stored symbols and relation data for the
   selected scope.

## Validate change detection

1. Compare a stored file fingerprint with a newly observed file state.
2. Confirm that unchanged files are recognized as unchanged.
3. Confirm that changed files are recognized as changed before re-analysis is
   attempted.

## Validate reopen behavior

1. Close the tool after indexing a repository.
2. Reopen the tool against the same SQLite file.
3. Confirm that all files, symbols, and dependency relations are still present.
4. Confirm that no fresh full-repository analysis is required to read the
   stored metadata.

## Expected result

The repository metadata persists locally, supports incremental file-level
updates, returns fast file/module lookups, detects unchanged files by content
fingerprint, and restores the full indexed state after reopen without a fresh
analysis pass.
