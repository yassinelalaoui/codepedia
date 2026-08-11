# Repository Metadata Interface Contract

## Purpose

Define the storage-facing operations used to persist and reopen repository
metadata without re-analyzing unchanged source files.

## Core operations

### `upsertRepository`

Inputs:

- repository identity
- repository root path
- detected languages
- indexing timestamp

Expected behavior:

- Creates the repository record when it does not exist
- Updates the repository record when it already exists
- Preserves the repository identity for the same root

### `upsertSourceFile`

Inputs:

- repository identity
- file path
- language
- content hash
- last modified timestamp

Expected behavior:

- Creates or updates one source-file record
- Replaces only the file-specific metadata for the changed file
- Leaves unrelated source files untouched

### `storeSymbolsForFile`

Inputs:

- source-file identity
- module symbol
- class symbols
- function symbols

Expected behavior:

- Stores all symbols associated with the file
- Keeps subtype-specific attributes available for later reopen
- Supports retrieving all symbols for one file or module in a single lookup

### `storeDependencyEdgesForFile`

Inputs:

- source-file identity
- typed dependency edges

Expected behavior:

- Stores typed import, call, and inheritance relations
- Avoids duplicate edges for the same source, target, and type

### `loadRepository`

Inputs:

- repository identity or root path

Expected behavior:

- Restores the persisted repository state exactly as it was last stored
- Returns files, symbols, and relations without requiring a fresh full scan

### `loadFileMetadata`

Inputs:

- file path or file identity

Expected behavior:

- Returns the full stored metadata for one file
- Includes the file fingerprint and all associated symbols

### `loadModuleMetadata`

Inputs:

- module identity or path

Expected behavior:

- Returns the stored metadata for one module
- Includes the module record and related symbol information

### `hasFileChanged`

Inputs:

- stored file identity
- newly observed content hash

Expected behavior:

- Indicates whether the file content differs from the stored state
- Can be used to skip re-analysis of unchanged files

## Persistence expectations

- The storage file remains local to the user's environment
- No external service or database server is required
- Repeated updates for one file do not rewrite the entire repository snapshot
- Reloading the repository preserves the same direct metadata answers
