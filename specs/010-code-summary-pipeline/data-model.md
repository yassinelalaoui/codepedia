# Data Model: Local Code Summary Pipeline

## SymbolSummaryJob

Represents one summary task for a module or a public significant function.

Fields:
- `symbolId`
- `sourceFileId`
- `kind`
- `name`
- `contentHash`
- `isIncremental`
- `priority`

Relationships:
- Produced from repository metadata and dependency-graph analysis
- Consumed by the summarization pipeline

Validation:
- `symbolId` must reference an existing symbol
- `kind` must be a module or function symbol in scope
- `contentHash` must reflect the current source snapshot

## SummaryContext

Represents the text and relationship context passed to the local LLM.

Fields:
- `symbolSource`
- `imports`
- `directCallers`
- `symbolMetadata`
- `repositoryRoot`

Relationships:
- Built from `RepositoryMetadataStore` and `DependencyGraph`
- Consumed by `LocalLLMEngine`

Validation:
- Source text must be present
- Imports may be empty, but the context must remain deterministic
- Direct callers may be empty when none are known

## SummaryResult

Represents the generated natural-language summary for a symbol.

Fields:
- `symbolId`
- `generatedSummary`
- `modelName`
- `contextHash`
- `generatedAt`

Relationships:
- Produced by the local LLM pipeline
- Written back to the symbol record's `generatedSummary` field

Validation:
- `generatedSummary` must be non-empty for successful jobs
- `contextHash` must match the input context used for generation

## ImpactedSymbolSet

Represents the symbols that must be regenerated after a change.

Fields:
- `changedFileIds`
- `changedSymbolIds`
- `dependentSymbolIds`

Relationships:
- Derived from file content hashes and dependency graph neighborhoods
- Used to avoid full repository re-summarization

Validation:
- Impacted symbols must include the directly changed symbol or file
- Unchanged symbols must not be added unless their local context changed
