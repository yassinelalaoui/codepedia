# Data Model: Local LLM Access Layer

## LocalLLMEngine

Represents the shared local-only LLM access layer.

Fields:
- `modelName`
- `endpointUrl`

Methods:
- `generate(prompt)`
- `isAvailableLocally()`

Relationships:
- Used by summary generation during indexing
- Used by chat response generation
- Communicates only with a local HTTP backend

Validation:
- `modelName` must not be empty
- `endpointUrl` must point to a local HTTP endpoint
- Availability must be checked before any generation request

## PromptEnvelope

Represents the prompt payload sent to the local model.

Fields:
- `promptText`
- `context`
- `systemPrompt`
- `options`

Relationships:
- Consumed by `LocalLLMEngine.generate(prompt)`

Validation:
- `promptText` must not be empty
- Optional context must remain attached to the prompt
- Optional generation options must be serializable to JSON

## GenerationResult

Represents the text returned by the local model service.

Fields:
- `text`
- `modelName`
- `endpointUrl`
- `rawResponse`

Relationships:
- Produced by a successful generation request

Validation:
- `text` must contain the generated natural-language response
- `modelName` should match the configured engine model when supplied by the backend

## AvailabilityStatus

Represents the outcome of a local availability check.

Fields:
- `available`
- `serviceReachable`
- `modelInstalled`
- `message`

Relationships:
- Returned or embedded by `isAvailableLocally()`

Validation:
- `available` is true only when the service is reachable and the model exists
- `message` must explain how to fix an unavailable local setup

## LocalLLMError

Represents an explicit local-only failure.

Fields:
- `kind`
- `message`
- `endpointUrl`
- `modelName`

Kinds:
- `service_unavailable`
- `model_missing`
- `invalid_response`
- `generation_failed`

Relationships:
- Raised by availability checks and generation

Validation:
- The error message must not suggest a cloud fallback
- The message must guide the user toward starting or installing the local model
