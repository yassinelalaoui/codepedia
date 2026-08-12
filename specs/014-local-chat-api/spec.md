# Feature Specification: Local Chat API

**Feature Branch**: `014-local-chat-api`

**Created**: 2026-08-12

**Status**: Draft

**Input**: User description: "Construire une API backend exposant le pipeline RAG local sous forme de service de chat consommable par l'interface web. L'API doit permettre de créer une session de chat, d'envoyer une question et de recevoir la réponse générée avec la liste des symboles/fichiers cités en justification, et de consulter l'historique des messages d'une session. L'API ne doit être accessible que depuis la machine locale ou le réseau interne de l'utilisateur, jamais exposée publiquement par défaut. Critère de succès : un client HTTP local peut créer une session, poser une question et recevoir une réponse structurée incluant le texte généré et les identifiants des symboles cités, sans qu'aucune requête ne sorte du réseau local."

## Overview

Expose the existing local RAG pipeline (question answering with cited evidence)
as an HTTP backend service that a web interface can consume. A local client
must be able to create a chat session, submit a question and receive the
generated answer together with the symbols and files cited as justification,
and retrieve the message history of a session. The API must remain reachable
only from the local machine or the user's local network, and must never be
exposed publicly by default.

## Goals

- Let a local HTTP client create a chat session backed by the existing local
  RAG pipeline.
- Let a client submit a question to a session and receive a structured answer
  that includes the generated text and the cited symbols/files separately from
  the prose.
- Let a client retrieve the ordered message history of a session.
- Restrict all access to the local machine or the user's local network by
  default, with no public exposure.
- Reuse the existing local retrieval, generation, and citation pipeline rather
  than reimplementing it.

## Non-Goals

- Building the web interface itself; this feature is the backend service only.
- Multi-user authentication or authorization beyond trusting the local
  machine/network.
- Sharing sessions with other machines or users over the public internet.
- Rate limiting or hardening intended for a public-internet-facing deployment.
- Changing how the underlying RAG pipeline retrieves evidence or generates
  answers.

## User Stories

### US1 - Start a chat session

As a developer using the local web interface, I want to create a new chat
session so that I can begin asking questions about the indexed repository.

Acceptance criteria:

- A client can request creation of a new session and receive a unique session
  identifier in the response.
- A newly created session starts with an empty message history.
- The returned session identifier can immediately be used to ask a question or
  read history.

### US2 - Ask a question and receive a structured, cited answer

As a developer, I want to send a question to an existing session and receive
the generated answer along with the exact symbols and files cited, so that my
web UI can render the answer and its evidence links separately.

Acceptance criteria:

- Submitting a question to an existing session returns the generated answer
  text.
- The response includes the distinct cited symbol identifiers and cited file
  paths as structured fields, not only embedded in the answer text.
- The question and the generated answer are appended, in order, to the
  session's message history.
- If the local embedding engine or local model is unavailable, the client
  receives an explicit, structured error instead of a partial or fabricated
  answer, and nothing is added to the session history.

### US3 - Review a session's message history

As a developer, I want to fetch the full history of a chat session so that my
web UI can display the conversation so far, for example after a page reload.

Acceptance criteria:

- A client can request the message history of a session by its identifier.
- The history preserves the original order and role (user or assistant) of
  each message.
- Each assistant message in the history includes its citations.
- Requesting the history of an unknown session identifier returns a clear
  not-found error rather than an empty success response.

### Edge Cases

- What happens when a question is submitted to a session identifier that does
  not exist? The client receives a clear not-found error and no session is
  created implicitly.
- What happens when the local embedding engine or local model is unavailable
  at question time? The client receives an explicit failure response before
  any answer text is generated, and neither the question nor a partial answer
  is recorded in the session history.
- What happens when a client requests the history of a session that has no
  messages yet? The client receives a successful response with an empty
  message list, not an error.
- What happens when a client submits an empty or whitespace-only question?
  The request is rejected with a clear validation error.
- What happens when a request originates from outside the local machine or
  the user's local network? The connection is not accepted, consistent with
  the default local-only binding.

## Requirements *(mandatory)*

### Functional Requirements

#### Session management

- The API MUST allow a client to create a new chat session and MUST return a
  unique session identifier for it.
- The API MUST allow a client to retrieve the ordered message history of an
  existing session by its identifier.
- The API MUST return a clear not-found error when a client references a
  session identifier that does not exist.

#### Question answering

- The API MUST allow a client to submit a natural-language question to an
  existing session.
- The API MUST return the generated answer text for the submitted question.
- The API MUST return, alongside the answer text, the symbols and files that
  justify the answer, structured per the Response structure and traceability
  requirements below.
- The API MUST append the submitted question and the generated answer, in
  order, to the session's message history once the answer is produced.
- The API MUST return an explicit, structured error, and MUST NOT return a
  fabricated or partial answer, when the local embedding engine or local
  model is unavailable.
- The API MUST reject empty or whitespace-only questions with a clear
  validation error.

#### Local-only network access

- The API MUST bind only to the local machine (localhost) or addresses within
  the user's local/private network by default.
- The API MUST NOT be reachable from the public internet by default, and MUST
  require an explicit, separate action from the user to change that.
- The API MUST NOT send repository content, questions, or generated answers to
  any host outside the local machine or the user's local network while
  handling a request.

#### Response structure and traceability

- Every answer response MUST expose the distinct list of cited symbol
  identifiers and cited file paths that justify the answer, as structured
  fields distinct from the free-text answer.
- The session history response MUST preserve the distinction between user and
  assistant messages and MUST include citations on assistant messages.

### Key Entities *(include if feature involves data)*

- **ChatSessionResource**: The API-visible chat session — an identifier and
  its ordered message history — backed by the existing local RAG pipeline.
- **QuestionRequest**: An incoming client request asking a question within a
  given session.
- **AnswerResponse**: The structured response to a question, containing the
  generated answer text plus the distinct cited symbol identifiers and file
  paths.
- **SessionHistoryResponse**: The ordered list of prior messages (user and
  assistant) for a session, including citations where applicable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- A local HTTP client can create a session, ask a question, and receive a
  structured response containing the generated answer text and the cited
  symbol identifiers in a single request/response cycle per action.
- No request or response involved in creating a session, asking a question, or
  reading history is observed leaving the local machine or the user's local
  network.
- A client can retrieve a session's full message history and see it match the
  order of the questions and answers previously submitted to that session.
- An attempt to reach the API from outside the local machine or local network
  fails to connect by default, without any additional configuration by the
  user.
- When the local model or local embedding engine is unavailable, a client
  asking a question receives an explicit error response within the same
  request cycle, and no fabricated answer is returned.

## Assumptions

- The local retrieval, generation, and citation pipeline already exists and is
  reused as-is; this feature only adds an HTTP layer on top of it.
- Sessions live for the lifetime of the running local service; no additional
  cross-restart persistence guarantee is required beyond what the underlying
  pipeline already provides.
- A single local user operates the API at a time; concurrent multi-user access
  control is out of scope.
- "Local network" means the user's own private network, reachable without
  traversing the public internet (excludes port-forwarding or public cloud
  exposure of the service).
- The web interface that will consume this API is a separate, already-planned
  component and is out of scope for this feature.