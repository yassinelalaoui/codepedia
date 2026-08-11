# Research: Local Embedding Engine

## Decision 1: Ollama-compatible localhost backend with `nomic-embed-text`

Decision: Use a local Ollama-compatible embedding backend as the default
runtime and standardize on `nomic-embed-text` as the default model name.

Rationale: The repository already has a local Ollama access layer and a
clear local-only error model. Reusing the same local runtime pattern keeps the
feature offline, reduces dependency sprawl, and gives the embedding engine a
known availability story.

Alternatives considered: A local `sentence-transformers` runtime was considered,
but it would introduce another Python model-loading path and a second model
distribution story alongside the existing local HTTP runtime.

## Decision 2: Explicit preflight availability check

Decision: Require an explicit availability check before embedding any text, and
make the check confirm both runtime reachability and local model presence.

Rationale: The spec requires the tool to fail clearly if the model is missing or
stopped. A preflight check keeps the failure mode predictable and avoids a
silent handoff to some other provider.

Alternatives considered: Letting embedding fail only at call time was rejected
because it would defer the error until after the caller has already attempted
the operation.

## Decision 3: Small `EmbeddingEngine` surface

Decision: Use a compact `EmbeddingEngine` abstraction centered on a single
`embed(text)` method, plus an explicit availability check in the same surface.

Rationale: The feature needs to be simple enough to call from both indexing and
query vectorization paths. A minimal abstraction makes it easy to reuse and
easy to test.

Alternatives considered: Exposing a larger API with prompt templates or batch
generation was rejected because the feature only needs text-to-vector
conversion.

## Decision 4: Local vectorization at existing integration points

Decision: Wire the engine into `src/vector_index/chunking.py` for chunk
vectorization and `src/vector_index/search.py` for query vectorization.

Rationale: Those are the real integration points for embedding code fragments
and user search queries in the current codebase. Keeping the integration inside
`vector_index` preserves the current indexing and retrieval flow.

Alternatives considered: Adding a separate caller-specific vectorization layer
was rejected because it would duplicate logic and fragment the retrieval path.

## Decision 5: Standard library transport

Decision: Use the Python standard library for the local HTTP transport.

Rationale: The project values a local, lightweight footprint and already
supports standard-library-based local integrations.

Alternatives considered: Third-party HTTP clients or a heavier model runtime
wrapper were not necessary for this scope.
