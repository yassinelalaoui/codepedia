# Research: Repository Metadata Persistence

## Decision 1: Embedded SQLite as the storage backend

Decision: Use a single local SQLite file for persisted repository metadata.

Rationale: The feature explicitly requires local-only persistence with no
external server. SQLite provides durable storage, transactional updates, and
efficient indexed lookups while remaining simple to ship and reopen.

Alternatives considered: Flat JSON or YAML files were rejected because they make
incremental updates and selective retrieval harder to guarantee. A server-based
database was rejected because it violates the local-only constraint.

## Decision 2: Normalized repository/file/symbol schema

Decision: Store repository, source file, symbol, and dependency edge records in
separate logical tables linked by stable identifiers.

Rationale: The feature needs incremental updates for a single file while
preserving unrelated data. A normalized layout minimizes rewrite scope and
supports efficient lookup by file or module.

Alternatives considered: A single denormalized blob per repository snapshot was
rejected because updating one file would require rewriting the full snapshot and
would make targeted lookups inefficient.

## Decision 3: Content hash plus modification time per file

Decision: Persist a content hash and last-modified timestamp for each source
file.

Rationale: The feature requires rapid change detection between indexing runs.
The hash answers whether content has changed, and the timestamp preserves the
observable file metadata expected by the repository index.

Alternatives considered: Timestamp-only detection was rejected because it is
not robust when file timestamps are preserved or altered independently of
content. Hash-only tracking was rejected because it would lose useful file
metadata.

## Decision 4: Explicit symbol subtype records

Decision: Persist a common symbol record plus subtype-specific attributes for
modules, classes, and functions.

Rationale: The feature must restore the analyzed repository exactly, including
module imports, class inheritance, function parameters, and return types where
available. Separate subtype attributes keep those details queryable after
reopen.

Alternatives considered: Collapsing all symbols into a single generic payload
was rejected because it would make typed queries and deterministic reloads less
clear.

## Decision 5: File-scoped incremental writes

Decision: Treat a single source file as the unit of incremental update.

Rationale: The spec requires adding or updating one file and its symbols without
rewriting the entire repository state. File-scoped writes are a natural match
for repository indexing workflows.

Alternatives considered: Repository-wide rewrite on each run was rejected
because it conflicts with the incremental update requirement and increases I/O
cost.
