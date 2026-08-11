# Local LLM Engine Contract

## Purpose

Define the public local-only LLM access API used by indexing and chat.

## Core type

### `LocalLLMEngine`

Constructor inputs:

- `modelName`
- `endpointUrl`

Required methods:

- `generate(prompt)`
- `isAvailableLocally()`

Expected behavior:

- Talks only to the configured local HTTP endpoint
- Checks availability before generation
- Never falls back to a cloud provider
- Returns explicit errors when the service is stopped or the model is missing

## Prompt expectations

- `generate(prompt)` accepts a prompt payload that includes the user text and
  any required context for summaries or chat
- The request is sent as a local non-streaming generation request
- The returned value is the model response text

## Availability expectations

- `isAvailableLocally()` returns `true` only when the local service responds
  and the configured model is available locally
- If the service is unreachable, the method returns `false` or raises an
  explicit local-only error depending on the implementation style
- The failure path must explain how to start or install the local runtime

## Failure expectations

- If the endpoint is down, the caller receives a clear service-unavailable
  error
- If the requested model is not listed locally, the caller receives a clear
  model-missing error
- If the response cannot be parsed, the caller receives an invalid-response
  error
