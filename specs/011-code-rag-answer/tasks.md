# Tasks: Local Code RAG Answering

## Phase 1: Setup

**Goal:** Create the chat package scaffolding and the shared message/session data structures.

**Independent test criteria:** The new `src/chat` package can be imported and exposes the core chat types without side effects.

- [X] T001 [P] Create `src/chat/models.py` with `ChatSession`, `ChatMessage`, `RetrievedEvidence`, `RAGContext`, and `Citation` dataclasses defined in the design docs.
- [X] T002 [P] Create `src/chat/__init__.py` to export the chat session and message types as the public API for the RAG feature.

## Phase 2: Foundational

**Goal:** Add the retrieval and prompt-assembly helpers needed before the session can answer questions.

**Independent test criteria:** The chat layer can build a prompt context from local evidence and validate local-model availability before answer generation begins.

- [X] T003 Create `src/chat/retrieval.py` with helpers that vectorize a question with `EmbeddingEngine`, run local similarity search against `VectorIndex`, and normalize the retrieved evidence.
- [X] T004 Create `src/chat/prompting.py` with helpers that assemble question, conversation history, retrieved evidence, and citation metadata into a `PromptEnvelope` for `LocalLLMEngine`.
- [X] T005 Create `src/chat/session.py` with the local availability check and shared orchestration hooks that the chat session will use before any answer is generated.

## Phase 3: User Story 1 - Ask a question about the indexed codebase

**Goal:** Let a developer ask a natural-language question and receive a useful, grounded answer.

**Independent test criteria:** Calling `ChatSession.ask(question)` returns a `ChatMessage` whose content answers the question and whose session history records the conversation in order.

- [X] T006 [US1] Implement `ChatSession.ask(question): ChatMessage` in `src/chat/session.py` so a question becomes a generated answer and both turns are appended to the session history.
- [X] T007 [US1] Implement session state management in `src/chat/session.py` so `ChatSession.messages` preserves chronological order and can be reused across follow-up questions.
- [X] T008 [US1] Add public exports for the chat session API in `src/chat/__init__.py` so callers can construct `ChatSession` and inspect `ChatMessage` objects directly.

## Phase 4: User Story 2 - Retrieve local evidence before answering

**Goal:** Retrieve the most relevant local fragments and summaries before generating the answer.

**Independent test criteria:** The answer pipeline uses only locally retrieved fragments and summaries, and the retrieved context is the one passed to the local model.

- [X] T009 [US2] Implement evidence ranking and selection in `src/chat/retrieval.py` so the chat pipeline keeps the most relevant code fragments and generated summaries for a question.
- [X] T010 [US2] Implement context assembly in `src/chat/prompting.py` so the retrieved evidence and conversation history are injected into the local prompt in a deterministic order.
- [X] T011 [US2] Wire `EmbeddingEngine`, `VectorIndex`, and `LocalLLMEngine` together in `src/chat/session.py` so question embedding, retrieval, and answer generation form a single local-only flow.

## Phase 5: User Story 3 - Stay local and cite evidence explicitly

**Goal:** Keep the entire flow local and surface the evidence used to justify each answer.

**Independent test criteria:** A generated answer names the files and symbols that supported it, and the pipeline fails explicitly when the local embedding engine or local LLM is unavailable.

- [X] T012 [US3] Implement citation extraction in `src/chat/session.py` so each assistant message records the source symbol ids and file paths used to justify the answer.
- [X] T013 [US3] Enforce local-only failure behavior in `src/chat/session.py` so the chat flow stops with an explicit error when `EmbeddingEngine.isAvailableLocally()` or `LocalLLMEngine.isAvailableLocally()` is false.
- [X] T014 [US3] Ensure the final answer text in `src/chat/prompting.py` and `src/chat/session.py` explicitly references the files and symbols used as evidence.

## Phase 6: Polish & Cross-Cutting Concerns

**Goal:** Make the chat flow easy to consume and verify from the rest of the codebase.

**Independent test criteria:** The feature's public API is coherent, the quickstart scenarios still match the implementation, and the new chat layer can be reused by the existing repository scanner product flow.

- [X] T015 Update `src/chat/__init__.py`, `src/chat/models.py`, and `src/chat/session.py` for stable public exports and clean type surfaces.
- [X] T016 Validate the end-to-end question-answer flow against the repository indexing path documented in `specs/011-code-rag-answer/quickstart.md` and fix any mismatches in `src/chat/retrieval.py`, `src/chat/prompting.py`, or `src/chat/session.py`.
- [X] T017 [US3] Add an integration validation in `tests/integration/test_chat_session.py` that proves a successful answer path emits no outbound network requests while still returning cited files and symbols.

## Dependencies

- `T001` and `T002` can run in parallel.
- `T003`, `T004`, and `T005` depend on the chat package scaffolding from Phase 1.
- `T006` depends on the foundational retrieval and prompting helpers from `T003` through `T005`.
- `T007` depends on `T006`.
- `T008` depends on `T006` and `T007`.
- `T009`, `T010`, and `T011` depend on the local retrieval and prompt context helpers being available.
- `T012` depends on `T011`.
- `T013` depends on the local availability checks implemented earlier in Phase 2 and Phase 4.
- `T014` and `T015` are final polish tasks after the main flow lands.
- `T017` depends on `T011` through `T016` and covers the explicit no-network success criterion.

## Parallel Execution Examples

### User Story 1

```text
Task: T006 -> implement ChatSession.ask in src/chat/session.py
Task: T007 -> implement message history management in src/chat/session.py
Task: T008 -> export the chat API in src/chat/__init__.py
```

### User Story 2

```text
Task: T009 -> implement retrieval ranking in src/chat/retrieval.py
Task: T010 -> assemble prompt context in src/chat/prompting.py
Task: T011 -> wire EmbeddingEngine, VectorIndex, and LocalLLMEngine in src/chat/session.py
```

### User Story 3

```text
Task: T012 -> capture citation ids in src/chat/session.py
Task: T014 -> ensure answer text includes file and symbol references in src/chat/prompting.py and src/chat/session.py
Task: T017 -> add no-network success validation in tests/integration/test_chat_session.py
```

## Implementation Strategy

1. Build the chat scaffolding and message/session model first so the new flow has a stable public surface.
2. Add retrieval and prompt assembly next so local evidence can be selected and injected into the local LLM.
3. Finish with citations and local-only failure handling so every answer is auditable and the feature never falls back to a non-local service.
4. Use the quickstart validation path as the final check that the whole retrieval-to-answer flow behaves like an interactive chat feature.

## Phase 7: Convergence

- [X] T018 Implement explicit insufficient-evidence handling in `src/chat/session.py` so `ChatSession.ask` states clearly when the repository lacks enough evidence to answer while still surfacing the nearest relevant local evidence, per spec.md Edge Cases and contracts/chat-session.md Failure expectations (missing)
- [X] T019 Implement ambiguity surfacing in `src/chat/retrieval.py` and `src/chat/session.py` so that when multiple fragments are similarly relevant, the answer mentions the ambiguity, per spec.md Edge Cases (missing)
- [X] T020 Implement multi-location citation coverage in `src/chat/retrieval.py` and `src/chat/prompting.py` so a capability spanning several files is cited at all directly relevant locations rather than only one, per spec.md Edge Cases (missing)
