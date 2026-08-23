# Feature Specification: Chat Session Persistence

**Feature Branch**: `025-chat-session-persistence`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "Étendre la couche de persistance des métadonnées (Partie 2.1) pour stocker durablement les sessions de chat et leurs messages, afin qu'une conversation survive à un redémarrage du serveur ou à un rechargement de la page wiki. Chaque session doit être identifiable par un identifiant stable, et chaque message (question de l'utilisateur ou réponse générée) doit être persisté avec son rôle, son contenu, la liste des symboles/fichiers cités en justification, et son horodatage, dans l'ordre chronologique. L'écriture doit être incrémentale (un message ajouté n'implique pas de réécrire toute la session), et la lecture doit permettre de récupérer l'intégralité de l'historique d'une session donnée en une seule requête. Aucune infrastructure supplémentaire ne doit être introduite : la persistance continue de reposer sur le même fichier SQLite local que le reste des métadonnées. Critère de succès : une session créée, alimentée de plusieurs échanges, puis suivie d'un redémarrage complet du serveur, permet de retrouver l'intégralité de l'historique d'une session à l'identique, dans le bon ordre."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Conversation survives a server restart (Priority: P1)

A team member is chatting with the wiki about the analyzed repository. Several
questions and answers have already been exchanged. The local server is then
restarted (e.g. the operator re-runs `repo-scanner serve`, or the process
crashes and is relaunched). The reader returns to the same session and finds
the full conversation exactly as it was, in the original order, before asking
their next question.

**Why this priority**: This is the entire point of the feature — without it,
every restart silently discards conversation history, which is the concrete
pain point the request describes.

**Independent Test**: Create a session, exchange several question/answer
pairs, stop and restart the server process, then fetch the session's history
again. It must match the pre-restart history exactly, in the same order.

**Acceptance Scenarios**:

1. **Given** a session with three exchanged messages, **When** the server
   process is fully stopped and restarted, **Then** requesting that session's
   history returns all three messages, in their original chronological order,
   with role, content, citations, and timestamp unchanged.
2. **Given** a freshly restarted server and a session id that was never
   created, **When** its history is requested, **Then** the system reports
   the session as not found rather than returning an empty history.

---

### User Story 2 - Conversation survives a wiki page reload (Priority: P1)

A reader is asking questions in the wiki's chat panel. They reload the page
(or reopen it later) without the server restarting. The conversation they had
is still there, so they don't have to re-ask what they already asked or lose
the answers and citations they were given.

**Why this priority**: Page reloads are far more frequent than server
restarts and are equally destructive today, since the session id currently
lives only in the browser tab's memory.

**Independent Test**: Create a session, exchange messages, reload the wiki
page while the server keeps running, and confirm the same conversation
reappears without creating a new, empty session.

**Acceptance Scenarios**:

1. **Given** an active session with prior messages, **When** the wiki page is
   reloaded, **Then** the reader sees the same conversation history restored,
   in order, rather than a blank chat panel.

---

### User Story 3 - Each new message is saved without rewriting history (Priority: P2)

As a conversation grows long (many question/answer pairs), adding one more
message must not require re-saving everything that came before it.

**Why this priority**: This is a durability/robustness property rather than a
user-visible feature on its own, but it directly protects User Stories 1 and
2 from partial-write corruption and keeps the chat responsive as history
grows — the request calls it out explicitly as a hard requirement.

**Independent Test**: Append messages to a session one at a time and confirm
that persisting a new message does not touch or require rewriting previously
stored messages (verified by confirming prior messages remain retrievable
and unchanged after each append, including after an interruption between
appends).

**Acceptance Scenarios**:

1. **Given** a session with N already-persisted messages, **When** one new
   message is added, **Then** the N existing messages remain retrievable and
   unchanged, and the new message appears after them in the history.
2. **Given** a session in the middle of being written to, **When** the
   process stops before a given message finishes persisting, **Then** all
   previously completed messages remain intact and retrievable on restart.

---

### Edge Cases

- What happens when a session is created but no message is ever exchanged,
  and the server restarts? The session must still exist and be retrievable,
  with an empty message list.
- What happens when the history of a session with a very large number of
  messages is requested? The full history is still returned in one request,
  in chronological order.
