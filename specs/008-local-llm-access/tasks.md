# Tasks: Local LLM Access Layer

## Implementation Strategy

Build the local LLM access layer in vertical slices. Start with the package
scaffold and shared error/model types, then add the local HTTP transport and
availability check, then implement prompt generation, and finish by wiring the
shared engine into indexing and chat flows with explicit offline failure
handling.

## Dependencies

1. Setup must complete before any implementation work.
2. Foundational models, transport helpers, and error types must exist before
   the engine API is wired.
3. User Story 1 establishes the explicit local availability check.
4. User Story 2 establishes prompt generation through the local backend.
5. User Story 3 ensures both indexing summaries and chat reuse the same local
   engine and failure behavior.

## Parallel Opportunities

- Setup: package scaffold and fixture/documentation prep can be prepared in
  parallel.
- Foundational: models, errors, and transport helpers can be built in parallel
  after the package scaffold exists.
- User Story 1: availability logic and local endpoint validation can be
  implemented alongside the contract surface.
- User Story 2: prompt payload handling and generation response parsing can be
  implemented alongside shared client wiring.
- User Story 3: summary-generation integration and chat integration can be
  prepared in parallel once the shared engine exists.

## Phase 1: Setup

- [X] T001 Create the local LLM package scaffold in `src/local_llm/__init__.py`, `src/local_llm/engine.py`, `src/local_llm/errors.py`, `src/local_llm/models.py`, and `src/local_llm/transport.py`.
- [X] T002 Prepare feature documentation placeholders in `specs/008-local-llm-access/research.md`, `specs/008-local-llm-access/data-model.md`, `specs/008-local-llm-access/contracts/local-llm-engine.md`, and `specs/008-local-llm-access/quickstart.md` if any field names or endpoint details need to be aligned during implementation.
- [X] T003 Verify the project uses only local HTTP and standard-library dependencies for this feature in `pyproject.toml` and the local LLM package structure.

## Phase 2: Foundational

- [X] T004 Define the core local LLM data models in `src/local_llm/models.py` for `PromptEnvelope`, `GenerationResult`, and `AvailabilityStatus`.
- [X] T005 Define explicit local-only error types in `src/local_llm/errors.py` for service unavailability, missing model, invalid response, and generation failure.
- [X] T006 [P] Implement the local HTTP transport helpers in `src/local_llm/transport.py` for `GET /api/version`, `GET /api/tags`, and `POST /api/generate`.
- [X] T007 [P] Define the configuration and validation helpers for model name and endpoint URL handling in `src/local_llm/models.py`.

## Phase 3: User Story 1 - Check local model availability

Story goal: verify that the local model service is running before any prompt
is sent, so the tool fails fast with a clear local-only error when Ollama or
llama.cpp is offline.

Independent test criteria: a local availability check can detect a stopped
service, confirm a running service, and report model absence without contacting
any external service.

- [X] T008 [US1] Implement `LocalLLMEngine.isAvailableLocally()` in `src/local_llm/engine.py` to check the configured local endpoint before generation.
- [X] T009 [P] [US1] Implement local service reachability and model-presence checks in `src/local_llm/transport.py` using the configured `endpointUrl` and `modelName`.
- [X] T010 [US1] Route availability failures through explicit local-only error messages in `src/local_llm/errors.py` and `src/local_llm/engine.py`.

## Phase 4: User Story 2 - Generate text from a local prompt

Story goal: send a prompt with context to the local model and receive a plain
text natural-language response for summaries and chat.

Independent test criteria: a prompt envelope can be serialized locally, sent to
the model, and parsed back into a generated text response without any cloud
fallback.

- [X] T011 [US2] Implement `LocalLLMEngine.generate(prompt)` in `src/local_llm/engine.py` for non-streaming local text generation.
- [X] T012 [P] [US2] Implement prompt assembly and JSON payload serialization in `src/local_llm/models.py` and `src/local_llm/transport.py` for text plus context.
- [X] T013 [US2] Implement response parsing and invalid-payload handling in `src/local_llm/transport.py` and `src/local_llm/models.py`.
- [X] T014 [US2] Ensure generation errors surface as explicit local-only failures in `src/local_llm/errors.py` and `src/local_llm/engine.py`.

## Phase 5: User Story 3 - Reuse the same layer for summaries and chat

Story goal: reuse one local-only engine for both code-summary generation during
indexing and answer generation in chat so both flows behave identically.

Independent test criteria: both the indexing summary path and the chat reply
path use `LocalLLMEngine`, fail fast when the model is unavailable, and never
silently fall back to a cloud provider.

- [ ] T015 [US3] Integrate `LocalLLMEngine` into the code-summary generation path in the real indexing call site once the repository's actual summary pipeline is identified.
- [ ] T016 [US3] Integrate `LocalLLMEngine` into the chat response path in the real chat call site once the repository's actual chat pipeline is identified.
- [X] T017 [P] [US3] Add a small shared wrapper or factory in `src/local_llm/__init__.py` so both product paths construct the engine consistently.

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T018 Align `src/local_llm/models.py`, `src/local_llm/errors.py`, `src/local_llm/transport.py`, and `src/local_llm/engine.py` with the final field names and local-only error wording from `specs/008-local-llm-access/spec.md`.
- [X] T019 Update `specs/008-local-llm-access/research.md`, `specs/008-local-llm-access/data-model.md`, `specs/008-local-llm-access/contracts/local-llm-engine.md`, and `specs/008-local-llm-access/quickstart.md` so they match the final engine behavior and endpoint choices.
- [ ] T020 Verify the full feature against the local Ollama quickstart scenarios in `specs/008-local-llm-access/quickstart.md`, including the stopped-service failure case.
