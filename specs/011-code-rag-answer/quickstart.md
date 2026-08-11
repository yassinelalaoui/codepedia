# Quickstart: Local Code RAG Answering

## Prerequisites

- Python 3.11 or later
- Local project dependencies installed
- Local embedding model available on `http://localhost:11434`
- Local LLM available on `http://localhost:11434`
- A repository that has already been indexed into the local vector index

## Validate retrieval and answer generation

1. Start the local embedding service and the local LLM service.
2. Open an indexed repository that contains a known capability, such as
   authentication or repository scanning.
3. Create a chat session for that repository.
4. Ask a question such as "where is authentication handled?"
5. Confirm the response is a natural-language answer rather than a raw search
   result list.
6. Confirm the response cites the relevant files and symbols used to justify
   the answer.
7. Confirm the cited evidence matches the repository content.
8. Confirm the successful answer path does not emit any outbound network
   requests while still using only local evidence.

## Validate citation fidelity

1. Ask a second question that targets a different feature area.
2. Confirm the answer names the files and symbols actually involved in that
   area.
3. Confirm the answer does not introduce uncited repository facts.
4. Confirm `citedSymbolIds` and the cited file paths can be mapped back to the
   retrieved evidence.

## Validate local-only failure behavior

1. Stop the local embedding model or the local LLM.
2. Ask the same question again.
3. Confirm the session fails with an explicit local-only error.
4. Confirm no external service is contacted during the failure.

## Validate interactive behavior

1. Ask a follow-up question that depends on the previous turn.
2. Confirm the session preserves the earlier messages in order.
3. Confirm the answer remains grounded in the local repository evidence.

## Expected result

The chat session returns grounded answers that cite the correct files and
symbols, stays entirely local, and fails clearly when either the embedding
engine or the local LLM is unavailable.
