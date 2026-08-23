# Chat Persistence Schema Contract

## Purpose

Define the two tables this feature adds to the existing per-repository
`repository-metadata.sqlite` file (`repository_metadata.sqlite_store`,
005), alongside `repositories` / `source_files` / `symbols` /
`dependency_graphs` / `dependency_edges`. See data-model.md for the full
field-by-field rationale.

## DDL

```sql
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    last_activity_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    cited_symbol_ids TEXT NOT NULL,
    cited_file_paths TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_timestamp
    ON chat_messages(session_id, timestamp);
```

## Placement

These statements are appended to
`repository_metadata.sqlite_store.SCHEMA_STATEMENTS` and therefore run
through the same `ensure_schema()` every other table in this file already
goes through — created lazily on first `connect()`, idempotent
(`IF NOT EXISTS`) like every existing statement in that tuple.

## Invariants

- `chat_messages.session_id` always references an existing `chat_sessions.id`;
  deleting a session (not exposed by this feature, but consistent with the
  existing `ON DELETE CASCADE` convention used for `source_files` →
  `repositories`) cascades to its messages.
- `chat_messages.sequence` is unique per `session_id` and strictly increasing
  in insertion order — the tie-breaker for chronological ordering when two
  messages share the same `timestamp` value (spec.md edge case).
- `cited_symbol_ids` / `cited_file_paths` are always valid JSON arrays of
  strings (possibly empty, `"[]"`), matching the existing convention already
  used for `symbols.metadata` / `module_symbols.imports` in this same file.
- No column in either table is nullable; a message with no citations is
  represented by empty JSON arrays, never `NULL`.
