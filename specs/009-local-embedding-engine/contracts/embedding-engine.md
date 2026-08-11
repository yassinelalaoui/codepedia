# Embedding Engine Contract

## Purpose

Define the public local-only embedding API used by indexing and semantic
search.

## Core type

### `EmbeddingEngine`

Constructor inputs:

- `modelName`
- `endpointUrl`

Required methods:

- `embed(text)`
- `isAvailableLocally()`

Expected behavior:

- Talks only to the configured local model runtime
- Checks availability before embedding
- Never falls back to a cloud provider
- Returns explicit errors when the runtime is stopped or the model is missing

## Embedding expectations

- `embed(text)` accepts a single piece of text, which may be code or prose
- The returned value is a numeric vector suitable for similarity comparison
- The vector must be stable for the same model and the same input text

## Availability expectations

- `isAvailableLocally()` returns `true` only when the local runtime responds and
  the configured model is available locally
- If the runtime is unreachable, the method returns `false` or raises an
  explicit local-only error depending on the implementation style
- The failure path must explain how to start or install the local runtime

## Failure expectations

- If the endpoint is down, the caller receives a clear service-unavailable
  error
- If the requested model is not available locally, the caller receives a clear
  model-missing error
- If the input text is invalid, the caller receives an explicit validation
  error
- If the response cannot be parsed, the caller receives an invalid-response
  error
