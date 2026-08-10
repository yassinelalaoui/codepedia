# Feature Specification: Multi-Language AST Parsing Engine

## Overview

The product parses individual source files into a uniform AST representation
that downstream pipeline stages can consume without caring about the original
language. It uses Tree-sitter as the parsing backbone and must support at least
Python, JavaScript, TypeScript, Java, Go, and Rust.

The parser must tolerate incomplete or temporarily invalid source code. A file
that cannot be parsed successfully must be logged and skipped without stopping
the broader indexing or parsing pipeline.

## User Scenarios & Testing

### Primary user scenario

A developer or lead technical user passes a source file and its detected
language to the parser. The parser returns a consistent AST representation for
that file, regardless of language, so later steps in the pipeline can inspect
symbols, structure, and relationships in the same way across the codebase.

### Acceptance scenarios

1. A valid Python file produces a coherent AST in the same output shape as a
   valid JavaScript, Java, Go, or Rust file.
2. A TypeScript file produces an AST that is structurally compatible with the
   JavaScript output shape.
3. A syntactically incomplete source file still fails gracefully, is recorded as
   a parse failure, and does not stop parsing of other files.
4. A batch containing both valid and broken source files completes, with valid
   files parsed and broken files skipped.
5. The AST output is stable enough for downstream indexing and symbol extraction
   to consume without special-casing the source language.

## Requirements

### Functional Requirements

1. The parser must accept a source file path and the detected language for that
   file.
2. The parser must produce a uniform AST representation for supported
   languages.
3. The parser must support at minimum Python, JavaScript, TypeScript, Java, Go,
   and Rust.
4. The parser must preserve enough structural information for downstream stages
   to identify top-level declarations, nested declarations, and other language
   constructs relevant to documentation and indexing.
5. The parser must tolerate incomplete or temporarily invalid syntax without
   terminating the batch process.
6. The parser must log parse failures in a way that allows the file to be
   revisited later.
7. The parser must return a per-file success or failure outcome so the pipeline
   can continue processing remaining files.
8. The parser must not require downstream stages to know the source language in
   order to traverse the AST shape.
9. The parser must avoid mutating the analyzed source repository.

### Non-Functional Requirements

1. The parser must be robust against editor-in-progress files and other
   transient syntax errors.
2. The parser must remain suitable for fully local execution.
3. The parser must support batch processing across many files without a single
   parse failure halting the full run.

## Assumptions

1. The detected language is available before parsing begins.
2. The parser returns a machine-readable AST object plus metadata for each
   processed file.
3. Downstream stages need structural consistency more than language-specific
   syntax details.
4. Parse failures are recorded as diagnostic events or structured error objects
   available to the pipeline.

## Success Criteria

1. Every supported language in the target set produces an AST with a consistent
   top-level envelope.
2. A syntactically broken file is reported as a parse failure and does not
   interrupt parsing of other files.
3. A mixed batch of valid and invalid files completes with all valid files
   parsed successfully.
4. Downstream stages can consume the output without language-specific branches
   for Python, JavaScript/TypeScript, Java, Go, or Rust.
5. The parser remains usable on code being actively edited, including files that
   are temporarily incomplete or invalid.

## Key Entities

### Parse Request

The input describing one file to parse, including its path, language, and
content source.

### AST

The uniform abstract syntax tree returned for a successfully parsed file.

### Parse Result

The per-file outcome, including either the AST or a failure record.

### Parse Failure

The structured diagnostic emitted when a file cannot be parsed successfully.

### Language Adapter

A language-specific mapping that connects a detected language to the parser
logic needed to produce the uniform AST shape.

