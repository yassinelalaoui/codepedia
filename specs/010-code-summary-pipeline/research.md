# Research: Local Code Summary Pipeline

## Decision 1: Reuse `LocalLLMEngine` for all summary generation

Decision: Use the existing local LLM engine as the only generation backend for
module and function summaries.

Rationale: The feature must stay local and must explicitly fail when the model
is unavailable. Reusing the established local engine avoids introducing a
second generation path and keeps the failure behavior consistent.

Alternatives considered: Adding a second summarization backend was rejected
because it would complicate availability checks and risk diverging behavior.

## Decision 2: Use direct callers from `DependencyGraph`

Decision: Include the symbol's source code, imports, and direct callers from the
dependency graph as the primary summary context.

Rationale: These are the most relevant local signals already present in the
repository. Direct callers provide the clearest explanation of how a symbol is
used without forcing the prompt to absorb the entire graph.

Alternatives considered: Traversing the full transitive call graph was rejected
because it would make prompts noisy and harder to keep bounded.

## Decision 3: Incremental regeneration by impact set

Decision: Recompute summaries only for symbols whose source file changed or
whose local dependency context is affected by the change.

Rationale: The spec requires incremental re-indexing rather than a full
repository re-summary. A symbol-level impact set supports that requirement while
preserving existing summaries for unchanged symbols.

Alternatives considered: Re-summarizing the full repository on each run was
rejected because it would be slower and would defeat the incremental goal.

## Decision 4: Store summaries on existing symbol records

Decision: Update the existing `generated_summary` field on the `symbols` table
and the corresponding symbol objects when summaries are produced.

Rationale: The repository already models generated summaries as part of symbol
state, so storing the result there keeps the data model simple and aligned with
the rest of the metadata pipeline.

Alternatives considered: A separate summary table or artifact store was
considered, but it would duplicate symbol identity and add persistence
complexity without a clear benefit.

## Decision 5: Keep prompt composition local and explicit

Decision: Build summary prompts from local source snippets and relationship
metadata inside the repository codebase rather than introducing a template
service or remote prompt builder.

Rationale: The feature is local-only and should remain easy to inspect, test,
and modify alongside the repository metadata logic.

Alternatives considered: External prompt templating was rejected because it
would not add value for a deterministic local pipeline.
