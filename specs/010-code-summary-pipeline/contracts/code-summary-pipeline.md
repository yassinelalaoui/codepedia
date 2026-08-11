# Code Summary Pipeline Contract

## Purpose

Define the public local-only pipeline used to generate and persist summaries for
modules and public significant functions.

## Core type

### `CodeSummaryPipeline`

Constructor inputs:

- `metadataStore`
- `dependencyGraph`
- `llmEngine`

Required methods:

- `isReady()`
- `summarizeRepository()`
- `summarizeSourceFile()`
- `summarizeImpactedSymbols()`

Expected behavior:

- Verifies the local LLM is available before work starts
- Builds summary context from symbol code, imports, and direct callers
- Persists the generated summary onto the matching symbol record
- Regenerates only symbols that are impacted by a change
- Never falls back to a remote model

## Readiness expectations

- `isReady()` returns `true` only when the local model is available
- If the local model is unavailable, the pipeline must fail before processing
  any symbol

## Context expectations

- The pipeline must include the symbol source code in the summary context
- The pipeline must include imports when they are available
- The pipeline must include direct callers when the dependency graph knows them

## Persistence expectations

- A successful summary run writes the generated text to `Symbol.generatedSummary`
- Incremental runs preserve existing summaries for unchanged symbols
- The pipeline does not mutate source code files

## Failure expectations

- If the local model is not available, the caller receives a clear local-only
  error
- If the dependency graph or metadata cannot produce a summary context, the
  caller receives an explicit failure
- If generation returns an invalid result, the caller receives a clear
  generation error
