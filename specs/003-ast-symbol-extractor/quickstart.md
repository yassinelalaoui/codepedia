# Quickstart: AST Symbol Extractor

## Prerequisites

- Python 3.11 or later
- The project dependencies installed in a local virtual environment
- A sample source file containing modules, classes, nested functions, imports,
  and at least one inheritance relationship

## Validate shared symbol hierarchy

1. Run the extractor on a test file that contains a module, one class, one
   top-level function, and one nested function.
2. Confirm that the output includes a shared base symbol shape with `id`,
   `name`, `lineStart`, `lineEnd`, `docstring`, and `generatedSummary`.
3. Confirm that the returned concrete types map to `ModuleSymbol`,
   `ClassSymbol`, and `FunctionSymbol`.

## Validate class-specific data

1. Run the extractor on a class that inherits from another class.
2. Confirm that the class record includes the parent class value.
3. Confirm that class methods appear in the returned inventory.

## Validate function-specific data

1. Run the extractor on a function that has parameters and a declared return
   type.
2. Confirm that the parameters are preserved in order.
3. Confirm that the return type is captured when present and omitted when not
   declared.

## Validate raw relations

1. Run the extractor on a file containing import statements and function calls.
2. Confirm that imports are returned as explicit records.
3. Confirm that call relations are returned as raw records even when some
   targets are unresolved.
4. Confirm that inheritance relations are returned without requiring graph
   assembly.

## Expected result

The extractor returns a complete, file-scoped symbol inventory with the full
class hierarchy, nested declarations, imports, calls, and inheritance links
preserved for downstream processing.
