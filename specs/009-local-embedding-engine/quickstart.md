# Quickstart: Local Embedding Engine

## Prerequisites

- Python 3.11 or later
- Local project dependencies installed
- Ollama running on `http://localhost:11434`
- A local embedding model available, such as:
  - `nomic-embed-text`
  - another embedding model configured for local use

## Validate availability

1. Start the local embedding runtime.
2. Confirm the service responds on `http://localhost:11434`.
3. Confirm the configured model is available locally.
4. Call `isAvailableLocally()` on `EmbeddingEngine`.
5. Confirm the method reports the model as available.

## Validate embedding quality

1. Embed two semantically close code fragments, such as two repository helper
   functions.
2. Embed one unrelated fragment, such as a logging or formatting helper.
3. Compare cosine similarity across the three vectors.
4. Confirm the related fragments score higher than the unrelated fragment.

## Validate search reuse

1. Embed a code fragment during indexing.
2. Embed a user-style search query with the same engine.
3. Confirm both vectors can be compared directly.
4. Confirm the query vector can be used to rank relevant code fragments.

## Validate failure behavior

1. Stop the local embedding runtime.
2. Call `isAvailableLocally()` again.
3. Confirm the engine reports the runtime as unavailable.
4. Call `embed(text)` and confirm it fails immediately with a clear local-only
   error.
5. Confirm the message tells the user to start or install the local embedding
   runtime rather than suggesting any remote fallback.

## Expected result

The engine detects local unavailability before embedding, produces useful
vectors for semantically related text, and stays fully offline during normal
operation.
