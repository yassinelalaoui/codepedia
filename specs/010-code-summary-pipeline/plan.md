# Implementation Plan: Local Code Summary Pipeline

Branch: `010-code-summary-pipeline` | Date: 2026-08-11 | Spec: [spec.md](spec.md)

Input: Feature specification from `/specs/010-code-summary-pipeline/spec.md`

## Summary

Build a local summarization pipeline that walks the indexed repository
inventory, assembles symbol-specific context from the symbol source, its
imports, and its direct callers from the dependency graph, then asks the local
LLM for a concise natural-language description of the symbol's role. The
resulting summary is written back to the corresponding `Symbol.generatedSummary`
field in the repository metadata store.

The pipeline will reuse the existing local LLM engine for generation and the
existing dependency graph for caller context. It will run incrementally so that
only symbols affected by a file or symbol change are regenerated.

## Technical Context

Language/Version: Python 3.11+
Primary Dependencies: Python standard library, `local_llm`, `dependency_graph`,
`repository_metadata`, `parser_engine`, and the existing pytest-based test stack
Storage: Existing SQLite-backed repository metadata store; summaries are stored
in the existing `symbols.generated_summary` column
Testing: pytest with unit, contract, and integration coverage
Target Platform: Local CLI/library usage on Windows, macOS, and Linux
Project Type: Internal pipeline used by repository indexing and summary
generation
Performance Goals: Fast local availability checks before processing and
incremental regeneration limited to impacted symbols
Constraints: Local-only execution, no cloud fallback, repository read-only
outside of metadata persistence, and deterministic context assembly from local
source data
Scale/Scope: Repository-wide summary generation with symbol-level incremental
updates

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Confidentiality absolute: pass
- Zero exposure network by default: pass
- Never reply silently with a cloud service: pass
- Traceability of AI responses: pass; summaries are stored on the source symbol
  and remain attributable to the repository context that produced them
- Incremental local operation: pass; the pipeline regenerates only impacted
  summaries
- Minimal infrastructure and local storage: pass; it reuses the existing SQLite
  metadata store
- Repository analysis read-only: pass; source files remain untouched

## Project Structure

### Documentation for this feature

`specs/010-code-summary-pipeline/`
- `spec.md`
- `research.md`
- `data-model.md`
- `quickstart.md`
- `contracts/`
  - `code-summary-pipeline.md`

### Source Code

`src/`
- `repository_metadata/`
  - `summary_pipeline.py`
  - `summary_context.py`
  - `summary_prompts.py`
  - `store.py`
  - `sqlite_store.py`
- `local_llm/`
  - `engine.py`
- `dependency_graph/`
  - `graph.py`

Structure Decision: keep the summarization pipeline close to repository
metadata so it can read and update symbol records directly, while delegating
caller relationships to `DependencyGraph` and generation to `LocalLLMEngine`.

## Phase 0: Research

### Decision 1

Use `LocalLLMEngine` as the only generation backend and require an explicit
availability check before any symbol summary work starts.

### Decision 2

Assemble summary context from the symbol source text, its imports, and its
direct callers from `DependencyGraph`, keeping the prompt bounded to direct
relationships only.

### Decision 3

Model incremental regeneration around impacted symbol jobs derived from file
hash changes and dependency-graph neighborhoods so unchanged symbols keep their
existing summaries.

### Decision 4

Persist summaries by updating the existing `generated_summary` field on symbol
records in SQLite rather than adding a separate summary table.

### Decision 5

Keep prompt assembly and summary storage in the Python standard library and the
existing repository packages to preserve the offline footprint.

## Phase 1: Design

### Data model

Define the symbol summary job, the assembled context, the generated summary
result, and the impacted symbol set used for incremental updates.

### Contracts

Document the local pipeline interface, its dependency on `LocalLLMEngine`, the
dependency-graph inputs required for caller context, and the failure behavior
when the local model is unavailable.

### Quickstart

Provide validation steps that prove module and significant function summaries
are generated locally, stored on symbols, and regenerated only for impacted
symbols after a change.

## Constitution Check After Design

No violations introduced by the chosen design.
