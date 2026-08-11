# Quickstart: Local LLM Access Layer

## Prerequisites

- Python 3.11 or later
- Local project dependencies installed
- Ollama running on `http://localhost:11434`
- At least one local model pulled, such as:
  - `llama3`
  - `qwen2.5-coder`
  - `deepseek-coder`

## Validate availability

1. Start Ollama locally.
2. Confirm the service responds on `http://localhost:11434/api/version`.
3. Check that the configured model appears in the local model list.
4. Call `isAvailableLocally()` on `LocalLLMEngine`.
5. Confirm the method reports the model as available.

## Validate generation

1. Build a prompt with text and context for either summary generation or chat.
2. Call `generate(prompt)` on `LocalLLMEngine`.
3. Confirm that the returned value is plain natural-language text.
4. Confirm that the request stays local and does not contact any remote API.

## Validate failure behavior

1. Stop Ollama.
2. Call `isAvailableLocally()` again.
3. Confirm that the engine reports the service as unavailable.
4. Call `generate(prompt)` and confirm that it fails immediately with a clear
   local-only error.
5. Confirm that the message guides the user to start or install the local
   runtime rather than suggesting any cloud fallback.

## Expected result

The engine detects local unavailability before generation, uses only the local
HTTP backend when available, and produces clear errors when the model runtime
is stopped or missing.
