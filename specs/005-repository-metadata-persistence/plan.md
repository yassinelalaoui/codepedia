# Implementation Plan: Repository Metadata Persistence

Branch: `005-repository-metadata-persistence` | Date: 2026-08-11 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/005-repository-metadata-persistence/spec.md`

## Summary

Build a local-only persistence layer that stores repository analysis metadata in
a single SQLite file. The persisted state must retain repository records,
source-file records, extracted symbols and their subtype-specific attributes,
and typed dependency relations so the tool can close and reopen without
re-analyzing unchanged content.

The persistence layer must support incremental file updates, fast retrieval of
all metadata for a single file or module, and content-hash based change
detection for source files.

## Technical Context

Language/Version: Python 3.11+
Primary Dependencies: sqlite3, dataclasses, hashlib, pathlib, typing, and the
existing repository scanning, symbol extraction, and dependency graph modules
Storage: Single local SQLite file; no external database server
Testing: pytest with unit, contract, and integration coverage
Target Platform: Local CLI/library usage on Windows, macOS, and Linux
Project Type: Internal analysis and indexing pipeline for repository metadata
Performance Goals: Incremental file-level updates, efficient file/module lookup,
and exact metadata restoration across reopen operations
Constraints: Fully local execution, no cloud fallback, read-only analyzed source
repositories, and stable persisted identities for files and symbols
Scale/Scope: Repository-level metadata persistence for multi-file codebases with
repeat indexing and dependency graph retention

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentiality absolute: pass
- Zero exposure network by default: pass
- Never repli silently vers le cloud: pass
- Traceabilite des reponses IA: pass; feature persists code metadata, not AI
  output
- Re-indexation incrementale: pass; incremental file updates are central to the
  feature
- Infrastructure minimale et stockage local: pass; SQLite file satisfies the
  local-storage requirement
- Depot analyse en lecture seule: pass

## Project Structure

### Documentation for this feature

`specs/005-repository-metadata-persistence/`
- `plan.md`
- `research.md`
- `data-model.md`
- `quickstart.md`
- `contracts/`
  - `repository-metadata-interface.md`
  - `sqlite-schema.md`

### Source Code

`src/`
- `repository_metadata/`
  - `__init__.py`
  - `models.py`
  - `store.py`
  - `sqlite_store.py`
  - `fingerprints.py`
- `parser_engine/`
- `dependency_graph/`

Structure Decision: Keep the persistence layer in a dedicated repository
metadata package so repository scanning, symbol extraction, and dependency
graph assembly remain separate concerns while sharing a common persisted
source of truth.

## Phase 0: Research

### Decision 1

Use a single embedded SQLite file to store repository, file, symbol, and edge
metadata.

### Decision 2

Model repository state with normalized tables for repositories, source files,
symbols, and dependency edges so incremental updates can replace one file's
records without rewriting unrelated content.

### Decision 3

Store a content hash and modification timestamp for each source file so the
indexer can quickly detect whether a file needs to be reprocessed.

### Decision 4

Represent symbol subtypes explicitly so module-, class-, and function-specific
attributes remain queryable after reopening the repository.

### Decision 5

Expose read and write operations that are optimized for a single file or module
scope so interactive lookups remain efficient on previously indexed content.

## Phase 1: Design

### Data model

Define repository, source file, symbol, dependency edge, and graph snapshot
entities with validation rules and relationships that support incremental
updates and deterministic reloads.

### Contracts

Document the SQLite schema layout and the public repository metadata storage
interface used by the application.

### Quickstart

Provide validation steps that prove initial indexing, incremental file updates,
file/module lookups, content-hash change detection, and reopen/reload behavior.

## Constitution Check After Design

No violations introduced by the chosen design.
