# Implementation Plan: Local Repository Scanner

Branch: `001-local-repo-scanner` | Date: 2026-08-10 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/001-local-repo-scanner/spec.md`

## Summary

Build a fully local Python CLI that scans a developer-provided repository path,
applies `.gitignore`-aware filtering, excludes common dependency/build trees and
binary content, detects the language of each retained source file, and emits a
structured JSON result consumed by the Parsing module (1.2).

## Technical Context

Language/Version: Python 3.11+
Primary Dependencies: Typer, pathspec, tree-sitter Python bindings, tree-sitter
language packages, pytest
Storage: N/A for the scanner itself; output is emitted as structured JSON and
the analyzed repository remains read-only
Testing: pytest with fixture-based integration tests and contract validation
Target Platform: Local CLI on Windows, macOS, and Linux
Project Type: CLI tool plus internal scanning library
Performance Goals: Stream through enterprise repositories with tens of
thousands of files without loading the full tree or full file contents into
memory at once
Constraints: Fully local execution, no cloud fallback, no external database or
broker, no writes into the scanned repository
Scale/Scope: Polyglot repositories with a strong focus on Python, JavaScript,
and Java source trees

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentiality absolute: pass
- Zero exposure network by default: pass
- Never repli silently vers le cloud: pass
- Traçabilité des réponses IA: pass; this feature does not generate AI text
- Ré-indexation incrémentale: pass in scope; the scanner streams traversal and
  does not materialize the repository tree in memory
- Infrastructure minimale et stockage local: pass
- Depot analyse en lecture seule: pass

## Project Structure

### Documentation for this feature

`specs/001-local-repo-scanner/`
├── `plan.md`
├── `research.md`
├── `data-model.md`
├── `quickstart.md`
└── `contracts/`
    ├── `cli.md`
    └── `scan-output.schema.json`

### Source Code

`src/`
├── `repo_scanner/`
│   ├── `__init__.py`
│   ├── `cli.py`
│   ├── `scanner.py`
│   ├── `ignore.py`
│   ├── `language.py`
│   ├── `binary.py`
│   ├── `models.py`
│   └── `output.py`
└── `tests/`
    ├── `unit/`
    ├── `integration/`
    └── `fixtures/`

Structure Decision: Use a single Python package under `src/repo_scanner` with a
thin Typer CLI wrapper and a streaming scan pipeline split into ignore handling,
binary detection, language detection, and output formatting modules.

## Phase 0: Research

### Decision 1

Choose Python + Typer for the CLI surface.

### Decision 2

Use `pathspec` to reproduce Git ignore semantics for repository-local filtering.

### Decision 3

Use Tree-sitter-backed language detection with a fast extension-based path for
common files and content fallback for ambiguous cases.

### Decision 4

Emit a stable JSON object on stdout for the Parsing module (1.2) to consume.

## Phase 1: Design

### Data model

Define repository, candidate path, scan entry, and scan result entities with
explicit relationships and validation rules.

### Contracts

Document the CLI contract and the JSON output schema used by downstream
consumers.

### Quickstart

Provide validation steps that prove ignored paths, binary files, and language
labels are handled correctly on a real polyglot repository.

## Constitution Check After Design

No violations introduced by the chosen design.

