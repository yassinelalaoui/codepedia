# Data Model: AST Symbol Extractor

## Symbol

Abstract base type for all extracted symbols.

Fields:
- `id`
- `name`
- `lineStart`
- `lineEnd`
- `docstring`
- `generatedSummary`

Validation:
- `id` must be unique within the returned inventory
- `lineStart` and `lineEnd` must be positive integers with `lineStart <= lineEnd`
- `generatedSummary` must be present and empty at extraction time
- `docstring` may be empty or absent only when no documentation exists in source

## ModuleSymbol

Represents the file-level scope of a source file.

Fields:
- `base` (`Symbol`)
- `filePath`
- `imports`

Relationships:
- Owns the file-level symbol inventory for the source file
- May contain nested classes and functions in its descendants

Validation:
- Exactly one module symbol is expected per analyzed file

## ClassSymbol

Represents a class declaration.

Fields:
- `base` (`Symbol`)
- `parentClass`
- `methods`
- `nestedSymbols`

Relationships:
- May contain method symbols and nested declarations
- May participate in inheritance relations

Validation:
- `parentClass` is optional when the source defines no explicit base class
- `methods` must contain method symbols declared inside the class body

## FunctionSymbol

Represents a function or method declaration.

Fields:
- `base` (`Symbol`)
- `parameters`
- `returnType`
- `nestedSymbols`
- `owner`

Relationships:
- May be owned by a module or class
- May contain nested functions

Validation:
- `parameters` must preserve the declared order
- `returnType` is optional when not declared in source

## ImportRecord

Represents an import statement observed in a file.

Fields:
- `id`
- `sourceFile`
- `text`
- `lineStart`
- `lineEnd`

Validation:
- Must be attributable to exactly one source file

## CallRelation

Represents a raw function-call relationship.

Fields:
- `id`
- `sourceFile`
- `callerSymbolId`
- `calleeSymbolIdOrName`
- `lineStart`
- `lineEnd`

Validation:
- May remain partially unresolved when the target cannot be fully identified

## InheritanceRelation

Represents a raw inheritance relationship between classes.

Fields:
- `id`
- `sourceFile`
- `subclassSymbolId`
- `parentClassName`
- `lineStart`
- `lineEnd`

Validation:
- Must be emitted when a class declaration extends or inherits from another
  class

## FileSymbolInventory

Represents the complete extraction output for one source file.

Fields:
- `sourceFile`
- `module`
- `classes`
- `functions`
- `imports`
- `callRelations`
- `inheritanceRelations`

Validation:
- Must preserve all discovered symbols, including nested ones
- Must preserve raw relations without assembling the final graph