- What happens when two messages are persisted with the same timestamp
  (clock resolution collision)? Chronological order must still be
  well-defined and stable (e.g. by falling back to insertion order).
- What happens when a message being appended has empty citation lists (no
  symbols or files cited)? It must persist and be retrieved correctly with
  empty citation lists, not as an error or missing message.
- What happens when the underlying metadata storage file is missing or was
  never initialized (very first run)? Session persistence must initialize
  its own storage the same way the rest of the metadata store does, without
  requiring a separate setup step.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST persist every chat session with a stable,
  unique session identifier that remains valid across server restarts.
- **FR-002**: System MUST persist every chat message (both user questions and
  generated assistant responses) belonging to a session, recording at least:
  the message's role (user or assistant), its full text content, the list of
  cited symbol identifiers, the list of cited file paths, and a timestamp.
- **FR-003**: System MUST preserve and be able to reconstruct the exact
  chronological order in which messages were exchanged within a session.
- **FR-004**: System MUST persist a new message as an incremental write that
  does not require rewriting or re-persisting the session's previously
  stored messages.
- **FR-005**: System MUST be able to retrieve the complete message history of
  a given session in a single read operation.
- **FR-006**: System MUST make a session's persisted history available again
  after a full server restart, identical in content and order to what was
  persisted before the restart.
- **FR-007**: System MUST make a session's persisted history retrievable
  again after the wiki page is reloaded, without requiring the server to
  restart, by allowing the client to resume a previously created session
  rather than always creating a new one.
- **FR-008**: System MUST distinguish between a session that does not exist
  and a session that exists but has no messages yet, when history is
  requested.
- **FR-009**: System MUST use the same local SQLite-backed metadata storage
  already used for the rest of the repository's metadata — no additional
  storage engine, external service, or infrastructure component may be
  introduced for this feature.
- **FR-010**: System MUST continue to operate fully offline and bound to the
  local machine, consistent with the rest of the tool: session and message
  persistence introduces no network dependency. (Satisfied structurally — no
  new network-facing surface is introduced — and already exercised by the
  project's existing local-only network-boundary tests; no feature-specific
  test is needed for this requirement on its own.)

### Key Entities

- **Chat Session**: A single ongoing conversation between a reader and the
  chat assistant, scoped to one analyzed repository. Identified by a stable
  session id. Has zero or more chat messages, in chronological order.
- **Chat Message**: One turn in a chat session — either a user's question or
  an assistant's generated answer. Carries a role (user/assistant), its text
  content, the ordered list of cited symbol ids, the ordered list of cited
  file paths that justify the answer, and the timestamp at which it was
  recorded. Belongs to exactly one Chat Session and has a well-defined
  position in that session's chronological order.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A session created, given several exchanges, and followed by a
  full server restart, yields the identical message history — same messages,
  same content, same citations, same order — as before the restart, 100% of
  the time.
- **SC-002**: A reader who reloads the wiki page mid-conversation sees their
  prior conversation restored rather than an empty chat, with no manual
  action required beyond the reload itself.
- **SC-003**: Appending a new message takes about the same amount of time
  whether the session already has 1 prior message or 500 — the time to
  append does not grow as the conversation gets longer, verified by
  comparing append time near the start and near the end of a 500-message
  session.
- **SC-004**: Retrieving a session's full history is always a single request
  from the client's perspective, regardless of how many messages the session
  contains.

## Assumptions

- The existing chat session id (already generated when a session is created,
  per feature 014-local-chat-api) is reused as the stable identifier for
  persistence — no new id scheme is introduced.
- "Server restart" means the `repo-scanner serve`/`index` process stops and
  is relaunched against the same repository's already-indexed state; it does
  not cover switching to a different repository or deleting the repository's
  stored state.
- Persisted sessions are scoped per analyzed repository, consistent with how
  the rest of the metadata store (scan inventory, symbols, summaries) is
  already scoped.
- Resuming a session after a page reload relies on the client retaining and
  resending the session id it was given (e.g. via local browser storage);
  no user-facing login or identity system is introduced.
- There is no requirement in this feature to list, browse, delete, or expire
  past sessions — only to create, append to, and fully retrieve one session's
  history. Session lifecycle/cleanup is out of scope unless specified later.
- No message-editing or message-deletion capability is introduced; messages
  are append-only once persisted.
