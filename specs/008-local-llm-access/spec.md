# Feature Specification: Local LLM Access Layer

## Overview

Build a local LLM access layer that talks only to a model running on the
developer machine, exposed over HTTP by Ollama or llama.cpp on `localhost`.
The layer must provide two explicit capabilities:

1. Check whether the local model service is available before generation.
2. Send a prompt with context and receive a natural-language response.

The layer is used in two places in the product:

- generating code summaries during indexing
- generating answers in the chat experience

The system must never silently fall back to a cloud service. If the local model
is not installed, not started, or unreachable, the caller must receive a clear
error and a user-facing message that explains how to start or install the local
service.

## Goals

- Provide a single local-only client abstraction for LLM requests.
- Fail fast when the local model backend is unavailable.
- Keep the generation path reusable for both indexing and chat.
- Make availability checks explicit and testable.
- Avoid any hidden cloud fallback or network escape hatch.

## Non-Goals

- Training or fine-tuning local models.
- Managing model downloads beyond clear user guidance.
- Implementing a remote/cloud LLM provider.
- Building prompt orchestration or retrieval logic beyond this access layer.

## User Stories

### US1 - Check local model availability

As a user, I want the tool to verify that my local LLM service is running
before any prompt is sent, so that I get an immediate and understandable error
if the service is offline.

Acceptance criteria:

- The layer exposes an explicit availability check.
- The check targets the configured local endpoint only.
- If the service is unreachable, the check fails with a clear local-only error.
- No generation request is attempted when availability fails.

### US2 - Generate text from a local prompt

As a user, I want to send a prompt with context to the local model and get a
natural-language response back, so that summaries and chat replies can be
generated locally.

Acceptance criteria:

- The API accepts prompt text plus optional context.
- The API returns the model response as text.
- The request is sent only to the local backend.
- Generation errors surface clearly to the caller.

### US3 - Use the same layer for summaries and chat

As the product, I want a shared local LLM client for indexing summaries and
chat responses so that both paths behave consistently.

Acceptance criteria:

- The same availability check is used in both generation paths.
- Both paths fail fast when the local backend is down.
- Neither path may redirect to a cloud provider.

## Functional Requirements

### Connection handling

- The layer must support a configurable local base URL, defaulting to
  `http://localhost:11434` for Ollama-compatible deployments.
- The layer must be able to detect a local HTTP service failure before sending
  any generation request.
- The layer must distinguish between unavailable service, invalid response, and
  generation failure.

### Prompt generation

- The layer must accept:
  - prompt text
  - optional system instructions or context
  - optional model name
  - optional generation parameters when supported by the backend
- The layer must return plain text output suitable for summaries and chat.
- The layer must preserve the original prompt/context boundaries when sending
  requests to the backend.

### Error handling

- If the local model service is not running, the user must get an explicit
  error.
- If the model is not installed, the user must get an explicit error with a
  message that guides them to install or start a local model service.
- If the request would otherwise fall back to a cloud provider, that fallback
  must be disabled.

### Safety and privacy

- All requests must remain local to the machine.
- The implementation must not require or contact any external API endpoint.
- The failure mode must be obvious and actionable, not silent.

## Quality Requirements

- Availability checks should be fast enough to run before each generation call.
- The local client should be deterministic about error reporting for the same
  offline state.
- The interface should be small enough to reuse from both indexing and chat.

## Success Criteria

- When the local service, such as Ollama on `localhost:11434`, is stopped, the
  tool detects the outage before sending any prompt.
- The user sees a clear message telling them that the local model is not
  available and how to start or install it.
- No external service is contacted in the unavailable-service scenario.
- Both summary generation and chat generation use the same local-only layer.
