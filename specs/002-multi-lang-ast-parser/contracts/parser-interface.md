# Parser Interface Contract

## Purpose

Define the uniform API that the downstream pipeline uses to parse source files
into a normalized AST envelope.

## Core contract

Each concrete parser must expose the same method:

`parse(SourceFile) -> AST`

Where:
- `SourceFile` identifies the file path, detected language, and file content
- `AST` is the normalized tree returned on success

## Shared expectations

- The caller provides a file with a detected language that maps to a registered
  parser.
- The parser returns a normalized AST on success.
- The parser returns a structured failure record or equivalent parse result on
  failure.
- The parser must not raise an uncaught exception that stops the batch pipeline
  for ordinary syntax errors.

## Supported parser family

- `PythonParser`
- `JavaScriptParser`
- `TypeScriptParser`
- `JavaParser`
- `GoParser`
- `RustParser`

## Downstream guarantees

- The AST envelope is structurally consistent across languages.
- Downstream code can traverse nodes without knowing the source language.
- Parse failures are observable and can be logged or retried later.

