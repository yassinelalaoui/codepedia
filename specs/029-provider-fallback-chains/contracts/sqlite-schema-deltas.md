# Contract: SQLite Schema Deltas

**Status**: Two additive changes to already-existing SQLite files. No new
database file, no migration framework introduced — follows this codebase's
existing idempotent `ensure_schema()` convention (research.md §8/§9).

## `repository_metadata` DB — new table

Appended to `repository_metadata/sqlite_store.py`'s `SCHEMA_STATEMENTS`
tuple, the same way `chat_sessions`/`chat_messages` (spec 025) were added:

```sql
CREATE TABLE IF NOT EXISTS engine_failover_log (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    stage TEXT NOT NULL,
    attempted_provider TEXT NOT NULL,
    result_provider TEXT,
    reason TEXT NOT NULL
)

CREATE INDEX IF NOT EXISTS idx_engine_failover_log_timestamp
    ON engine_failover_log(timestamp)
```

`result_provider` is nullable — `NULL` represents "every provider in the
chain was exhausted, nothing was switched to" (spec FR-007). No foreign key:
unlike `chat_messages`→`chat_sessions`, a failover event isn't scoped to one
session/index id — it's a repository-wide, cross-stage log.

## `repository_metadata` DB — `chat_messages` column addition

```sql
ALTER TABLE chat_messages ADD COLUMN generated_by TEXT NOT NULL DEFAULT ''
```

Guarded in `ensure_schema()` by checking `PRAGMA table_info(chat_messages)`
for a column named `generated_by` first, since (unlike `CREATE TABLE/INDEX
IF NOT EXISTS`) `ALTER TABLE ADD COLUMN` has no built-in idempotency and
would raise `sqlite3.OperationalError: duplicate column name` on a second
run against an already-migrated database.

## `vector_index` DB — `chunks` column addition

```sql
ALTER TABLE chunks ADD COLUMN embedding_model_id TEXT NOT NULL DEFAULT ''
```

Same `PRAGMA table_info(chunks)` guard as above, added to
`vector_index/storage.py`'s own `ensure_schema()` (a separate SQLite file
from `repository_metadata`, with its own schema function — research.md §1's
package inventory).

## Compatibility

Every existing row in both tables gets the column's `DEFAULT ''` on first
open after upgrading — `generated_by=''` for a chat message answered before
this feature existed, `embedding_model_id=''` for a vector computed before
it. Neither is deleted or rewritten (spec FR-011, Edge Cases). An empty
`embedding_model_id` never matches a *named* current provider's search
filter (research.md §8), so pre-existing vectors remain excluded from a
same-model comparison against a newly-configured provider without being
misidentified as belonging to it.
