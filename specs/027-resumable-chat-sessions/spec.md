# Feature Specification: Resumable Chat Sessions via Streaming, Listing & History

**Feature Branch**: `027-resumable-chat-sessions`

**Created**: 2026-08-25

**Status**: Draft

**Input**: User description: "Étendre l'API de chat (Partie 4.3) pour exposer, en plus de l'échange question/réponse existant, un mode de réponse en flux permettant au client de recevoir les tokens de la réponse au fur et à mesure de leur génération par le pipeline (Partie 3.4), plutôt que d'attendre la réponse complète. L'API doit aussi exposer la liste des sessions existantes et l'historique complet des messages d'une session donnée (Partie 2.1), pour permettre à un client de reprendre une conversation après une déconnexion ou un rechargement de page. Ces nouvelles routes restent soumises à la même contrainte que le reste de l'API : accessibles uniquement depuis la machine locale ou le réseau interne, jamais exposées publiquement par défaut. Critère de succès : un client HTTP local ouvrant la route de streaming reçoit les fragments de réponse progressivement plutôt qu'en un seul bloc final ; après fermeture puis réouverture de la connexion, ce même client peut récupérer l'historique complet et identique de la session via les nouvelles routes de lecture."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rediscover and resume a conversation after reconnecting (Priority: P1)

A team member has an ongoing chat conversation with the assistant. Their
browser tab is closed, the page is reloaded, or the connection drops for any
reason. When they come back, they have no record of which conversation they
were in — only the server does. They need a way to see what conversations
exist and pick the one they were just in, then see its complete prior
exchange again before continuing, exactly as it was.

**Why this priority**: This is the actual gap in today's API. A single
session's history can already be replayed once you know its identifier, but
there is no way for a client that lost track of that identifier to discover
it again. Without this, a reload or reconnect is effectively a dead end for
resuming — the client would have to start a brand-new conversation. This is
independently valuable and testable on its own, regardless of whether
answers are streamed or delivered in one block.

**Independent Test**: With one or more sessions already containing prior
messages, reconnect as a new client instance (no session identifier held in
memory) and confirm it can retrieve the list of existing sessions, identify
the right one, and pull back that session's complete, correctly ordered
message history, identical to what was there before disconnecting.

**Acceptance Scenarios**:

1. **Given** at least one chat session exists with prior messages, **When** a
   client asks for the list of existing sessions, **Then** it receives every
   existing session's identifier along with enough information (such as
   when it was created and when it was last active) to tell them apart and
   pick the right one to resume.
2. **Given** a client has picked a session identifier from that list,
   **When** it asks for that session's message history, **Then** it receives
   the complete, correctly ordered set of prior messages — identical in
   content and order to what the conversation actually contained.
3. **Given** no chat sessions exist yet, **When** a client asks for the list
   of existing sessions, **Then** it receives an empty list rather than an
   error.
4. **Given** a client asks for the history of a session identifier that does
   not exist, **When** the request is made, **Then** it receives a clear
   "not found" response rather than an empty or fabricated history.
5. **Given** the server has been restarted since the client last
   disconnected, **When** the client lists sessions and resumes one,
   **Then** the session and its history are exactly as they were before the
   restart.

---

### User Story 2 - Watch the answer arrive as it's generated (Priority: P2)

A team member asks the chat a question and, instead of a silent wait
followed by the entire answer appearing at once, sees the reply build up
progressively, piece by piece, as the assistant produces it.

**Why this priority**: This materially improves the experience of asking a
question — especially longer answers — by removing the "is it stuck?"
uncertainty of a long blocking wait. It is independent of session
discovery/resume (User Story 1): it can be exercised on any single session
regardless of whether the client found that session through starting a new
conversation or through resuming an existing one.

**Independent Test**: Ask a question on an existing session using the
progressive-delivery mode of the question/answer capability, and confirm
the reply arrives as a sequence of progressively delivered fragments rather
than a single block, with the fragments — once concatenated in arrival
order — reconstructing the exact same answer text and citations a
complete, non-progressive exchange would have produced.

**Acceptance Scenarios**:

1. **Given** an existing session and a question the configured model can
   answer, **When** the question is submitted for progressive delivery,
   **Then** the client receives the first fragment of the answer well
   before the full answer is complete, followed by the remaining fragments
   progressively until generation finishes.
2. **Given** the same interaction, **When** all received fragments are
   concatenated in the order received, **Then** the resulting text and its
   cited symbols/files match what a complete, non-progressive answer to the
   same question would have contained.
3. **Given** the configured model is unavailable, **When** a question is
   submitted for progressive delivery, **Then** the client receives a clear
   "unavailable" error rather than a partial, hanging, or silently failed
   exchange.

---

### User Story 3 - New capabilities stay as local-only as the rest of the API (Priority: P3)

An operator relies on the chat API never being reachable from outside the
local machine or their internal network. The new session-listing and
history-recovery capabilities must uphold that same guarantee — they are
not a side door that quietly changes the API's exposure.

**Why this priority**: This is a safety guarantee rather than new
user-facing value, and it extends a constraint the API already enforces
everywhere else, so the risk of it being overlooked specifically for the
new capabilities is what earns it its own story rather than being assumed
as a given.

**Independent Test**: With the API running under its default local-only
configuration, confirm that the session-listing and session-history
capabilities behave identically to the existing capabilities with respect
to network reachability — reachable from the local machine/internal
network, and not reachable from outside it — with no separate exposure
setting for them specifically.

**Acceptance Scenarios**:

