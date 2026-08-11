# Feature Specification: Local Code Summary Pipeline

## Overview

Build a local pipeline that generates a natural-language description of the
role of each module and each public function marked as significant during
indexing. For every symbol in scope, the pipeline must assemble relevant
context from the symbol's own source code, its imports, and its direct callers
known through the dependency graph, then send that context to the local LLM
and store the generated summary back on the matching symbol.

The pipeline must operate entirely locally, must verify that the local model is
available before any work begins, and must support incremental re-indexing so
that only symbols affected by a change have their summaries regenerated.

## Goals

- Generate a readable summary for each in-scope module and public significant
  function.
- Use local source context, imports, and dependency information to improve
  summary quality.
- Fail fast when the local LLM is not available.
- Regenerate only summaries affected by a source change.
- Keep all summary generation local and attributable to the source symbol.

## Non-Goals

- Summarizing private helper functions that the indexer does not treat as
  significant.
- Replacing the existing symbol extraction or dependency graph pipelines.
- Generating summaries from remote or cloud-hosted models.
- Building a user-facing chat experience.
- Translating summaries into another language.

## User Stories

### US1 - Generate summaries for indexed symbols

As a maintainer, I want the indexer to generate a concise natural-language
summary for each in-scope module and public significant function so that the
repository inventory includes a readable description of what each symbol does.

Acceptance criteria:

- Each in-scope module receives a summary.
- Each public significant function receives a summary.
- The summary is stored with the corresponding symbol.
- The summary reflects the symbol's code and relevant context.

### US2 - Use local context and local LLM only

As a maintainer, I want the pipeline to use the symbol's code, its imports, and
its direct callers from the dependency graph as context so that summaries are
grounded in the repository structure and generated only by the local model.

Acceptance criteria:

- The assembled context includes the symbol source code.
- The assembled context includes relevant imports.
- The assembled context includes direct callers when available.
- Summary generation uses only the configured local LLM.

### US3 - Regenerate only impacted summaries

As a maintainer, I want changed symbols to have their summaries regenerated
without rebuilding summaries for the entire repository so that incremental
re-indexing stays fast and efficient.

Acceptance criteria:

- A change to a file or symbol can trigger summary regeneration for just the
  affected symbols.
- Unchanged symbols keep their existing summaries.
- The pipeline does not require a full repository re-summarization for a small
  edit.

## Functional Requirements

### Summary generation

- The pipeline must generate a natural-language summary for each module in
  scope.
- The pipeline must generate a natural-language summary for each public
  significant function in scope.
- The summary must describe the role of the symbol in the repository.
- The summary must be stored on the corresponding symbol record.

### Context assembly

- The pipeline must assemble the symbol's own source code as part of the input
  context.
- The pipeline must include the symbol's imports when they are available.
- The pipeline must include direct callers known from the dependency graph when
  they are available.
- The assembled context must be sufficient to explain the symbol in terms of
  its local repository usage.

### Local model availability

- The pipeline must verify that the local LLM is available before any summary
  generation work starts.
- If the local model is unavailable, the pipeline must stop immediately and
  return an explicit error.
- The failure message must tell the user how to start or install the local
  model.
- The pipeline must not silently fall back to any remote service.

### Incremental regeneration

- The pipeline must be able to identify summaries affected by a symbol or file
  modification.
- The pipeline must regenerate only impacted summaries when incremental
  re-indexing runs.
- The pipeline must preserve existing summaries for unchanged symbols.

### Local operation

- The pipeline must operate without contacting any external service.
- The pipeline must keep summary generation tied to the local repository
  analysis flow.
- The generated summaries must remain attributable to the source symbol and
  file.

## Edge Cases

- A symbol with no direct callers should still receive a useful summary from
  its source code and imports.
- A symbol with minimal source code, such as a one-line function, should still
  be summarized deterministically.
- A module with no public functions should still be able to receive a module
  summary if it is in scope.
- If the dependency graph does not yet contain caller information for a symbol,
  the pipeline should still generate a summary from the remaining available
  context.

## Assumptions

- "Public significant function" means a non-private function symbol retained by
  the existing indexer as part of the repository inventory.
- The repository already has a dependency graph that can provide direct caller
  information when available.
- The local LLM is already supported elsewhere in the product and is reused for
  this pipeline.
- Incremental re-indexing can identify which files or symbols changed since the
  last run.

## Success Criteria

- After indexing a test module, every in-scope public significant function has
  a stored summary that matches the code's actual role.
- Module summaries and function summaries are generated only by the local LLM
  and not by any external service.
- When a file changes, only the summaries for affected symbols are regenerated.
- If the local model is unavailable, the pipeline reports the failure before
  processing any symbol.

## Key Entities

### SymbolSummaryJob

Represents the work item for summarizing one module or function.

### SummaryContext

Represents the symbol source, imports, and direct caller context passed to the
local model.

### SummaryRecord

Represents the generated summary stored on the symbol.

### ImpactedSymbolSet

Represents the symbols whose summaries must be regenerated after a change.
