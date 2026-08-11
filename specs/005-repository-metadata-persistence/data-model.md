# Data Model: Repository Metadata Persistence

## Repository

Represents one indexed repository stored in the local persistence file.

Fields:
- `id`
- `rootPath`
- `detectedLanguages`
- `lastIndexedAt`

Relationships:
- Owns many `SourceFile` records
- Owns the persisted `DependencyGraph` snapshot for the repository state

Validation:
- `id` must be stable for the same repository root
- `rootPath` must identify the repository being indexed
- `detectedLanguages` must reflect the languages observed during indexing

## SourceFile

Represents one scanned source file inside a repository.

Fields:
- `id`
- `repositoryId`
- `path`
- `language`
- `contentHash`
- `lastModified`

Relationships:
- Belongs to one `Repository`
- Owns many `Symbol` records
- May contribute edges to the persisted dependency graph

Validation:
- `path` must be unique within a repository
- `contentHash` must change when file content changes
- `lastModified` must reflect the observed file state at index time

## Symbol

Represents a stored symbol extracted from a source file.

Fields:
- `id`
- `sourceFileId`
- `kind`
- `name`
- `lineStart`
- `lineEnd`
- `docstring`
- `generatedSummary`
- `metadata`

Relationships:
- Belongs to one `SourceFile`
- Can act as the source or target of dependency edges

Validation:
- `kind` must identify the concrete symbol family
- `lineStart` and `lineEnd` must describe a valid source span
- `metadata` must preserve subtype-specific attributes needed for reload

## ModuleSymbol

Represents a module-level symbol stored as a specialized `Symbol`.

Fields:
- `id`
- `symbolId`
- `filePath`
- `imports`

Relationships:
- Represents the module entry point for a source file

Validation:
- `filePath` must match the owning source file path
- `imports` must preserve the module's direct import metadata when present

## ClassSymbol

Represents a class stored as a specialized `Symbol`.

Fields:
- `id`
- `symbolId`
- `parentClass`
- `methods`

Relationships:
- May inherit from another class via a dependency edge

Validation:
- `parentClass` must reflect the direct parent name when available
- `methods` must preserve the class's stored method list when present

## FunctionSymbol

Represents a function stored as a specialized `Symbol`.

Fields:
- `id`
- `symbolId`
- `parameters`
- `returnType`
- `nestedSymbols`
- `owner`

Relationships:
- May call other functions via dependency edges

Validation:
- `parameters` must preserve parameter order and available type information
- `returnType` must preserve the observed return type when available

## DependencyGraph

Represents the persisted dependency graph for a repository.

Fields:
- `id`
- `repositoryId`
- `nodes`
- `edges`

Relationships:
- Uses stored symbols as graph nodes
- Owns many `DependencyEdge` records

Validation:
- The graph must not duplicate node identities
- The graph must not duplicate typed edges between the same source and target

## DependencyEdge

Represents one typed directed dependency between stored symbols.

Fields:
- `sourceId`
- `targetId`
- `type`
- `sourceFileId`
- `metadata`

Relationships:
- Connects files or symbols through import, call, or inheritance relations

Validation:
- `type` must be one of `import`, `call`, or `inheritance`
- `sourceId` and `targetId` must refer to stored entities
- Duplicate edges with the same source, target, and type must be suppressed

## Repository snapshot state

Represents the current persisted view of a repository at the moment of the last
successful indexing run.

Fields:
- `repositoryId`
- `lastIndexedAt`
- `sourceFileCount`
- `symbolCount`
- `edgeCount`

Relationships:
- Summarizes the stored repository contents for reopen and validation flows

Validation:
- Reopening the tool must reproduce the stored snapshot exactly
