# Implementation Plan: Feature Grouping That Follows the Code

**Branch**: none. The work stays on `main` (owner rule). | **Date**: 2026-09-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/039-feature-grouping/spec.md`

## Summary

Spec 033 groups modules into the wiki's features using no model, and the
grouping is wrong in five measured ways (spec Background). This plan changes
the grouping stage of `src/doc_generator/features/` and nothing downstream.
Pages, the Overview, the planner's single call and the alias mechanism all
consume `Feature` exactly as before.

What changes:

- **Imports:** Java and JS/TS imports are resolved from the parsed import
  lines against a path index. Python keeps 033's graph-based adjacency
  untouched.
- **Seeds and tests:** test files neither seed groups nor pull production code
  into them. They are placed afterwards, with the code they exercise.
- **Folding:** groups fold by coupling, then by directory, never into the
  largest group. Entry modules are never absorbed by a group without one.
- **Counts and anchors:** entry-point counts are taken from members, and
  anchors prefer entry modules, then seeds.
- **Planner:** the prompt shows each group's seed and most relevant members
  under distinguishable labels, plus the README's opening paragraph. The plan
  cache key covers the grouping it was made for.

A read-only prototype of these rules, run on both reference repositories,
settled the one question deferred from clarify: every non-test module with an
entry point stays a seed. Research Decision 1 has the numbers. Largest
feature: 85% → 16% on `nextgen-wealth-ledger`, 18% on the sample. Java
modules coupled: 0 → 63 of 64. TypeScript: 2 → 42 of 43.

## Technical Context

**Language/Version**: Python ≥ 3.11 (project `.venv` is 3.13.7; 3.14 is avoided because Pydantic schema generation hangs).

**Primary Dependencies**: none new. Standard library only (`fractions`, `re`, `pathlib`). It builds on the existing `repository_metadata`, `dependency_graph` and `doc_generator.features`.

**Storage**: the existing `doc-manifest.sqlite`. There is no schema change: the plan cache key's inputs change, not the table (research Decision 9).

**Testing**: pytest. Run with `--basetemp` in the scratchpad and `-p no:cacheprovider`; the full suite takes about 10 minutes. Unit tests go in `tests/unit/test_feature_*.py`, integration tests in `tests/integration/`.

**Target Platform**: the local CLI (`codepedia index` / `serve`) on Windows, macOS and Linux.

**Project Type**: a single Python project (CLI plus a generated static wiki).

**Performance Goals**: grouping stays negligible next to indexing. The prototype groups 109 modules in well under a second, and import resolution is linear in import lines with one path-index lookup each.

**Constraints**:

- no model call in grouping;
- deterministic output, using exact `Fraction` weights and never float sums;
- the analysed repository is read-only;
- the planner's worst-case prompt stays within the 8,000-token provider budget, checked from constants;
- Python coupling is unchanged (spec FR-005).

**Scale/Scope**: reference repositories of 51 and 109 modules. Codepedia itself has about 140 modules. The candidate cap stays at 32.

## Constitution Check

*GATE: must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Assessment | Status |
| --- | --- | --- |
| 2.1 Remote by default, local on explicit choice | Grouping is static analysis and calls no model. The one planner call already goes through the configured summary chain (033 FR-033) and is unchanged. | Pass |
| 2.2 No network exposure by default | Nothing listens on a network. | Pass |
| 2.3 Failover only within a configured chain | Unchanged. The planner uses the same `FailoverExecutor`. | Pass |
| 2.4 Traceability of AI output | The planner's titles still attach to the candidates' modules. Anchors now name the modules that feature pages and the Overview cite, which improves traceability. | Pass |
| 2.5 Incremental re-indexing | An edit that does not reshape the feature list regenerates as before (033 FR-029). A reshaping edit forces the existing full pass (`requiresNavigationRegeneration`). The grouping is recomputed in memory from stored state; no file is re-parsed for it. | Pass |
| 2.6 Minimal infrastructure, local storage | No new store or dependency. | Pass |
| 2.7 Analysed repository read-only | Only the README and the already-parsed import lines are read. | Pass |

No violations, so Complexity Tracking is empty.

**Post-design re-check (after Phase 1)**: still passes. The design adds one
module inside `features/`, which takes no engine, like its siblings. It moves
three helpers (`is_test_path`, `ENTRY_KINDS`, `read_readme_lead`) from
`overview/evidence.py` down into `features/evidence.py`, next to a new
`entry_kind`, to avoid an import cycle (research Decision 3). No principle is
touched.

## Project Structure

### Documentation (this feature)

```text
specs/039-feature-grouping/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0: decisions and measurements
├── data-model.md        # Phase 1: changed and new types
├── quickstart.md        # Phase 1: how to verify on the reference repositories
├── contracts/
│   └── feature-grouping.md   # Phase 1: the grouping stage's rules and interfaces
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2, written by /speckit-tasks (not by this command)
```

### Source Code (repository root)

```text
src/doc_generator/
├── features/
│   ├── evidence.py     # + entry kinds per module, is_test_path, read_readme_lead, ENTRY_KINDS (moved here)
│   ├── imports.py      # NEW: resolve Java and JS/TS import lines to repository modules (no engine)
│   ├── fallback.py     # build_import_adjacency merges imports.py's edges; Python path unchanged
│   ├── candidates.py   # seeds exclude tests; production-only propagation; new folding; test placement
│   ├── validate.py     # anchor rule (entry module → seed → most connected); counts from members
│   └── planner.py      # member order and labels; README lead; cache key includes the grouping
├── overview/
│   └── evidence.py     # re-exports is_test_path / ENTRY_KINDS / read_readme_lead from features.evidence
└── prose.py            # disambiguated_labels (038 US4) reused for planner labels

tests/
├── unit/
│   ├── test_feature_imports.py      # NEW
│   ├── test_feature_candidates.py   # seeds, folding, entry modules, tests placement
│   ├── test_feature_validate.py     # anchors, counts
│   ├── test_feature_planner.py      # member order, labels, README lead, cache key, budget
│   └── test_feature_fallback.py     # adjacency merge; Python unchanged
└── integration/
    ├── test_feature_grouping_languages.py   # NEW: Java + TS fixture repository
    └── test_feature_navigation.py           # 033 guarantees re-asserted
```

**Structure Decision**: a single project. Everything changes inside
`src/doc_generator/features/` plus three re-exports. The generator's
`_ensure_features` keeps its four stages (evidence → adjacency → candidates →
plan → repair) and signature. `Feature`, `Candidate` and `FeaturePlan` keep
their existing fields (data-model.md), so pages, the Overview, search and
aliases need no change.

## Complexity Tracking

No constitution violations. Nothing to justify.
