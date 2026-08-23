# Feature Specification: Chat Streaming & Conversational Context Retrieval

**Feature Branch**: `026-chat-streaming-context`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "Faire évoluer le pipeline RAG (Partie 3.4) sur deux points indépendants. Premièrement, la génération de la réponse ne doit plus être bloquante de bout en bout : le moteur LLM (Partie 3.1, local ou cloud) doit exposer un mode de génération en flux, produisant les tokens de la réponse au fur et à mesure qu'ils sont générés plutôt qu'en un seul bloc à la fin, afin que l'appelant (l'API, Partie 4.3) puisse les retransmettre progressivement. Deuxièmement, la recherche par similarité ne doit plus se limiter à la dernière question posée : lorsqu'une session contient déjà des échanges précédents, la requête envoyée à l'index vectoriel local doit être enrichie du contexte conversationnel pertinent (questions/réponses récentes), pour qu'une question de suivi elliptique (ex. "et pour l'autre ?") retrouve correctement les fragments pertinents plutôt que des résultats non liés. Cet enrichissement doit rester entièrement local, sans appel réseau supplémentaire au-delà du moteur LLM déjà configuré. Le comportement de citation explicite des symboles/fichiers sources reste inchangé et continue de s'appliquer à la réponse complète une fois assemblée. Critère de succès : sur une question de suivi faisant référence implicitement à un échange précédent de la même session, les fragments récupérés correspondent bien au sujet réel de la question de suivi ; et sur une question simple, les premiers tokens de la réponse sont disponibles nettement avant la fin de la génération complète, mesurable via le délai entre l'envoi de la question et le premier fragment de réponse reçu."

## Clarifications

### Session 2026-08-19

- Q: How should SC-002's "well before the end" claim be measured, so it's a testable target rather than a vague comparison? → A: Time-to-first-fragment stays roughly flat regardless of how long the final answer turns out to be — it does not grow the way waiting for the complete answer does.
- Q: How much of the recent conversation should be used to enrich a follow-up's search query? → A: A small, fixed number of the most recent exchanges (e.g., the last 2-3 question/answer pairs), regardless of how long the session has gotten.
- Q: If answer generation fails partway through streaming (the model itself erroring out mid-stream, not a client disconnect), what should happen to the partial output and the session history? → A: Discard the partial output and surface a clear error; nothing is added to the session's history for that failed attempt, matching today's failure behavior.
- Q: (raised during `/speckit-plan`) Should a remote/cloud LLM engine actually be added as a second, real answer-generation option? → A: Yes — an explicit, opt-in remote engine is in scope, never on by default and never used as an automatic fallback for the local engine. This required amending the project constitution (2.1/2.3, now v2.0.0) to permit a narrow, user-configured exception; the analysis/indexing pipeline remains local-only with no exception.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Progressive answer delivery instead of a silent wait (Priority: P1)

A team member asks the chat a question. Instead of staring at a loading state
until the entire answer is ready, they start seeing the beginning of the
answer almost immediately, with the rest arriving progressively as it is
generated, the same way a person typing an answer produces it word by word
rather than all at once.

**Why this priority**: This directly addresses the "long silent wait" pain
point the request calls out, and it is independently valuable and
independently testable regardless of any retrieval-quality change — it can
be verified with today's existing retrieval behavior unchanged.

