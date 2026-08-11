# Research: Local LLM Access Layer

## Decision 1: Ollama-compatible localhost HTTP as the backend

Decision: Use an Ollama-compatible HTTP service on `http://localhost:11434`
as the default backend for local generation.

Rationale: The feature requirement explicitly targets local HTTP access, and
Ollama provides the relevant endpoints for version checks, model inventory,
and text generation on the local machine.

Alternatives considered: llama.cpp over an ad hoc local HTTP wrapper was
considered, but Ollama gives a clearer and more standardized endpoint surface
for this repository.

## Decision 2: Availability check before generation

Decision: Implement an explicit `isAvailableLocally()` check that first verifies
the service is reachable and then confirms the requested model is listed by the
local runtime.

Rationale: The spec requires a fast preflight check and an explicit failure when
the model is absent or the service is stopped. Ollama exposes a version endpoint
and a local model listing endpoint that support this two-step verification.

Alternatives considered: Relying only on generation-time failures was rejected
because it would delay error reporting and make the failure mode less explicit.

## Decision 3: Text generation via `POST /api/generate`

Decision: Use `POST /api/generate` with non-streaming responses for the engine's
`generate(prompt)` method.

Rationale: The generate endpoint returns a plain text response and is suitable
for both summarization and chat-style text generation when the caller builds the
prompt context explicitly.

Alternatives considered: `POST /api/chat` was considered, but the requested
engine surface is a single prompt-based method and generation gives a simpler
shared abstraction for both product paths.

## Decision 4: Local-only error model

Decision: Surface explicit local-only errors for unreachable service, missing
model, and invalid response payloads.

Rationale: The feature must never silently fall back to a cloud service and
must guide the user to install or start the local model. A clear error taxonomy
keeps the behavior testable and user-friendly.

Alternatives considered: Returning generic network errors was rejected because
it would not guide the user toward the local setup issue.

## Decision 5: Standard library HTTP transport

Decision: Use Python's standard library HTTP client rather than adding a new
third-party transport dependency.

Rationale: The repository already supports a small local toolchain and does not
need another dependency for a single local HTTP integration point.

Alternatives considered: `requests` or `httpx` were considered, but they were
rejected to keep the feature lightweight and easy to run in the existing
environment.
