# Phase 0 Research: Chat Session Persistence

## Decision 1 — Where the two new tables live

**Decision**: Add `chat_sessions` and `chat_messages` DDL directly to
`repository_metadata.sqlite_store.SCHEMA_STATEMENTS`, plus
`CREATE INDEX IF NOT EXISTS idx_chat_messages_session_timestamp ON
chat_messages(session_id, timestamp)`. They are created by the exact same
`ensure_schema()` / `connect()` already used for `repositories` /
`source_files` / `symbols` / `dependency_graphs` / `dependency_edges`, in the
same per-repository `repository-metadata.sqlite` file
(`cli/paths.py:metadata_db_path`).

**Rationale**: Matches the request precisely ("le même schéma SQLite que
Repository/SourceFile/Symbol"). `sqlite_store.py` is already the single
schema-owning module for this file — nothing outside it defines DDL for it
today — so extending `SCHEMA_STATEMENTS` keeps that invariant instead of
introducing a second place that can create/alter tables in the same file.
It also avoids a second local database file, which constitution 2.6
("infrastructure minimale et stockage local... aucune dependance a une
infrastructure lourde") does not require and would only add operational
surface (two files to keep in sync, two places a corrupt-partial-write could
happen).

**Alternatives considered**:
- A dedicated `chat-sessions.sqlite` file next to `repository-metadata.sqlite`
  — rejected: adds a second local db file for no isolation benefit, and reads
  slightly against the spirit of "no additional infrastructure."
- A shared cross-package `schema.py` that both `repository_metadata` and
  `chat` import — rejected as unneeded indirection; `repository_metadata`
  already is that shared schema owner for this file, so reuse it rather than
  inventing a new intermediary.

## Decision 2 — Where the row ↔ `chat.models` mapping code lives

**Decision**: A new module owned by the `chat` package, `chat/sqlite_store.py`,
holds the CRUD functions (`create_session`, `touch_session`, `append_message`,
`load_session`, `load_messages`), operating directly on
`chat.models.ChatSession` / `chat.models.ChatMessage`. It opens the shared
database via `repository_metadata.sqlite_store.connect(db_path)`, so schema
creation and the connection factory stay centralized in `repository_metadata`
while the object mapping stays where the mapped types are defined.

**Rationale**: `docs/architecture.md` states the system's layers plainly:
"Packages within a layer don't depend on each other; dependencies only flow
downward (a later layer depends on layers above it)." `repository_metadata`
is layer 2 (Analysis); `chat` is layer 4 (Knowledge Derivation) and already
legitimately depends downward on layer 2/3 packages (e.g. it already reads
`RetrievedEvidence` shaped by embedding/vector-index concerns). The reverse —
`repository_metadata` importing `chat.models.ChatMessage` to build its own
CRUD functions — would invert that mandated direction and make an earlier,
supposedly foundational layer depend on a later one. Placing the CRUD/mapping
code inside `chat` instead keeps every existing dependency arrow pointing the
same way it already does, while still fully satisfying "ChatSession/ChatMessage
existantes deviennent le mapping objet de ces tables" literally — those exact
dataclasses are what gets read from and written to the tables, with zero
duplicate DTOs anywhere.

**Alternatives considered**:
- CRUD/mapping functions inside `repository_metadata.sqlite_store`, importing
  `chat.models` — rejected: inverts the mandated layer direction.
- New, `repository_metadata`-local persistence dataclasses
  (`ChatSessionRecord`/`ChatMessageRecord`), translated to `chat.models`
  objects in `chat_api` — rejected: works layering-wise, but contradicts the
  explicit ask that the *existing* `ChatSession`/`ChatMessage` classes become
  the mapping, and adds a translation step neither the request nor the spec
  called for.

## Decision 3 — Extending `ChatSession` with persisted timestamps

**Decision**: Add `createdAt: str` and `lastActivityAt: str` fields to the
existing `chat.models.ChatSession` dataclass, both ISO-8601 UTC strings
defaulting to "now" the same way `ChatMessage.timestamp` already does. The
pre-existing `vectorIndex` / `embeddingEngine` / `llmEngine` / `topK` fields
remain runtime-only — they are never read from or written to `chat_sessions`.

**Rationale**: `chat_sessions(id, createdAt, lastActivityAt)` as specified
maps onto exactly the identity + two timestamp fields of the object that
already exists; adding them in place keeps one `ChatSession` type rather than
a parallel persisted/runtime split.

**Alternatives considered**: a separate `PersistedChatSession` record —
rejected, contradicts "deviennent le mapping objet de ces tables."

## Decision 4 — When a message is written

**Decision**: `ChatSession.ask()` (`chat/session.py`) persists the user
message and the assistant message individually, immediately after each is
appended to `self.messages` — via an optional `messageStore` collaborator
set on the `ChatSession` instance by whoever constructs/reloads it
(`chat_api.SessionRegistry`). Creating a session persists its `chat_sessions`
row up front; each successful message append also refreshes
`lastActivityAt` for that session.

**Rationale**: Directly satisfies FR-004 (incremental write — appending a
message never rewrites the session) and SC-003 (append stays O(1) regardless
of prior history length): each write is one `INSERT` into `chat_messages`
plus one `UPDATE` of a single `chat_sessions` row, never a re-serialization
of the whole message list.

**Alternatives considered**: persist the full `messages` list after every
`ask()` call — rejected, this is exactly the "rewrite the whole session on
every append" behavior FR-004 forbids, and it would violate SC-003 as history
grows.

## Decision 5 — How `SessionRegistry` resolves a session id after a restart or reload

**Decision**: `SessionRegistry.get_session()` first checks its in-memory
cache (the fast path for an active conversation within one running process);
on a cache miss, it falls back to `chat.sqlite_store.load_session()` +
`load_messages()`, reconstructs a live `ChatSession` (re-attaching the
registry's own `vectorIndex`/`embeddingEngine`/`llmEngine`, since those are
never persisted), populates its message history, caches it, and returns it —
raising `SessionNotFoundError` only when the store also has no such id.
`create_session()` persists the new `chat_sessions` row in addition to
caching it in memory.

**Rationale**: This single code path covers both User Story 1 (server
restart — the in-memory cache is empty because the process is new) and User
Story 2 (page reload — the browser resends a session id the current
process's cache may or may not still hold) without special-casing which kind
of "loss" happened, and it satisfies FR-006/FR-007/FR-008 (a genuinely
unknown id still 404s via the existing `SessionNotFoundError` → `chat_api`
exception handler, per `chat_api/errors.py`).

**Alternatives considered**: always load from SQLite, no in-memory cache —
rejected as an unnecessary read on every single question in an already-active
conversation, when nothing has restarted or reloaded.

## Decision 6 — Resuming a session id across a page reload

**Decision**: `ChatPanel.tsx` persists the created session id to the
browser's local storage (scoped to the wiki's own origin) instead of only an
in-memory React ref, and on mount attempts to resume that stored id — fetching
its history — before falling back to creating a brand-new session if none is
stored or the stored id no longer resolves (e.g. the repository was
re-indexed from scratch).

**Rationale**: Directly satisfies FR-007 / User Story 2. No server-side
identity or login system is introduced, consistent with the spec's
Assumptions ("no user-facing login or identity system").

**Alternatives considered**: a server-set cookie — rejected as unnecessary
complexity for a single-user local tool already serving one static origin
with no auth boundary.

## Decision 7 — API surface

**Decision**: No new HTTP endpoints. `POST /sessions` still creates a new
session (and now also persists its row); `GET /sessions/{id}/messages`
already returns the full ordered history in one request (FR-005) and already
404s via `SessionNotFoundError` for an unknown id (FR-008) — both simply need
to keep working once storage is durable, which Decisions 4–5 provide.
"Resuming" a session from the frontend's perspective is just calling the
existing `GET` on a remembered id, not a distinct "resume" endpoint.

**Rationale**: Minimizes surface-area change; the existing contract already
had the right shape (see `specs/014-local-chat-api/contracts/` and
`chat_api/schemas.py`), it just wasn't backed by durable storage yet.

**Alternatives considered**: none — no gap in the existing contract was found
that required a new endpoint.
