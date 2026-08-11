# Research: AST Symbol Extractor

## Decision 1: Abstract symbol hierarchy

Decision: Model symbols with an abstract `Symbol` base type and three concrete
subtypes: `ModuleSymbol`, `ClassSymbol`, and `FunctionSymbol`.

Rationale: The feature needs shared fields across all symbol kinds while still
preserving type-specific data such as parents, methods, parameters, and return
types. A common abstract base keeps the contract consistent and makes later
stages simpler.

Alternatives considered: A flat record structure with a `kind` field. Rejected
because it blurs the distinction between module, class, and function behavior
and makes type-specific validation less clear.

## Decision 2: Shared base fields

Decision: Keep `id`, `name`, `lineStart`, `lineEnd`, `docstring`, and
`generatedSummary` on the shared symbol base.

Rationale: These fields are needed on every symbol and give downstream tooling a
single place to read identity, location, and documentation metadata. Leaving
`generatedSummary` empty now preserves the contract for Part 3 without forcing a
later model migration.

Alternatives considered: Store positions only on concrete symbol types.
Rejected because callers would then need type-specific branches to read common
metadata.

## Decision 3: Raw relationship records

Decision: Return imports, call relations, and inheritance relations as raw
records alongside the symbol inventory.

Rationale: The feature explicitly stops short of full graph assembly. Keeping
relations raw preserves source evidence and lets the dependency graph be built
later without re-traversing the AST.

Alternatives considered: Build the graph immediately. Rejected because the
feature scope is extraction, not resolution.

## Decision 4: File-scoped deterministic output

Decision: Preserve file boundaries and emit stable results for the same input
content.

Rationale: The extractor feeds later indexing and dependency workflows, which
need repeatable output for diffing and incremental processing.

Alternatives considered: Derive ephemeral identifiers from traversal order only.
Rejected because that would make results harder to compare across runs.

## Decision 5: Nested declaration preservation

Decision: Keep nested declarations in the returned symbol set rather than only
returning top-level declarations.

Rationale: The acceptance criteria require nested functions and multi-level
nesting to remain visible in the output, even when they are inside other
symbols.

Alternatives considered: Collapse nested declarations into their parent symbol.
Rejected because it would lose detail required for dependency and documentation
generation.
