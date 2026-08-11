# Feature Specification: AST Symbol Extractor

## Overview

The product analyzes each source file and extracts a structured symbol
inventory from its AST. The resulting inventory is intended to support later
documentation and dependency-graph construction workflows.

The extractor must return modules, classes, and functions with consistent
shared metadata, along with file-level imports and raw call and inheritance
relationships. It must preserve enough structure for nested declarations,
methods, parameters, and return information to be consumed without revisiting
the original source file.

## User Scenarios & Testing

### Primary user scenario

A developer or lead technical user runs the extractor on a source file or a set
of source files. The extractor returns a structured representation of every
symbol it finds, including its location, documentation text when available, and
relationships to other symbols in the same file or across files.

### Acceptance scenarios

1. A file containing a module, at least one class, at least one top-level
   function, and at least one nested function produces entries for all of those
   symbols.
2. A class entry includes its parent class when inheritance is present and
   includes its methods as part of the returned symbol inventory.
3. A function entry includes its parameters and return type information when
   available in the source.
4. A symbol entry includes an existing docstring or equivalent leading
   documentation text when one is present in the source.
5. A file containing import statements returns those imports as structured
   import records associated with that file.
6. A file containing calls between symbols returns those call relationships as
   raw relations, without requiring the dependency graph to already be built.
7. Nested declarations remain visible in the output instead of being collapsed
   into only their outer container.
8. The extractor preserves the original file boundaries so results can be
   attributed back to the source file that produced them.

### Edge Cases

1. A file without any class or function declarations still returns its module
   record and any imports it contains.
2. A symbol without a docstring is returned without a fabricated documentation
   value.
3. A function without an explicit return type is returned without a return type
   value rather than with a placeholder.
4. A call whose target cannot be fully resolved still appears as a raw call
   relation record.
5. A class with multiple levels of nesting still returns all nested symbols
   rather than only the outermost one.

## Requirements

### Functional Requirements

1. The extractor must analyze each source file through its AST.
2. The extractor must return a structured inventory containing at minimum
   modules, classes, and functions.
3. Every returned symbol must inherit from a shared base structure with all of
   the following fields:
   - `id`
   - `name`
   - `lineStart`
   - `lineEnd`
   - `docstring`
   - `generatedSummary`, initialized as empty and reserved for Part 3
4. Module records must represent the source file-level scope.
5. Class records must include the class name, position, parent class when
   present, and the methods defined on that class.
6. Function records must include the function name, position, parameters, and
   return type information when it is available in the source.
7. The extractor must include nested functions and other nested symbol
   declarations that appear inside a parent symbol.
8. The extractor must identify import statements for each file and return them
   as explicit import records.
9. The extractor must identify function calls between symbols and return them as
   raw relationship records suitable for later graph assembly.
10. The extractor must identify inheritance relationships between classes and
    return them as raw relationship records suitable for later graph assembly.
11. Relationship records must be attributable to the source file in which they
    were observed.
12. The extractor must preserve symbol data without modifying the analyzed
    source files.
13. The extractor must return the full set of discovered symbols for a file
    rather than stopping at the first top-level declaration.

### Non-Functional Requirements

1. The output must be stable enough for downstream indexing, documentation, and
   dependency analysis workflows.
2. The extractor must remain suitable for fully local execution.
3. The extractor must support source files that contain multiple nested levels
   of declarations.
4. The extractor must provide deterministic results for the same input file
   content.

## Assumptions

1. The extractor is used on source files already recognized as supported by the
   broader parsing pipeline.
2. Docstrings or equivalent leading documentation text are returned only when
   they are explicitly present in the source.
3. Return type information is included when the source makes it available and
   omitted otherwise.
4. Relationship records are raw extraction results and do not need to be fully
   resolved into a dependency graph within this feature.
5. The generated summary field exists in the shared symbol structure but is left
   empty by this feature.

## Success Criteria

1. On a test file containing modules, classes, nested functions, imports, and
   calls, the extractor returns every expected symbol and relationship with the
   correct attributes.
2. The returned data includes accurate start and end line positions for each
   discovered symbol.
3. The returned data includes docstrings for symbols that contain them and does
   not invent docstrings where none exist.
4. The returned data includes parameters for functions and parent class
   information for classes when those details are present in the source.
5. The extractor returns import, call, and inheritance relations as raw records
   that can be consumed by a later graph-building step.
6. The extractor does not omit nested declarations from the result set.
7. The extractor produces consistent output for repeated runs on the same input
   file.

## Key Entities

### Base Symbol

The shared abstract structure inherited by every symbol type. It includes the
symbol identifier, name, line start, line end, docstring, and generated summary
field.

### Symbol Hierarchy

The extractor must model a common abstract `Symbol` type with three concrete
subtypes:

- `ModuleSymbol`
- `ClassSymbol`
- `FunctionSymbol`

### Module

The file-level symbol that represents the scope of a source file.

### Class

A symbol representing a class declaration, including its parent class and the
methods it contains.

### Function

A symbol representing a function or method declaration, including parameters
and return type information when available.

### Import Record

A record describing an import statement observed in a source file.

### Call Relation

A raw record describing a function call observed between symbols.

### Inheritance Relation

A raw record describing a class inheritance link observed between symbols.
