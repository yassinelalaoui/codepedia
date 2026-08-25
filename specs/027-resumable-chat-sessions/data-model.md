# Data Model: Resumable Chat Sessions via Streaming, Listing & History

No new entities and no schema change. This feature reads existing data
through one new query shape.

## Chat Session (existing entity — `chat.models.ChatSession`, `chat_sessions` table)

Unchanged fields, now also returned in **collection** form (previously only
retrievable one at a time by a caller who already knew its `id`):

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `id` | string | `chat_sessions.id` | Opaque session identifier (uuid4 hex, unchanged). |
| `createdAt` | string (ISO 8601 UTC) | `chat_sessions.created_at` | Unchanged; set once at session creation. |
| `lastActivityAt` | string (ISO 8601 UTC) | `chat_sessions.last_activity_at` | Unchanged; already refreshed on every `append_message` (spec 025). Drives the new listing's sort order. |

**New read shape**: `list_sessions(db_path) -> tuple[ChatSession, ...]` —
every persisted session (empty `messages`, same as `load_session`'s single-
session shape), ordered by `lastActivityAt` descending. No new validation
rules; existing `ChatSession.__post_init__` normalization already applies.

## Chat Message (existing entity — `chat.models.ChatMessage`, `chat_messages` table)

Unchanged. This feature does not add, remove, or reinterpret any field;
`GET /sessions/{id}/messages` already returns the complete, ordered history
(spec 014/025) and continues to do so unchanged (FR-003, FR-009).

## API-layer view types (new — `chat_api.schemas`)

- **`SessionSummary`**: `{ sessionId: string, createdAt: string, lastActivityAt: string }` — one entry in a session-listing response. Deliberately excludes messages (a summary, not a history — history stays a separate, existing call per session).
- **`SessionListResponse`**: `{ sessions: tuple[SessionSummary, ...] }` — the full, ordered (most-recently-active first), unpaginated list.

No relationships change: a `ChatMessage` still belongs to exactly one
`ChatSession` via `session_id`, unaffected by this feature.
