# Quickstart: Multi-Language AST Parsing Engine

## Prerequisites

- Python 3.11 or later
- Local Tree-sitter language grammar packages for the supported languages
- The project dependencies installed in a virtual environment

## Validate supported languages

1. Parse a valid Python file through `PythonParser`.
2. Parse a valid JavaScript file through `JavaScriptParser`.
3. Parse a valid TypeScript file through `TypeScriptParser`.
4. Parse a valid Java file through `JavaParser`.
5. Parse a valid Go file through `GoParser`.
6. Parse a valid Rust file through `RustParser`.
7. Confirm that each parser returns the same AST envelope shape.

## Validate invalid syntax handling

1. Parse a file that is syntactically incomplete or broken.
2. Confirm that the parser returns a structured failure record instead of
   raising an uncaught exception.
3. Confirm that the batch continues parsing other files after the failure.

## Validate uniform downstream consumption

1. Feed the AST output from several languages into the downstream indexing
   stage.
2. Confirm that the downstream code traverses the output without language-
   specific branches.

## Expected result

Supported files produce coherent ASTs, malformed files are logged and skipped,
and the broader pipeline keeps moving.

