# Phase 1 Data Model: Chat Interface Polish

This feature adds no backend entity, table, or column — it changes how the
existing frontend client (`frontend/src/`) tracks and renders state that was
already available (streamed fragments, persisted history, a session id).
The "entities" below are client-side view/state shapes.

## DisplayMessage (extended)

Existing shape in `ChatPanel.tsx`, extended with an explicit delivery state
so rendering logic (indicator vs. formatted content vs. error) doesn't have
to infer state from incidental fields like "content is the empty string."

| Field            | Type                                                        | Notes |
|------------------|--------------------------------------------------------------|-------|
| `role`           | `"user" \| "assistant"`                                      | Unchanged. |
| `content`        | `string`                                                      | Accumulated raw answer text (Markdown source) so far; unchanged shape, now rendered through the Markdown pipeline instead of as plain text. |
| `citedSymbolIds` | `string[]`                                                    | Unchanged — drives the existing separate citation list. |
| `citedFilePaths` | `string[]`                                                    | Unchanged. |
| `deliveryState`  | `"awaiting-first-fragment" \| "streaming" \| "complete" \| "error"` | New. `"awaiting-first-fragment"` renders the activity indicator in place of content; `"streaming"`/`"complete"` render `content` through the Markdown/citation pipeline; `"error"` is a terminal state for a message whose generation failed (FR-004). |

**Transitions** (assistant message only; a user message is always
`"complete"` the moment it's added):

```text
(message created, no fragment yet) --> awaiting-first-fragment
awaiting-first-fragment --[first onFragment]--> streaming
streaming --[more onFragment calls]--> streaming
streaming / awaiting-first-fragment --[terminal `done` event]--> complete
streaming / awaiting-first-fragment --[terminal `error` event, or ask() rejects]--> error
```

`error` is reached the same way the current implementation already handles
failure (`ChatPanel.tsx` catch block): the in-progress user/assistant pair is
what surfaces the error, per FR-004 and existing FR-007 behavior — nothing
about the removal-on-failure policy changes, only that a visible indicator
existed beforehand instead of a silently empty bubble.

## InlineSymbolReference (parsed, not stored)

Derived at render time from an inline Markdown code span's text; never
persisted, never sent to the backend.

| Field         | Type             | Notes |
|---------------|------------------|-------|
| `rawText`     | `string`         | The exact text inside the inline code span, e.g. `src/auth/login.py :: auth.authenticate_user`. |
| `filePath`    | `string \| null` | Left-hand side of `::`, trimmed; `null` if the span doesn't match the `<path> :: <symbol>` shape at all (then it's just ordinary inline code, not an `InlineSymbolReference`). |
| `symbolId`    | `string \| null` | Right-hand side of `::`, trimmed. |
| `resolved`    | `{ label: string; pageUrl: string } \| null` | Result of `findByCitation(entries, { symbolId, filePath })` (`frontend/src/lib/searchIndex.ts`, unchanged) — reuses the exact resolution already used for the separate citation list (FR-006). `null` means FR-007's plain-text fallback applies. |

## ConversationUrlState

Represents the session id's location of record, replacing the
`sessionIdRef` + `localStorage` pair the current implementation uses.

| Field             | Type                                            | Notes |
|-------------------|--------------------------------------------------|-------|
| `paramName`        | `string` (constant, e.g. `"chatSession"`)        | The query-string key read/written on the page's own URL. |
| `sessionId`        | `string \| null`                                  | Value of that parameter; `null` before any session exists on this page load. |
| `historyLoadState` | `"idle" \| "loading" \| "loaded" \| "not-found"`  | `"idle"` when no `sessionId` is present at mount (nothing to load); `"loading"` while the mount-time `getHistory()` call for a present `sessionId` is outstanding (FR-010 gates new questions here); `"loaded"` once history is restored and rendered; `"not-found"` once a 404 has been observed and the id has been cleared from the URL, after which the panel behaves as a fresh conversation (FR-011). |

**Transitions**:

```text
(mount, no `chatSession` param) --> idle
(mount, `chatSession` param present) --> loading
loading --[getHistory succeeds]--> loaded
loading --[getHistory 404s]--> not-found (param removed from the URL via history.replaceState)
idle / not-found --[first question asked, session created]--> loaded
  (createSession() succeeds; the new id is written into the URL via
  history.replaceState so a reload or copy of the address now resumes it)
```

## Relationship to existing entities

No change to the backend `ChatSession` / `ChatMessage` persistence model
(spec 025, `src/chat/models.py`, `repository_metadata.sqlite_store`) or to
the `AskQuestionResponse` / `SessionHistoryResponse` wire shapes
(`chat_api/schemas.py`) — this feature is entirely a client-side
presentation and persistence-location change layered on data those
contracts already provide.
