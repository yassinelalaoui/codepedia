# Implementation Plan: Multi-Language AST Parsing Engine

Branch: `002-multi-lang-ast-parser` | Date: 2026-08-10 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/002-multi-lang-ast-parser/spec.md`

## Summary

Build a fully local Tree-sitter-based parsing engine that accepts a source file
and its detected language, routes the file through a language-specific parser
implementation, and returns a uniform AST envelope that downstream pipeline
stages can consume consistently across Python, JavaScript, TypeScript, Java,
Go, and Rust.

The parser must be resilient to syntax errors. Individual parse failures are
captured as structured failures, logged, and skipped so the batch pipeline
continues processing other files.

## Technical Context

Language/Version: Python 3.11+
Primary Dependencies: Tree-sitter Python bindings, official language grammar
packages for Python, JavaScript, TypeScript, Java, Go, and Rust, pytest
Storage: N/A; parsed ASTs are returned in-memory to downstream pipeline stages
Testing: pytest with unit, contract, and integration coverage
Target Platform: Local CLI/library on Windows, macOS, and Linux
Project Type: Internal parsing library plus pipeline-facing API
Performance Goals: Parse files independently and keep batch failures isolated;
support large file batches without one broken file halting the run
Constraints: Fully local execution, no cloud fallback, no external databases or
brokers, no writes into the analyzed source repository
Scale/Scope: Multi-language source batches from medium and enterprise codebases

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentiality absolute: pass
- Zero exposure network by default: pass
- Never repli silently vers le cloud: pass
- Traçabilité des réponses IA: pass; this feature does not generate AI content
- Ré-indexation incrémentale: pass in scope; parsing is file-local and batch
  failures do not force a full rerun
- Infrastructure minimale et stockage local: pass
- Depot analyse en lecture seule: pass

## Project Structure

### Documentation for this feature

`specs/002-multi-lang-ast-parser/`
├── `plan.md`
├── `research.md`
├── `data-model.md`
├── `quickstart.md`
└── `contracts/`
    ├── `parser-interface.md`
    └── `ast-envelope.schema.json`

### Source Code

`src/`
├── `parser_engine/`
│   ├── `__init__.py`
│   ├── `models.py`
│   ├── `parser_base.py`
│   ├── `parser_registry.py`
│   ├── `parsers/`
│   │   ├── `python_parser.py`
│   │   ├── `javascript_parser.py`
│   │   ├── `typescript_parser.py`
│   │   ├── `java_parser.py`
│   │   ├── `go_parser.py`
│   │   └── `rust_parser.py`
│   ├── `treesitter_runtime.py`
│   ├── `ast_builder.py`
│   └── `errors.py`
└── `tests/`
    ├── `unit/`
    ├── `contract/`
    └── `integration/`

Structure Decision: Use a Python package under `src/parser_engine` with an
abstract `Parser` base class and one concrete parser per language. Each parser
exposes the same `parse(SourceFile) -> AST` method and shares a common
Tree-sitter runtime adapter plus uniform AST builder.

## Phase 0: Research

### Decision 1

Use Python as the implementation language for the parsing engine.

### Decision 2

Use the official Tree-sitter Python bindings with official language grammar
packages for Python, JavaScript, TypeScript, Java, Go, and Rust.

### Decision 3

Define a shared abstract `Parser` base class plus concrete language-specific
implementations that all satisfy the same `parse(SourceFile) -> AST` contract.

### Decision 4

Represent parse failures as structured per-file results so the batch pipeline
can continue after an error.

## Phase 1: Design

### Data model

Define source-file inputs, parser dispatch metadata, AST envelopes, parse
results, and parse failures.

### Contracts

Document the parser API and the AST envelope returned to downstream pipeline
stages.

### Quickstart

Provide validation steps that prove supported languages parse successfully and
that a malformed file is logged and skipped without aborting the batch.

## Constitution Check After Design

No violations introduced by the chosen design.

