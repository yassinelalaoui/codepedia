# Contract: Chat Session URL Parameter

**Status**: New client-facing contract (no backend/API change). Replaces the
`localStorage` key `repo-scanner:chat-session-id` (spec 025) as the sole
mechanism for retaining a conversation's identity across a reload, a copied
link, or a different browser/device (FR-008, FR-009).

## Format

A wiki page hosting the chat panel (every generated page — `wiki-chat-root`
is mounted globally by `layout.html.jinja`) may carry one query-string
parameter:

```text
?chatSession=<sessionId>
```

- `chatSession` — the exact `sessionId` string returned by `POST /sessions`
  or accepted by `GET /sessions/{id}/messages` and
  `POST /sessions/{id}/messages` (spec 014/025/027, `chat_api/schemas.py`).
  Opaque to the client; never parsed or validated client-side beyond
  presence.
- Any other query-string parameters already present on the page (present or
  future) are left untouched — the client only ever reads/writes its own
  `chatSession` key, via `URLSearchParams`, and never rewrites the rest of
  the query string or the path.

## Client behavior

| Event | Behavior |
|-------|----------|
| Page loads with `?chatSession=<id>` present | `ChatPanel` mount effect calls `GET /sessions/<id>/messages` before enabling the question input. Success -> render restored history, input enabled (FR-010). 404 (`session_not_found`) -> parameter removed from the URL via `history.replaceState` (no reload), input enabled, conversation starts empty (FR-011). |
| Page loads with no `chatSession` parameter | Input enabled immediately; no history fetch. Conversation starts empty. |
| A session is created for the first time (first question asked on a page with no id yet) | Once `POST /sessions` resolves, `chatSession=<newId>` is written onto the current URL via `history.replaceState` — no navigation, no reload, no entry added to browser history. |
| The address (with `chatSession=<id>` for a still-existing session) is copied and opened again — same browser or a different one | Same as "page loads with the parameter present" above; this is what makes the address itself the shareable handle on the conversation (FR-009). |
| Two tabs open the same `?chatSession=<id>` address at once | Each tab independently runs the load sequence above; they are not required to stay live-synchronized with each other's subsequent questions (spec.md Edge Cases). |

## Explicitly out of scope

- Carrying `chatSession` across navigation to a *different* generated page
  (e.g. following a citation link) is not part of this contract; if the
  chosen link-generation approach happens to preserve it, that's incidental,
  not guaranteed (spec.md Assumptions).
- No new HTTP route or backend behavior is introduced by this contract —
  it governs only what the browser puts in its own address bar.