**Independent Test**: Ask a question the currently configured model (local by
default, or an explicitly configured remote engine — see the streaming
engine's configuration scenario below) can answer, and confirm that the
reply arrives as a sequence of fragments over time rather than a single
block, with the first fragment arriving well before generation finishes,
and that the fragments concatenate back into the same complete answer and
citations a caller would have received before.

**Acceptance Scenarios**:

1. **Given** a session and a question the configured model can answer,
   **When** the answer is generated, **Then** the caller receives a first
   fragment of the response noticeably before the full answer is complete,
   followed by the remaining fragments progressively until the answer is
   done — the same streaming behavior whether the configured engine is the
   local model or an explicitly configured remote one.
2. **Given** the same interaction, **When** all received fragments are
   concatenated in the order they arrived, **Then** the resulting text
   matches what today's single-block response would have produced, and the
   same cited symbols/files are attached once the complete answer is
   assembled.
3. **Given** the configured model engine is unavailable, **When** a question
   is asked, **Then** the caller still receives today's clear "unavailable"
   error rather than a partial, hanging, or silently-failing stream, and the
   system never silently tries a different engine than the one configured.

---

### User Story 2 - Follow-up questions retrieve the right evidence (Priority: P1)

A team member has already asked about one thing in a session, then asks a
short, elliptical follow-up that only makes sense in light of what was just
discussed (for example, "what about the other one?"). The search for
relevant code still finds the right material, because it accounts for the
recent conversation instead of treating the follow-up question as if it
arrived out of nowhere.

**Why this priority**: This is independently valuable and independently
testable — it can be verified using today's existing (non-streaming) answer
generation, with no dependency on User Story 1. It directly fixes a
correctness gap: elliptical follow-ups currently retrieve unrelated results.

**Independent Test**: Ask an initial question that surfaces known evidence,
then ask a deliberately elliptical follow-up question, and confirm the
retrieved evidence matches the follow-up's real intended subject rather than
being unrelated or generic.

**Acceptance Scenarios**:

1. **Given** a session with at least one prior exchanged question and
   answer, **When** a new, elliptical follow-up question is asked, **Then**
   the evidence retrieved for it is relevant to the real subject implied by
   the conversation so far, not just the literal words of the follow-up.
2. **Given** a brand-new session with no prior messages, **When** the first
   question is asked, **Then** retrieval behaves exactly as it does today,
   based on that question alone.
3. **Given** a session with several prior exchanges on unrelated topics,
   **When** a new question is asked that is fully self-contained (names its
   own subject explicitly, not elliptical), **Then** retrieval still
   correctly favors the new question's actual subject rather than being
   pulled toward unrelated older context.

---

### User Story 3 - Choosing an explicit remote engine for chat answers (Priority: P2)

An operator who wants faster or more capable answer generation than their
local hardware provides can choose to configure a remote (cloud) engine for
chat answers instead of the local one. Because this is a deliberate,
informed choice rather than something the system does on its own, the
operator is told clearly, at the moment they configure it, that this sends
the text of their questions and the cited code context in answers to a
third-party service.

**Why this priority**: This is an opt-in capability that most users will
never touch — the default, local-only behavior in User Stories 1 and 2 must
keep working completely unchanged for anyone who doesn't configure it. It is
independently testable: configuring (or not configuring) a remote engine can
be verified on its own, separately from streaming or retrieval enrichment.

**Independent Test**: With no remote engine configured, confirm chat answers
still come from the local model only. Then explicitly configure a remote
engine and confirm answers now come from it, that configuring it surfaces a
clear disclosure that content leaves the machine, and that removing the
configuration reverts to local-only behavior with no remaining remote usage.

**Acceptance Scenarios**:

1. **Given** no remote engine has been configured, **When** a question is
   asked, **Then** the answer is generated by the local model only, exactly
   as before this feature existed.
2. **Given** an operator is explicitly configuring a remote engine, **When**
   they do so, **Then** the system clearly discloses that questions and
   cited code context will be sent to that third-party service as part of
   completing the configuration.
3. **Given** a remote engine has been explicitly configured, **When** a
   question is asked, **Then** the answer is generated (and streamed, per
   User Story 1) using that configured engine, and only because of the
   operator's explicit configuration — never automatically.
4. **Given** a remote engine is configured but currently unreachable,
   **When** a question is asked, **Then** the system reports the configured
   engine as unavailable rather than silently using the local model instead.

---

### Edge Cases

- What happens when a session's conversation history grows very long? The
  conversational context used to enrich a search query must stay bounded to
  relevant/recent exchanges rather than growing without limit as the session
  gets longer.
- What happens when a follow-up question names a brand-new, unrelated
  subject rather than referring back to prior context? Enrichment must not
  force irrelevant older context into the search — the question's own
  subject still takes priority.
- What happens when evidence is insufficient or ambiguous for a (possibly
  context-enriched) query? Today's existing insufficient-evidence and
  ambiguous-evidence handling continues to apply unchanged, now evaluated
  against whatever the enriched search returns.
- What happens if a caller disconnects or stops listening while an answer is
  still streaming? Generation for that in-progress answer stops rather than
  continuing to run to completion for nobody.
- What happens to citations if streaming is interrupted partway through? Only
  a complete, fully-generated answer gets its citations attached and is
  recorded as the assistant's message; an interrupted stream does not
  produce a fabricated or partial citation list.
- What happens when the model itself fails partway through generating a
  streamed answer (as opposed to the caller disconnecting)? The partial
  output is discarded, a clear error is surfaced to the caller, and nothing
  is added to the session's history for that attempt — the same
  no-side-effect behavior today's non-streamed failures already have.
- What happens when the configured remote engine is unreachable while the
  local engine would have been able to answer? The system reports the
  configured engine as unavailable; it never silently substitutes a
  different engine than the one explicitly configured, in either direction.
- What happens to conversational-context enrichment (User Story 2) when a
  remote engine is configured? Enrichment itself remains local-only (FR-006)
  regardless of which engine ends up generating the answer — only the final
  answer-generation step may use the explicitly configured remote engine.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST be able to generate an assistant answer
  incrementally, in a sequence of fragments produced as they become
  available, rather than only ever as a single complete block delivered at
  the end.
- **FR-002**: System MUST make each generated fragment available to the
  caller as soon as it is produced, without waiting for the complete answer.
- **FR-003**: System MUST still assemble the complete answer text from the
  delivered fragments, in order, for citation attachment and for recording
  in the session's history — identical in content to what non-streamed
  generation would have produced.
- **FR-004**: System MUST continue to attach citations (cited symbols and
  file paths) to the complete, assembled answer only, once generation
  finishes — never to an individual in-progress fragment.
- **FR-005**: System MUST, when a chat session already has one or more prior
  exchanged messages, incorporate conversational context from a small, fixed
  number of the most recent exchanges (e.g., the last 2-3 question/answer
  pairs) into the query used for the similarity search for a new question —
  not the new question in isolation, and not the session's entire history.
- **FR-006**: System MUST perform this contextual enrichment via local text
  and citation-data concatenation only — no LLM call of any kind is made to
  build the search query, regardless of which engine (local or an
  explicitly configured remote one) is currently configured for answers.
- **FR-007**: System MUST perform the same plain (non-enriched) similarity
  search it does today when a session has no prior messages yet (the first
  question asked in a session).
- **FR-008**: System MUST retrieve evidence relevant to a follow-up
  question's real, implied subject even when that question refers to earlier
  context elliptically rather than naming its subject explicitly.
- **FR-009**: System MUST keep today's evidence-insufficiency and
  ambiguous-evidence detection behavior working unchanged, now applied to
  whichever evidence the (possibly context-enriched) search returns.
- **FR-010**: System MUST NOT introduce any new outbound network dependency
  for conversational-context enrichment (User Story 2) — enrichment stays
  local-only regardless of which answer-generation engine is configured.
- **FR-011**: System MUST discard the partial output and record no assistant
  message in the session's history when answer generation fails partway
  through streaming — matching today's behavior where a failed generation
  has no history side effect.
- **FR-012**: System MUST support, in addition to the local answer-generation
  engine, an explicitly configured remote (cloud) answer-generation engine as
  an alternative — never enabled by default, and only used when an operator
  has deliberately configured it.
- **FR-013**: System MUST clearly disclose, at the point an operator
  configures a remote engine, that doing so sends the text of questions and
  the cited code context in answers to a third-party service.
- **FR-014**: System MUST NOT automatically switch between the local engine
  and a configured remote engine (in either direction) when one is
  unavailable — unavailability of the currently configured engine is
  reported clearly, per today's existing behavior, never silently masked by
  substituting the other engine.
- **FR-015**: System MUST support streamed, incremental generation (FR-001)
  identically whether the currently configured answer-generation engine is
  the local model or an explicitly configured remote one.

### Key Entities

- **Streamed Answer Fragment**: One incremental, ordered piece of an
  in-progress assistant answer, made available to the caller as soon as it
  is produced. Concatenating every fragment for one answer, in the order
  delivered, reconstructs the complete answer text.
- **Conversationally-Enriched Search Query**: The query actually used for one
  question's similarity search — the question itself when a session has no
  prior history, or the question combined with relevant recent conversation
  context when prior exchanges exist in the same session.
- **Answer-Generation Engine Configuration**: Which engine currently
  generates chat answers — the local model by default, or an explicitly
  configured remote engine. Never both at once, never chosen automatically;
  only ever changed by an operator's deliberate configuration action.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a follow-up question that references a previous exchange in
  the same session only implicitly, the fragments retrieved match the
  follow-up's real subject, not the previous behavior's unrelated or
  generic results.
- **SC-002**: The delay between a question being sent and the first response
  fragment being received stays roughly flat regardless of how long the
  eventual complete answer turns out to be — unlike today, where that delay
  grows with the length of the full answer because nothing is visible until
  generation finishes. Verified by comparing the time-to-first-fragment for a
  short answer against a long answer and confirming they are comparable.
- **SC-003**: The complete answer content and its attached citations,
  reconstructed from all streamed fragments, match what a caller would have
  received from today's single-block response for the same question and
  evidence — streaming changes only how the answer arrives, not what it says.
- **SC-004**: A session's very first question (asked before any other
  exchange exists) continues to retrieve evidence exactly as it does today,
  with no change in behavior for that case.
