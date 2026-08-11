# Implementation Plan: AST Symbol Extractor

Branch: `003-ast-symbol-extractor` | Date: 2026-08-11 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/003-ast-symbol-extractor/spec.md`

## Summary

Build a local symbol extraction stage that walks each source file AST and
returns a structured symbol inventory for downstream documentation and
dependency analysis. The model centers on an abstract `Symbol` hierarchy with
`ModuleSymbol`, `ClassSymbol`, and `FunctionSymbol` as concrete subtypes, each
sharing common metadata fields and exposing file-level imports plus raw
call/inheritance relations.

The extractor must preserve nested declarations, keep source positions exact,
and leave `generatedSummary` empty until Part 3 fills it in.

## Technical Context

Language/Version: Python 3.11+
Primary Dependencies: Existing local parser engine, pytest, dataclasses,
standard library JSON tooling, and the repository's current Tree-sitter-backed
AST layer
Storage: In-memory extraction results; no external storage required for this
feature
Testing: pytest with unit, contract, and integration coverage
Target Platform: Local CLI/library on Windows, macOS, and Linux
Project Type: Internal analysis pipeline stage built on top of the existing AST
parsing engine
Performance Goals: Extract complete symbol inventories for each file without
dropping nested declarations or relationship metadata; keep output deterministic
for repeated runs on the same input
Constraints: Fully local execution, no cloud fallback, no writes into analyzed
source repositories, preserve source file boundaries
Scale/Scope: Single-file and batch symbol extraction across medium and large
polyglot repositories

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentiality absolute: pass
- Zero exposure network by default: pass
- Never repli silently vers le cloud: pass
- Traçabilité des réponses IA: pass; feature output is structured extraction
  data, not generated prose
- Ré-indexation incrémentale: pass in scope; extraction is file-local and can be
  rerun incrementally
- Infrastructure minimale et stockage local: pass
- Depot analyse en lecture seule: pass

## Project Structure

### Documentation for this feature

`specs/003-ast-symbol-extractor/`
├── `plan.md`
├── `research.md`
├── `data-model.md`
├── `quickstart.md`
└── `contracts/`
    ├── `symbol-extractor-interface.md`
    └── `symbol-inventory.schema.json`

### Source Code

`src/`
├── `parser_engine/`
│   ├── `models.py`
│   ├── `ast_builder.py`
│   ├── `parser_base.py`
│   └── `parsers/`
└── `repo_scanner/`

Structure Decision: Keep the symbol hierarchy and extraction result types in a
shared model layer so downstream code can consume a single abstract `Symbol`
interface while the extractor returns concrete module, class, and function
records from AST traversal.

## Phase 0: Research

### Decision 1

Use a shared abstract `Symbol` base with three concrete subtypes:
`ModuleSymbol`, `ClassSymbol`, and `FunctionSymbol`.

### Decision 2

Treat `generatedSummary` as part of the canonical symbol model, but leave it
empty in this feature so Part 3 can populate it later without reshaping the
schema.

### Decision 3

Represent imports, calls, and inheritance as raw relation records attached to
the file inventory rather than resolving them into a graph in this phase.

### Decision 4

Keep symbol extraction deterministic and file-scoped so repeated runs on the
same source produce stable identifiers, positions, and relations.

## Phase 1: Design

### Data model

Define the abstract symbol base, concrete symbol subtypes, file inventories,
import records, call relations, inheritance relations, and validation rules.

### Contracts

Document the extractor input/output contract and the structured symbol inventory
schema returned to downstream stages.

### Quickstart

Provide validation steps that prove classes, nested functions, imports, calls,
and inheritance are all preserved in the output with accurate locations and
shared base fields.

## Constitution Check After Design

No violations introduced by the chosen design.
