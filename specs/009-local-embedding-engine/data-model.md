# Data Model: Local Embedding Engine

## EmbeddingEngine

Represents the shared local-only embedding interface used by indexing and
semantic search.

Fields:
- `modelName`
- `endpointUrl`

Methods:
- `embed(text)`
- `isAvailableLocally()`

Relationships:
- Used by code chunk vectorization
- Used by search query vectorization
- Communicates only with a local model runtime

Validation:
- `modelName` must not be empty
- `endpointUrl` must point to a local endpoint
- Availability should be checked before embedding

## EmbeddingVector

Represents the numeric vector returned for a piece of text.

Fields:
- `values`

Relationships:
- Produced by `EmbeddingEngine.embed(text)`
- Consumed by vector similarity and storage layers

Validation:
- `values` must contain numeric values
- Vector dimensionality must remain stable for a given model

## EmbeddingRequest

Represents the text sent for vectorization.

Fields:
- `text`
- `sourceKind`
- `modelName`

Relationships:
- Consumed by the embedding engine

Validation:
- `text` must be deterministic to handle for the same input
- Empty or whitespace-only text must produce an explicit, predictable outcome

## EmbeddingResult

Represents the outcome of a successful embedding operation.

Fields:
- `vector`
- `modelName`
- `endpointUrl`

Relationships:
- Returned by `EmbeddingEngine.embed(text)`

Validation:
- The result must be usable for cosine similarity comparisons

## EmbeddingAvailabilityStatus

Represents the outcome of a local availability check.

Fields:
- `available`
- `runtimeReachable`
- `modelInstalled`
- `message`

Relationships:
- Returned or surfaced by `isAvailableLocally()`

Validation:
- `available` is true only when the local runtime is reachable and the model is
  present
- `message` must explain how to start or install the local model

## LocalEmbeddingError

Represents an explicit local-only failure.

Fields:
- `kind`
- `message`
- `endpointUrl`
- `modelName`

Kinds:
- `service_unavailable`
- `model_missing`
- `invalid_input`
- `invalid_response`
- `embedding_failed`

Relationships:
- Raised by availability checks and embedding generation

Validation:
- The error message must not suggest a cloud fallback
- The message must guide the user toward starting or installing the local model
