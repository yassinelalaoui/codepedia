# Symbol Extractor Interface Contract

## Purpose

Define the structured extraction result returned from AST traversal so
downstream documentation and dependency analysis stages can consume one
consistent symbol inventory per source file.

## Core contract

The extractor returns one `FileSymbolInventory` per analyzed source file.

At a minimum, the inventory contains:

- one `ModuleSymbol`
- zero or more `ClassSymbol` entries
- zero or more `FunctionSymbol` entries
- zero or more import records
- zero or more call relations
- zero or more inheritance relations

## Shared symbol expectations

All symbol subtypes inherit from the abstract `Symbol` base and expose:

- `id`
- `name`
- `lineStart`
- `lineEnd`
- `docstring`
- `generatedSummary`

## Type-specific expectations

- `ModuleSymbol` represents the file scope and anchors the inventory
- `ClassSymbol` includes its parent class when present and its methods
- `FunctionSymbol` includes parameters and return type information when
  available

## Relationship expectations

- Import records are returned exactly as observed in the source file
- Call relations are returned as raw records and may be partially unresolved
- Inheritance relations are returned as raw records and are not required to be
  graph-resolved yet

## Downstream guarantees

- Results remain attributable to the source file that produced them
- Nested declarations are preserved in the returned inventory
- Repeated runs on the same file content should produce equivalent output