- **SC-005**: With no remote engine configured, chat behavior (including
  streaming and retrieval) is indistinguishable from a setup where the
  remote-engine capability did not exist at all — the opt-in capability adds
  zero behavior change for operators who never configure it.

## Assumptions

- "Local or cloud" in the request is read literally: this feature adds
  streaming to the local engine and introduces one explicitly-configured
  remote (cloud) engine as an alternative, never a default and never an
  automatic fallback. This required amending the project constitution
  (principles 2.1/2.3, now version 2.0.0) to permit a narrow, opt-in
  exception for chat answer generation specifically — the analysis/indexing
  pipeline (parsing, embeddings, vector search) remains local-only with no
  exception, unaffected by this change.
- Conversational-context enrichment (User Story 2) stays local-only
  regardless of which engine is configured for answer generation (FR-010) —
  only the final answer-generation step is affected by the engine choice.
- This feature is scoped to the answer-generation engine and the chat API
  layer that calls it (the two parties the request explicitly names). Making
  the wiki's chat UI actually render fragments as they arrive, rather than
  waiting for the complete response, is a separate, follow-on concern and is
  out of scope here.
- The exact count within "a small, fixed number of recent exchanges" (FR-005)
  — e.g., whether it is 2 or 3 prior question/answer pairs — is a
  planning-level tuning decision; this spec fixes the shape (small, fixed,
  most-recent-first) rather than the precise number.
- Today's ability to get a single, complete answer (not consumed as a
  stream) is preserved for callers that need it — this feature adds
  progressive delivery as a capability; it does not remove the ability to
  obtain the final, complete, cited answer.
- The exact mechanism used to build the conversationally-enriched query
  (e.g., combining recent exchange text directly, or using the local model
  to condense it) is a planning-level decision; this spec only requires that
  the result stays local and improves retrieval for elliptical follow-ups.