1. **Given** the API is running under its default configuration, **When**
   the new session-listing or session-history capabilities are used from
   the local machine or internal network, **Then** the request succeeds
   like any other chat API interaction.
2. **Given** the same default configuration, **When** a connection to those
   same capabilities is attempted from outside the local machine or
   internal network, **Then** it is refused the same way the existing
   capabilities already refuse such connections.

---

### Edge Cases

- What happens when a client lists sessions while many sessions have
  accumulated over a long period of use? The list still returns promptly
  and remains ordered so the most recently active conversations are easy to
  find first.
- What happens when a client asks for the history of a session that exists
  but has zero messages yet (just created, nothing asked)? It receives an
  empty message list, not an error.
- What happens if a client is actively receiving a progressively delivered
  answer and the connection drops mid-delivery? No partial answer is added
  to the session's history; a subsequent history read for that session does
  not show a half-finished answer.
- What happens when a client resumes a session and continues asking
  questions in it? The newly asked questions and their answers are appended
  to the same session's history, after the previously resumed messages, in
  correct order.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The API MUST allow a client to list all existing chat
  sessions, each identified unambiguously and accompanied by enough
  information (at minimum, when it was created and when it was last active)
  for a client to distinguish sessions from one another and pick the right
  one to resume.
- **FR-002**: The session list MUST reflect actually persisted sessions —
  including sessions created in a previous server run — not just sessions
  created since the server last started.
- **FR-003**: The API MUST allow a client to retrieve the complete,
  correctly ordered message history of any existing session by its
  identifier, producing the same result this capability already produces
  today for a session whose identifier is already known.
- **FR-004**: A request for the history of a session identifier that does
  not exist MUST fail clearly (matching the existing "session not found"
  behavior of the current chat API), rather than returning an empty or
  fabricated history.
- **FR-005**: The API MUST allow a client to submit a question and receive
  the answer delivered progressively, as a sequence of fragments generated
  over time, rather than only as one complete block once generation
  finishes.
- **FR-006**: The fragments delivered by the progressive-delivery mode
  MUST, once concatenated in the order received, reconstruct the identical
  answer text and cited symbols/files that the same question would produce
  through a complete, non-progressive exchange.
- **FR-007**: If answer generation fails partway through a progressively
  delivered response, the system MUST surface a clear error to the client
  and MUST NOT record a partial or incomplete answer into that session's
  persisted history.
- **FR-008**: The session-listing and session-history capabilities MUST be
  reachable only from the local machine or the user's local/internal
  network by default, matching the access restriction already enforced by
  the rest of the chat API, with no public exposure by default and no
  separate exposure configuration for them.
- **FR-009**: Existing chat API behavior that callers already depend on
  (session creation, non-progressive question answering, per-session
  history retrieval, citation behavior, "session not found" errors) MUST
  remain unchanged for any caller not using the new progressive-delivery or
  listing capabilities.

### Key Entities

- **Chat Session (existing entity, newly listable)**: A single ongoing
  conversation, identified by a unique identifier, with a creation time and
  a last-activity time. Previously only retrievable one at a time by a
  caller who already knew its identifier; this feature adds the ability to
  discover all existing sessions collectively.
- **Chat Message (existing entity, unchanged)**: One turn (question or
  answer) within a session's history, including, for answers, the cited
  symbols/files backing it. Progressive delivery changes how an answer's
  content arrives over time, not the final content or structure of the
  message once complete.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A client that has lost track of which session it was using
  (for example, after a page reload) can find that session again from the
  full list of existing sessions and recover its complete, identical prior
  history, without needing to have stored the session identifier anywhere
  outside the server itself.
- **SC-002**: The time between a question being submitted for progressive
  delivery and the first fragment of its answer arriving stays roughly
  constant, regardless of how long the eventual complete answer turns out
  to be — it does not grow the way waiting for the full answer does.
- **SC-003**: Concatenating every fragment of a progressively delivered
  answer, in the order it arrived, always reproduces exactly the same
  answer text and citations that the equivalent complete, non-progressive
  exchange would have produced, with zero observed mismatches across
  repeated tests.
- **SC-004**: No request to the session-listing or session-history
  capabilities from outside the local machine or local/internal network is
  ever accepted, matching the existing chat API's local-only guarantee with
  zero exceptions observed in testing.
- **SC-005**: Listing existing sessions and retrieving a chosen session's
  full history together take no more than 2 seconds for a client to
  complete, so resuming a conversation after reconnecting feels immediate
  rather than like a fresh cold start.

## Assumptions

- Session listing and per-session history retrieval, and the local-only
  network restriction, build directly on capabilities already delivered by
  prior features (session creation and non-progressive answering with
  per-session history in spec 014; message persistence across restarts in
  spec 025; a progressive-delivery-capable answer-generation pipeline in
  spec 026). Where those capabilities already satisfy a requirement here,
  this feature confirms and exposes them rather than rebuilding them from
  scratch.
- The session list is returned in full, ordered by most-recently-active
  first, with no pagination — consistent with a single local user
  accumulating a moderate number of sessions over time, rather than a
  multi-tenant system with unbounded session growth.
- No authentication or per-session access control is introduced beyond the
  existing local-machine/local-network restriction — any local client that
  can already reach the chat API can already see all sessions, matching
  today's single-user trust model.
- Progressive delivery and complete-answer delivery MAY be offered as one
  interaction with a response mode, or as two distinct interactions — this
  specification does not mandate which, only that both a progressive and a
  complete-answer-equivalent experience are available to callers.
