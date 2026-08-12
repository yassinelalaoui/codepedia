# Data Model: Local Chat API

This feature adds one new package of API-facing entities and reuses the
existing `chat` package's entities unchanged as the underlying model.

## Reused entities

- **`ChatSession`** (`chat`, feature 011): the underlying session object —
  an id, an ordered list of `ChatMessage`, and the shared `VectorIndex` /
  `EmbeddingEngine` / `LocalLLMEngine` it answers against. This feature does
  not change its shape or its `ask()` behavior; it only calls it.
- **`ChatMessage`** (`chat`, feature 011): one message (`role`, `content`,
  `citedSymbolIds`, `citedFilePaths`, `timestamp`). Every API response is a
  projection of one or more of these.
- **`Citation`** (`chat`, feature 011): a single symbol/file citation with a
  score; used internally by `ChatSession.ask` and already flattened into
  `ChatMessage.citedSymbolIds`/`citedFilePaths` by the time this feature's
  endpoints see it.
- **`RAGContext`** (`chat`, feature 011): the assembled prompt context;
  entirely internal to `ChatSession.ask`, never exposed over HTTP.
- **`LocalDependencyUnavailableError`** (`chat`, feature 011): raised by
  `ChatSession.ask` when the local embedding engine or local model is
  unavailable; this feature's error mapping (Decision 6) catches it.

## New entities (`chat_api`)

### SessionRegistry

Represents the in-memory `session_id -> ChatSession` mapping owned by the
running server process.

Fields:
- `sessions` — `dict[str, ChatSession]`, empty at process startup.
- `vectorIndex`, `embeddingEngine`, `llmEngine` — the single shared instances
  (per research.md Decision 5) injected into every `ChatSession` this
  registry creates.

Relationships:
- One `SessionRegistry` per running server process.
- Creates and owns every `ChatSession` the process serves; never persisted,
  discarded on process exit.

Validation:
- A session id returned by `create_session()` MUST be unique within the
  registry's lifetime (UUID4 hex, per Decision 4).
- Looking up a session id not present in `sessions` MUST be treated as a
  not-found condition by the caller (mapped to HTTP `404`), never an
  implicit session creation.

### CreateSessionResponse

Fields:
- `sessionId` — the newly created session's identifier.

### AskQuestionRequest

Fields:
- `question` — non-empty, non-whitespace-only string.

Validation:
- Empty or whitespace-only `question` is rejected before reaching
  `ChatSession.ask` (HTTP `422`).

### ChatMessageView

Fields:
- `role` — `"user"` or `"assistant"`.
- `content` — the message text.
- `citedSymbolIds` — ordered, de-duplicated list of cited symbol ids (empty
  for user messages).
- `citedFilePaths` — ordered, de-duplicated list of cited file paths (empty
  for user messages).
- `timestamp` — ISO 8601 UTC timestamp.

Relationships:
- One `ChatMessageView` is produced per `ChatMessage` in a session, field for
  field (research.md Decision 7).

### AskQuestionResponse

Fields:
- `answer` — the generated assistant message's `content`.
- `citedSymbolIds` — same list as the assistant `ChatMessageView`'s.
- `citedFilePaths` — same list as the assistant `ChatMessageView`'s.

Relationships:
- Derived from the `ChatMessage` returned by `ChatSession.ask()` for this
  request; the corresponding user message and this assistant message are
  both appended to the session's history as a side effect of a successful
  call.

### SessionHistoryResponse

Fields:
- `sessionId` — the session's identifier.
- `messages` — ordered list of `ChatMessageView`, oldest first.

Validation:
- `messages` is `[]` for a session that has never been asked a question
  (not an error condition).

### ApiErrorResponse

Fields:
- `code` — stable machine-readable error identifier (e.g.
  `"local_dependency_unavailable"`, `"session_not_found"`,
  `"empty_question"`).
- `message` — human-readable description.

Relationships:
- Returned as the body of every non-2xx response from this feature's
  endpoints, alongside the HTTP status codes defined in
  `contracts/chat-api.md`.